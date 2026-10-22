"""Owns the single motion callback and commits complete timestamp-matched groups."""
from datetime import datetime
import json
from pathlib import Path
import uuid
from PIL import Image
from pxr import Usd,UsdGeom
from .camera_capture import CameraCapture,matrix_rows
from .cloud_rate import on_capture_grid
from .frame_groups import FrameGroups
from .performance import timed


def resolve_camera_configs(stage, config):
    candidates=[dict(c) for c in config.get('cameras',[]) if c.get('enabled',True)]
    for camera in candidates:
        if camera['id'] == 'rear': camera['id'] = 'back'
        # Existing scene15/16 keeps its authored transform and inherited asset.
        if (camera['id'] == 'back' and not stage.GetPrimAtPath(camera['prim_path'])
                and camera['prim_path'].endswith('/FisheyeBack')):
            legacy_path = camera['prim_path'][:-len('FisheyeBack')] + 'FisheyeRear'
            if stage.GetPrimAtPath(legacy_path): camera['prim_path'] = legacy_path
    if candidates:
        present=[bool(stage.GetPrimAtPath(c['prim_path'])) for c in candidates]
        if all(present):
            ids=[c['id'] for c in candidates]
            if len(ids)!=len(set(ids)) or any(not i.replace('_','').isalnum() for i in ids):
                raise ValueError('Camera IDs must be unique directory-safe names')
            rates={float(c['save_rate_hz']) for c in candidates}
            if len(rates)!=1: raise ValueError('Synchronized cameras must use the same save rate')
            return candidates
        # The previous scene14 remains supported through the legacy single-camera entry.
        # Its FisheyeFront overlaps one rig path, so recognize its explicitly authored ID.
        legacy=config.get('camera',{})
        old=stage.GetPrimAtPath(legacy.get('prim_path','/Missing'))
        if old and not old.GetCustomDataByKey('sensorVisualizer:cameraId') and sum(present)==1:
            return [dict(legacy,id='fisheye_front')] if legacy.get('enabled') else []
        raise ValueError('Incomplete camera rig: open scene15, or check configured camera paths')
    single=config.get('camera',{})
    return [dict(single,id='fisheye_front')] if single.get('enabled') else []


class CameraRig:
    def __init__(self,runtime,configs):
        self.runtime=runtime
        self.configs=configs
        self.cameras={}
        self.join=FrameGroups([c['id'] for c in configs])
        self.stream=self.directory=None
        self.count=0
        self.latest=None
        self.dropped=[]
        self._error=None
        self.closed=False

    async def initialize(self):
        for config in self.configs:
            self.cameras[config['id']]=CameraCapture(self.runtime,config,self.receive)
        self.runtime.motion.frame_observer=self.remember

    @property
    def error(self):
        return self._error or next((c.error for c in self.cameras.values() if c.error),None)

    @property
    def received(self): return sum(c.received for c in self.cameras.values())

    @property
    def unmatched(self): return sum(c.unmatched for c in self.cameras.values())

    @timed('camera.rig_pose_snapshot')
    def remember(self,snapshot):
        if self.cameras:
            first=next(iter(self.cameras.values()))
            if first.history and snapshot['time']<next(reversed(first.history))-1e-7:
                self.reset()
        cache=UsdGeom.XformCache(Usd.TimeCode.Default())
        lidars={s['frame_id']:matrix_rows(cache.GetLocalToWorldTransform(
            self.runtime.stage.GetPrimAtPath(s['prim_path']))) for s in self.runtime.config['sensors']}
        for camera in self.cameras.values():
            camera.remember(snapshot,cache,lidars)

    @timed('camera.group_including_save')
    def receive(self,cid,frame):
        if self.closed: return
        _,row=frame
        if not on_capture_grid(row['simulation_time'],self.configs[0]['save_rate_hz']): return
        complete,dropped=self.join.add(cid,row['simulation_time_ns'],frame)
        self._consume(complete,dropped)

    def _consume(self,complete,dropped):
        if self.stream: self.dropped.extend(dropped)
        for stamp,frames in complete:
            self.latest=(stamp,frames)
            if self.stream:
                try: self._save_group(stamp,frames)
                except Exception as exc:
                    self._error='Camera group save failed: '+str(exc)
                    self._finish_streams()
                    raise

    @timed('camera.save_group')
    def _save_group(self,stamp,frames):
        name=f'{self.count:06d}_{stamp:016d}.png'
        pending=[]
        for cid,camera in self.cameras.items():
            rgb,_=frames[cid]
            dest=camera.directory/'images'/name
            temporary=dest.with_suffix('.png.pending')
            with self.runtime.performance.span('camera.png_encode_write.'+cid):
                Image.fromarray(rgb[:,:,:3]).save(temporary,format='PNG')
            pending.append((temporary,dest))
        for temporary,dest in pending: temporary.replace(dest)
        index={'capture_index':self.count,'simulation_time_ns':stamp,
               'simulation_time':stamp/1e9,'cameras':{}}
        for cid,camera in self.cameras.items():
            _,row=frames[cid]
            row=dict(row,frame_index=self.count,image='images/'+name,camera_id=cid)
            camera.stream.write(json.dumps(row,allow_nan=False)+'\n')
            camera.stream.flush()
            camera.count+=1
            camera.last_saved=row['simulation_time']
            index['cameras'][cid]={'image':f'cameras/{cid}/images/{name}',
                                  'frame_metadata':f'cameras/{cid}/frames.jsonl','frame_index':self.count}
        # This index is the group commit marker; readers only consume these entries.
        self.stream.write(json.dumps(index,allow_nan=False)+'\n')
        self.stream.flush()
        self.count+=1

    def start(self,session_dir):
        if self.stream: raise ValueError('Camera rig recording already active')
        if self.error: raise RuntimeError(self.error)
        self.directory=Path(session_dir)
        self.join=FrameGroups(self.cameras)
        self.count=0;self.dropped=[]
        try:
            for c in self.cameras.values(): c.start(session_dir)
            self.stream=(self.directory/'capture_index.jsonl').open('x',encoding='utf-8')
        except Exception:
            for c in self.cameras.values(): c.stop()
            raise

    def _finish_streams(self):
        was_recording=self.stream is not None
        if self.stream: self.stream.close();self.stream=None
        for c in self.cameras.values(): c.stop()
        if was_recording:
            (self.directory/'capture_summary.json').write_text(json.dumps({
                'complete_groups':self.count,'camera_ids':list(self.cameras),
                'dropped_groups':len(self.dropped),'error':self.error},indent=2)+'\n')
            (self.directory/'capture_drops.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in self.dropped))

    def stop(self):
        complete,dropped=self.join.finish()
        try: self._consume(complete,dropped)
        finally: self._finish_streams()

    def snapshot(self):
        if not self.latest: raise ValueError('Play until a complete four-camera frame is available')
        stamp,frames=self.latest
        directory=Path(self.runtime.config['output_directory'])/'camera_snapshots'/(
            datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
        directory.mkdir(parents=True)
        index={'simulation_time_ns':stamp,'cameras':{}}
        for cid,camera in self.cameras.items():
            folder=directory/cid;folder.mkdir()
            rgb,row=frames[cid]
            Image.fromarray(rgb[:,:,:3]).save(folder/'image.png')
            (folder/'frame.json').write_text(json.dumps(row,indent=2)+'\n')
            (folder/'calibration.json').write_text(json.dumps(camera.calibration,indent=2)+'\n')
            index['cameras'][cid]=cid+'/image.png'
        (directory/'capture.json').write_text(json.dumps(index,indent=2)+'\n')
        return directory

    def preview(self,cid=None):
        self.cameras[cid or next(iter(self.cameras))].preview()

    def reset(self):
        self.stop()
        self.join=FrameGroups(self.cameras)
        self.latest=None
        for c in self.cameras.values(): c.reset()

    async def close(self):
        self.closed=True
        self.stop()
        if self.runtime.motion: self.runtime.motion.frame_observer=None
        for camera in self.cameras.values(): await camera.close()
