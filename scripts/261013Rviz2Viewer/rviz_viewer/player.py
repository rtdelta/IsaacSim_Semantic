"""Group playback with unchanged CDR timestamps and independent web control."""
import collections, json, queue, threading, time
from pathlib import Path
import numpy as np
from .model import choose_model_group, deadline_ns, forward_kinematics, matrix_pose, pose_matrix

class Player:
    def __init__(self,node,index,assets,log_directory):
        from rosidl_runtime_py.utilities import get_message
        from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
        from visualization_msgs.msg import MarkerArray
        from std_msgs.msg import String
        self.node,self.index,self.assets=node,index,Path(assets).resolve()
        self.manifest=json.loads((self.assets/'manifest.json').read_text())
        if self.manifest['scene_sha256']!=self.scene_hash():raise ValueError('Viewer mesh and capture scene hashes differ')
        for part in self.manifest['parts'].values():
            import hashlib
            if hashlib.sha256((self.assets/part['mesh']).read_bytes()).hexdigest()!=part['sha256']:raise ValueError('Viewer mesh hash mismatch')
        self.classes={name:get_message(kind) for name,kind in index.types.items()}
        latched=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publishers={name:node.create_publisher(cls, name,latched if index.types[name]=='sensor_msgs/msg/PointCloud2' else 100) for name,cls in self.classes.items()}
        self.markers=node.create_publisher(MarkerArray,'/rviz_viewer/excavator',latched)
        self.status_pub=node.create_publisher(String,'/rviz_viewer/status',latched)
        self.commands=queue.Queue(64);self.lock=threading.Lock()
        self.state={'group':0,'groups':len(index.frames),'playing':False,'rate_hz':10.,'mode':'synchronized','model_offset':0,'alpha':.55,'error':None,'published_groups':0,'stamps_unchanged':True,'topics':[name for name,kind in index.types.items() if kind=='sensor_msgs/msg/PointCloud2']}
        self.origin=0;self.play_index=0;self.due=0;self.last_heartbeat=0
        self.raw_root=None;self.raw_joints={};self.raw_tf={};self.last_tf=None
        self.prefetch_pool=None;self.prefetched={}
        from concurrent.futures import ThreadPoolExecutor
        self.prefetch_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='rviz-bag-prefetch')
        self.log_directory=Path(log_directory);self.log_directory.mkdir(parents=True,exist_ok=True)
        self.log=(self.log_directory/'playback_events.jsonl').open('x',encoding='utf-8',buffering=1)
        self.intervals=[];self.previous_emit=None
        self.receivers=[node.create_subscription(self.classes[name],name,lambda msg,topic=name:self.receive(msg,topic),latched if index.types[name]=='sensor_msgs/msg/PointCloud2' else 100) for name in self.classes if index.types[name]=='sensor_msgs/msg/PointCloud2']
        self.event('initialized',audit=index.report)
        self.show(0)

    def scene_hash(self):
        import sqlite3
        with sqlite3.connect(self.index.path) as db:capture=Path(json.loads(db.execute("SELECT value FROM settings WHERE key='capture'").fetchone()[0]))
        for file,key in (('asset_manifest.json','root_sha256'),('spec.json','scene_sha256')):
            if (capture/file).is_file():return json.loads((capture/file).read_text())[key]
        raise ValueError('Capture scene provenance is missing')

    def event(self,name,**data):self.log.write(json.dumps({'event':name,'monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns(),**data},allow_nan=False)+'\n')
    def receive(self,msg,topic):
        import hashlib
        self.event('received',topic=topic,stamp_ns=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec,points=msg.width*msg.height,payload_sha256=hashlib.sha256(bytes(msg.data)).hexdigest())
    def snapshot(self):
        with self.lock:return dict(self.state)
    def request(self,command):self.commands.put_nowait(command)
    def status(self):
        from std_msgs.msg import String
        with self.lock:
            f=self.index.frames[self.state['group']]
            self.state.update(logical_time_s=f['logical_time_s'],header_stamp_ns=f['stamp_ns'])
            value=dict(self.state)
        self.status_pub.publish(String(data=json.dumps(value)));return value

    def bodies(self,group):
        frame=self.index.frames[group]
        if frame['body_world_row']:return {name:np.asarray(matrix).T for name,matrix in frame['body_world_row'].items()}
        if not frame['root_col']:raise ValueError('No root pose for group')
        return forward_kinematics(self.manifest,frame['root_col'],frame['joints_rad'])

    def publish_model(self,bodies,stamp,group):
        from visualization_msgs.msg import Marker,MarkerArray
        colors=[(.35,.4,.45),(.95,.65,.12),(.95,.75,.15),(.9,.5,.1),(.55,.35,.2)]
        markers=[]
        for i,(name,part) in enumerate(self.manifest['parts'].items()):
            p,q=matrix_pose(bodies[name]);m=Marker();m.header.frame_id='world';m.header.stamp.sec,m.header.stamp.nanosec=divmod(int(stamp),10**9)
            m.ns='excavator';m.id=i;m.type=Marker.MESH_RESOURCE;m.action=Marker.ADD
            m.mesh_resource=(self.assets/part['mesh']).as_uri();m.mesh_use_embedded_materials=False
            m.scale.x=m.scale.y=m.scale.z=1.
            m.pose.position.x,m.pose.position.y,m.pose.position.z=p
            m.pose.orientation.x,m.pose.orientation.y,m.pose.orientation.z,m.pose.orientation.w=q
            m.color.r,m.color.g,m.color.b=colors[i];m.color.a=self.state['alpha'];markers.append(m)
        self.markers.publish(MarkerArray(markers=markers))
        self.event('model_published',cloud_group=group,model_group=group+self.state['model_offset'],stamp_ns=stamp)

    def reset(self,stamp):
        from visualization_msgs.msg import Marker,MarkerArray
        from sensor_msgs.msg import PointCloud2
        m=Marker(action=Marker.DELETEALL);self.markers.publish(MarkerArray(markers=[m]))
        for topic,kind in self.index.types.items():
            if kind!='sensor_msgs/msg/PointCloud2':continue
            msg=PointCloud2(height=1,width=0,point_step=12,row_step=0,is_dense=True)
            msg.header.frame_id='world';msg.header.stamp.sec,msg.header.stamp.nanosec=divmod(stamp,10**9)
            self.publishers[topic].publish(msg)
        self.raw_tf={};self.last_tf=None;self.event('display_reset',stamp_ns=stamp)

    def rows(self,group,mode):
        key=(group,mode);future=self.prefetched.pop(key,None)
        result=future.result() if future else self.index.messages(group,mode)
        for n in range(group+1,min(group+4,len(self.index.frames))):
            k=(n,mode)
            if k not in self.prefetched:self.prefetched[k]=self.prefetch_pool.submit(self.index.messages,n,mode)
        for key in list(self.prefetched):
            if key[1]!=mode or not group<key[0]<group+4:self.prefetched.pop(key).cancel()
        return result

    def raw_update(self,topic,msg,stamp,group):
        changed=False
        if topic=='/excavator/root_pose':
            p,q=msg.pose.position,msg.pose.orientation;self.raw_root=pose_matrix([p.x,p.y,p.z],[q.x,q.y,q.z,q.w]);changed=True
        elif topic=='/joint_states':self.raw_joints=dict(zip(msg.name,msg.position));changed=True
        elif topic=='/tf':
            for t in msg.transforms:
                p,q=t.transform.translation,t.transform.rotation
                self.raw_tf[t.child_frame_id]=(t.header.frame_id,pose_matrix([p.x,p.y,p.z],[q.x,q.y,q.z,q.w]))
            def world(child,seen=None):
                if child=='world':return np.eye(4)
                seen=set() if seen is None else seen
                if child in seen or child not in self.raw_tf:raise KeyError(child)
                seen.add(child);parent,matrix=self.raw_tf[child];return world(parent,seen)@matrix
            try:self.raw_root=world('swing_coordinate');changed=True
            except KeyError:pass
        elif topic=='/sensor_visualizer/frame_index':
            value=json.loads(msg.data)
            if value.get('viewer_body_world_row'):
                self.publish_model({name:np.asarray(row).T for name,row in value['viewer_body_world_row'].items()},stamp,group);return
        if changed and self.raw_root is not None and all(j['name'] in self.raw_joints for j in self.manifest['joints']):
            self.publish_model(forward_kinematics(self.manifest,self.raw_root,self.raw_joints),stamp,group)

    def show(self,group,scheduled=None):
        from rclpy.serialization import deserialize_message
        from rosgraph_msgs.msg import Clock
        if not 0<=group<len(self.index.frames):raise ValueError('Group outside bag')
        mode=self.state['mode'];model_group=choose_model_group(group,self.state['model_offset'],len(self.index.frames))
        stamp=self.index.stamps[group];started=time.monotonic_ns();rows=self.rows(group,mode)
        if group<self.state['group'] or abs(group-self.state['group'])>1:self.reset(stamp)
        self.event('group_started',group=group,mode=mode,scheduled_ns=scheduled,late_ns=max(0,started-scheduled) if scheduled else 0)
        if mode=='synchronized':
            clock=Clock();clock.clock.sec,clock.clock.nanosec=divmod(stamp,10**9);self.publishers['/clock'].publish(clock)
            ordered=sorted(rows,key=lambda row:0 if row[0]=='/tf' else 1 if row[0]=='/joint_states' else 2)
            self.publish_model(self.bodies(model_group),stamp,group)
        else:
            ordered=rows
            if self.raw_root is None:
                previous=self.index.frames[max(0,group-1)];self.raw_root=np.asarray(previous['root_col']);self.raw_joints=dict(previous['joints_rad'])
        for topic,raw,source,recorded in ordered:
            if mode=='synchronized' and topic=='/clock':continue
            if mode=='original':
                target=started+round((recorded-stamp)*10/self.state['rate_hz'])
                remaining=(target-time.monotonic_ns())/1e9
                if remaining>0:time.sleep(remaining)
            msg=deserialize_message(raw,self.classes[topic])
            self.publishers[topic].publish(msg)
            if topic=='/tf':self.last_tf=msg
            if mode=='original':self.raw_update(topic,msg,source,group)
            payload={}
            if self.index.types[topic]=='sensor_msgs/msg/PointCloud2':
                import hashlib
                payload={'points':msg.width*msg.height,'payload_sha256':hashlib.sha256(bytes(msg.data)).hexdigest()}
            self.event('published',group=group,topic=topic,header_stamp_ns=source,recorded_ns=recorded,source_message_fields_unchanged=True,**payload)
        if self.previous_emit is not None:self.intervals.append((started-self.previous_emit)/1e6)
        self.previous_emit=started
        with self.lock:self.state.update(group=group,published_groups=self.state['published_groups']+1,error=None)
        self.event('group_complete',group=group,duration_ns=time.monotonic_ns()-started);self.status()

    def tick(self):
        while True:
            try:command=self.commands.get_nowait()
            except queue.Empty:break
            try:
                action=command.get('action');self.event('command',command=command)
                if action=='play':
                    if self.state['group']==len(self.index.frames)-1:self.show(0)
                    self.state['playing']=True;self.origin=time.monotonic_ns();self.play_index=1;self.due=deadline_ns(self.origin,1,self.state['rate_hz']);self.previous_emit=None
                elif action=='pause':self.state['playing']=False
                elif action in ('step','seek'):
                    self.state['playing']=False
                    target=command['group'] if action=='seek' else self.state['group']+command.get('delta',1)
                    self.raw_root=None;self.show(int(target))
                elif action=='configure':
                    self.state['playing']=False
                    if 'mode' in command:
                        if command['mode'] not in ('synchronized','original'):raise ValueError('Invalid mode')
                        self.state['mode']=command['mode'];self.raw_root=None
                        self.reset(self.index.stamps[self.state['group']])
                    if 'rate_hz' in command:
                        rate=float(command['rate_hz'])
                        if not .1<=rate<=60:raise ValueError('Rate must be 0.1 to 60 groups/s')
                        self.state['rate_hz']=rate
                    if 'alpha' in command:
                        alpha=float(command['alpha'])
                        if not 0<=alpha<=1:raise ValueError('Invalid mesh opacity')
                        self.state['alpha']=alpha
                    if 'model_offset' in command:
                        offset=int(command['model_offset'])
                        if offset not in (-2,-1,0,1,2):raise ValueError('Offset must be -2 to 2')
                        self.state['model_offset']=offset
                    if self.state['mode']=='original' and self.state['model_offset']!=0:raise ValueError('Model offset is only available in synchronized mode')
                    self.show(self.state['group'])
                else:raise ValueError('Unknown action')
            except Exception as exc:
                self.state.update(playing=False,error=str(exc));self.event('command_failed',error=str(exc))
            self.status()
        now=time.monotonic_ns()
        if self.state['playing'] and now>=self.due:
            target=self.state['group']+1
            if target>=len(self.index.frames):self.state['playing']=False;self.status()
            else:
                try:self.show(target,self.due)
                except Exception as exc:self.state.update(playing=False,error=str(exc));self.event('play_failed',error=str(exc));self.status()
                self.play_index+=1;self.due=deadline_ns(self.origin,self.play_index,self.state['rate_hz'])
        # Paused TF heartbeat allows a newly opened RViz to transform latched clouds.
        if not self.state['playing'] and now-self.last_heartbeat>1_000_000_000:
            if self.last_tf:self.publishers['/tf'].publish(self.last_tf)
            self.last_heartbeat=now

    def close(self):
        self.prefetch_pool.shutdown(wait=True,cancel_futures=True)
        values=np.asarray(self.intervals);report={'groups_published':self.state['published_groups'],'interval_samples':len(values),'interval_ms_median':float(np.median(values)) if len(values) else None,'interval_ms_p95':float(np.percentile(values,95)) if len(values) else None,'note':'Intervals include manual operations unless a dedicated play-only validation session was used; per-event scheduled/actual times are retained.'}
        (self.log_directory/'summary.json').write_text(json.dumps(report,indent=2));self.log.close()
