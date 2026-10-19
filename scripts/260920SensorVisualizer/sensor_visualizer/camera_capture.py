"""Frame-matched fisheye RGB capture using one Replicator writer callback."""
from collections import OrderedDict
from datetime import datetime
import json
from pathlib import Path
import uuid
import numpy as np
from PIL import Image
import omni.replicator.core as rep
from pxr import Gf, Usd, UsdGeom
from .cloud_rate import on_capture_grid
from .performance import timed


def matrix_rows(matrix):
    return [[float(matrix[i][j]) for j in range(4)] for i in range(4)]


class FrameWriter(rep.Writer):
    version = '1.0'

    def __init__(self, owner):
        self.owner = owner
        timestamp = rep.AnnotatorRegistry.get_annotator('IsaacReadSimulationTime')
        timestamp.initialize(resetOnStop=True)
        self.annotators = [rep.AnnotatorRegistry.get_annotator('rgb'), timestamp,
                          rep.AnnotatorRegistry.get_annotator('CameraParams')]

    def write(self, data):
        try:
            self.owner.receive(data)
        except Exception as exc:
            self.owner.error = 'Camera capture stopped: '+str(exc)
            self.owner.stop()

    def write_metadata(self):
        # Calibration and frame metadata are owned by CameraCapture, not a backend.
        pass


class CameraCapture:
    def __init__(self, runtime, config=None, on_frame=None):
        self.runtime = runtime
        self.config = dict(config if config is not None else runtime.config['camera'])
        self.id = self.config.get('id','fisheye_front')
        self.on_frame = on_frame
        self.path = self.config['prim_path']
        self.stage = runtime.stage
        prim = self.stage.GetPrimAtPath(self.path)
        if not prim or not prim.IsA(UsdGeom.Camera):
            raise ValueError('Missing configured camera '+self.path)
        if prim.GetAttribute('omni:lensdistortion:model').Get() != 'opencvFisheye':
            raise ValueError('Expected an OpenCV fisheye camera')
        self.history = OrderedDict()
        self.writer = self.product = None
        self.stream = self.directory = None
        self.count = self.received = self.unmatched = 0
        self.last_time = self.last_saved = None
        self.error = None
        self.latest = self.preview_window = None
        self.sequence = 0
        self.closed = False
        width, height = self.config.get('resolution') or list(prim.GetAttribute(
            'omni:lensdistortion:opencvFisheye:imageSize').Get())
        self.config['resolution']=[width,height]
        if [int(v) for v in prim.GetAttribute('omni:lensdistortion:opencvFisheye:imageSize').Get()] != [width,height]:
            raise ValueError('Camera resolution must match its fisheye calibration imageSize')
        source = prim.GetCustomDataByKey('sensorVisualizer') or {}
        self.calibration = {
            'camera_id':self.id,
            'camera_prim':self.path, 'width':width, 'height':height,
            'model':'opencv_fisheye',
            'intrinsics':{n:float(prim.GetAttribute('omni:lensdistortion:opencvFisheye:'+n).Get())
                          for n in ('fx','fy','cx','cy','k1','k2','k3','k4')},
            'calibration_source':source.get('cameraAsset','synthetic ideal equidistant; not physical calibration'),
            'source_asset_prim':source.get('cameraAssetPrim'),
            'source_asset_sha256_at_assembly':source.get('sourceSha256'),
            'source_extrinsic_applied':False,
            'mount_position_source':source.get('positionSource'),
            'exposure':{a.GetName():a.Get() for a in prim.GetAttributes()
                        if a.GetName().startswith('exposure:')},
            'camera_usd_axes':'X right, Y up, -Z forward',
            'camera_optical_axes':'X right, Y down, Z forward',
            'matrix_convention':'USD/Gf row vectors: p_world = p_local @ local_to_world',
            'quaternion_order':'xyzw', 'units':'metres and radians',
            'time_source':'IsaacReadSimulationTime annotator on the RGB render product, resetOnStop=True',
            'save_rate_hz':self.config['save_rate_hz'],
            'pointcloud_storage':'ROS2 MCAP in the same session/bag; join on message header time, never file order',
        }
        with Usd.EditContext(self.stage, runtime.layer):
            self.product = rep.create.render_product(self.path, (width,height),
                name='SV_Fisheye_'+uuid.uuid4().hex[:8], force_new=True, write_to_session_layer=False)
        self.writer = FrameWriter(self)
        try:
            self.writer.attach([self.product.path])
        except Exception:
            self.writer.detach()
            self.product.destroy()
            raise
        if self.on_frame is None:
            runtime.motion.frame_observer = self.remember

    @timed('camera.pose_snapshot')
    def remember(self, snapshot, cache=None, lidar_to_world=None):
        # Called immediately after articulation state and USD transforms are updated.
        t = float(snapshot['time'])
        if self.history and t < next(reversed(self.history))-1e-7:
            self.reset()
        cache = cache if cache is not None else UsdGeom.XformCache(Usd.TimeCode.Default())
        camera = cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(self.path))
        parent = cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(self.path).GetParent())
        optical = Gf.Matrix4d(1.).SetScale(Gf.Vec3d(1.,-1.,-1.)) * camera
        root = self.runtime.motion._root_matrix(snapshot['root_position'],
            [snapshot['root_xyzw'][3], *snapshot['root_xyzw'][:3]])
        row = {
            'simulation_time':t, 'root_position':snapshot['root_position'],
            'root_orientation_xyzw':snapshot['root_xyzw'],
            'base_control':snapshot.get('base_control'),
            'joint_names':snapshot['names'], 'joint_positions_rad':snapshot['positions'],
            'camera_usd_to_world':matrix_rows(camera), 'camera_optical_to_world':matrix_rows(optical),
            'camera_usd_to_parent':matrix_rows(camera * parent.GetInverse()),
            'camera_parent':str(self.stage.GetPrimAtPath(self.path).GetParent().GetPath()),
            'camera_usd_to_base':matrix_rows(camera * root.GetInverse()),
            'lidar_to_world':lidar_to_world if lidar_to_world is not None else {
                s['frame_id']:matrix_rows(cache.GetLocalToWorldTransform(
                self.stage.GetPrimAtPath(s['prim_path']))) for s in self.runtime.config['sensors']}}
        self.history[t] = row
        while len(self.history)>240:
            self.history.popitem(last=False)

    @timed('camera.receive_including_save')
    def receive(self, data):
        if self.closed or not self.runtime.timeline.is_playing():
            return
        def fetch(prefix):
            return next((v for k,v in data.items() if k == prefix or k.startswith(prefix+'-')), None)
        rgb, timing, params = fetch('rgb'), fetch('IsaacReadSimulationTime'), fetch('CameraParams')
        if rgb is None or timing is None or params is None:
            return
        if isinstance(rgb, dict): rgb=rgb['data']
        t=float(timing['simulationTime'])
        if self.last_time is not None and abs(t-self.last_time)<1e-7:
            return
        self.last_time=t
        self.received+=1
        if not self.history:
            self.unmatched+=1
            return
        key=min(self.history, key=lambda v:abs(v-t))
        if abs(key-t)>1e-5:
            self.unmatched+=1
            return
        row=dict(self.history[key])
        # Independent renderer evidence: never pair an image with a different pose.
        view=np.asarray(params['cameraViewTransform'],dtype=np.float64).reshape(4,4)
        rendered_world=np.linalg.inv(view)
        expected=np.asarray(row['camera_usd_to_world'])
        error=float(np.max(np.abs(rendered_world-expected)))
        if error>2e-3:
            self.unmatched+=1
            return
        rgba=np.asarray(rgb,dtype=np.uint8)
        if rgba.ndim!=3 or rgba.shape[2] not in (3,4):
            raise ValueError('Unexpected RGB shape '+str(rgba.shape))
        row.update(simulation_time=t, simulation_time_ns=round(t*1e9),
                   render_pose_max_abs_error=error, lens_distortion_model='opencvFisheye',
                   renderer_projection_model_legacy=str(params.get('cameraModel','')))
        self.latest=(rgba.copy(),row)
        if self.on_frame is not None:
            self.on_frame(self.id,self.latest)
            return
        if (self.stream and on_capture_grid(t,self.config['save_rate_hz']) and
                (self.last_saved is None or t-self.last_saved>=1/self.config['save_rate_hz']-1e-7)):
            name=f'images/{self.count:06d}_{round(t*1e9):016d}.png'
            Image.fromarray(rgba[:,:,:3]).save(self.directory/name)
            row.update(frame_index=self.count,image=name)
            self.stream.write(json.dumps(row,allow_nan=False)+'\n')
            self.stream.flush()
            self.count+=1
            self.last_saved=t

    def start(self, session_dir):
        if self.stream:
            raise ValueError('Camera recording is already active')
        self.directory=Path(session_dir)/'cameras'/self.id
        (self.directory/'images').mkdir(parents=True,exist_ok=False)
        (self.directory/'calibration.json').write_text(json.dumps(self.calibration,indent=2)+'\n')
        self.stream=(self.directory/'frames.jsonl').open('w',encoding='utf-8')
        self.count=0
        self.last_saved=None
        self.error=None
        self._start_received,self._start_unmatched=self.received,self.unmatched

    def stop(self):
        if self.stream:
            self.stream.close()
            self.stream=None
            (self.directory/'summary.json').write_text(json.dumps({
                'saved_frames':self.count, 'received_during_recording':self.received-self._start_received,
                'unmatched_during_recording':self.unmatched-self._start_unmatched,
                'error':self.error},indent=2)+'\n')

    def snapshot(self):
        if not self.latest:
            raise ValueError('Play simulation until a matched camera frame is available')
        directory=Path(self.runtime.config['output_directory'])/'camera_snapshots'/(
            datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
        directory.mkdir(parents=True)
        rgb,row=self.latest
        Image.fromarray(rgb[:,:,:3]).save(directory/'image.png')
        (directory/'frame.json').write_text(json.dumps(row,indent=2)+'\n')
        (directory/'calibration.json').write_text(json.dumps(self.calibration,indent=2)+'\n')
        return directory

    def preview(self):
        from omni.kit.viewport.utility import create_viewport_window
        if self.preview_window:
            self.preview_window.destroy()
        width,height=self.config['resolution']
        self.preview_window=create_viewport_window('Fisheye '+self.id.title(),width=720,
                                                   height=int(720*height/width))
        self.preview_window.viewport_api.camera_path=self.path

    def reset(self):
        self.stop()
        self.history.clear()
        self.last_time=self.last_saved=None
        self.latest=None

    async def close(self):
        self.closed=True
        self.stop()
        if self.runtime.motion and self.on_frame is None:
            self.runtime.motion.frame_observer=None
        if self.preview_window:
            self.preview_window.destroy()
            self.preview_window=None
        if self.writer:
            self.writer.detach()
            self.writer=None
            for _ in range(2): await self.runtime.app.next_update_async()
        if self.product:
            self.product.destroy()
            self.product=None
