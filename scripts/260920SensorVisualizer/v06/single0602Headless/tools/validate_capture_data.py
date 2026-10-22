
import io,json,sys,math,hashlib
from collections import Counter
from pathlib import Path
import rosbag2_py
import numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from PIL import Image
p=Path(sys.argv[1]);registry=json.loads((p/'sensor_registry.json').read_text())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from single0602_headless.trajectory import Trajectory
from single0602_headless.frame_contract import CONTRACT,verify_swing
from single0602_headless.scene_replay import place_state
job=json.loads((p/'job_spec.json').read_text());source=None
if job['replay']['mode'] in ('offline','live_complete'):source=Trajectory.load(job['replay']['trajectory'])
report=json.loads((p/'writer_report.json').read_text());assert report['state']=='finished',report
assets=json.loads((p/'asset_manifest.json').read_text())
assert hashlib.sha256(Path(assets['root_layer']).read_bytes()).hexdigest()==assets['root_sha256'],'Root USD changed'
r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=str(p/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
types={x.name:get_message(x.type) for x in r.get_all_topics_and_types()}
counts=Counter();frames=[];stamps=set();image_shapes={};point_counts={};tf_count=set();cameras={c['id']:c for c in registry['cameras']}
digests={}
roots={};joints={};tf_by_stamp={};camera_poses={};root_errors=[];joint_errors=[];quat_errors=[];transform_errors=[]

def matrix(position,quaternion):
    x,y,z,w=quaternion;assert abs(x*x+y*y+z*z+w*w-1)<2e-5
    out=np.eye(4);out[:3,3]=position
    out[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    return out

def pose_matrix(p):return matrix([getattr(p.position,n) for n in 'xyz'],[getattr(p.orientation,n) for n in 'xyzw'])
def stamp(s):return s.sec*10**9+s.nanosec
while r.has_next():
    topic,data,t=r.read_next();m=deserialize_message(data,types[topic]);counts[topic]+=1
    if topic in report['counts']:digests.setdefault(topic,hashlib.sha256()).update(int(t).to_bytes(8,'little')+data)
    if hasattr(m,'header'):assert stamp(m.header.stamp)==t,(topic,t)
    if topic=='/clock':assert stamp(m.clock)==t
    if topic=='/excavator/root_pose':roots[t]=m.pose
    if topic=='/joint_states':joints[t]=dict(zip(m.name,m.position))
    if topic.startswith('/camera/') and topic.endswith('/pose'):camera_poses[(t,topic.split('/')[2])]=pose_matrix(m.pose)
    if topic=='/tf':
        assert all(stamp(v.header.stamp)==t for v in m.transforms)
        children=[v.child_frame_id for v in m.transforms];assert len(children)==len(set(children));tf_count.add(len(children))
        tf_by_stamp[t]={v.child_frame_id:(v.header.frame_id,matrix([getattr(v.transform.translation,n) for n in 'xyz'],
            [getattr(v.transform.rotation,n) for n in 'xyzw'])) for v in m.transforms}
    if topic.endswith('/image_raw/compressed'):
        cid=topic.split('/')[2];image=Image.open(io.BytesIO(bytes(m.data)));image.load()
        expected=cameras[cid]['calibration'];assert image.size==(expected['width'],expected['height'])
        assert image.mode=='RGB';image_shapes[cid]=[image.width,image.height]
        assert any(hi-lo>2 for lo,hi in image.getextrema()),'Uniform image frame'
    if topic.endswith('/camera_info'):
        cid=topic.split('/')[2];cal=cameras[cid]['calibration'];v=cal['intrinsics']
        fisheye=cal['model']=='opencv_fisheye'
        assert m.distortion_model==('equidistant' if fisheye else cal['distortion_model']) and len(m.d)==(4 if fisheye else len(cal['distortion']))
        assert [m.width,m.height]==[cal['width'],cal['height']]
        assert np.allclose(m.d,[v['k1'],v['k2'],v['k3'],v['k4']] if fisheye else cal['distortion'],rtol=0,atol=1e-12)
        assert np.allclose(m.k,[v['fx'],0,v['cx'],0,v['fy'],v['cy'],0,0,1],rtol=0,atol=1e-12)
    if hasattr(m,'point_step'):
        assert m.point_step==12 and m.row_step==m.width*12 and len(m.data)==m.row_step
        assert [(f.name,f.offset,f.datatype,f.count) for f in m.fields]==[('x',0,7,1),('y',4,7,1),('z',8,7,1)]
        assert not m.is_bigendian and np.isfinite(np.frombuffer(bytes(m.data),dtype='<f4')).all()
        point_counts.setdefault(topic,[]).append(m.width)
    if topic=='/sensor_visualizer/frame_index':
        frame=json.loads(m.data);assert frame['simulation_time_ns']==t;assert 'trajectory' in frame
        for key,value in CONTRACT.items():assert frame['frame_contract'][key]==value,(key,frame['frame_contract'])
        verify_swing(frame['frame_contract']['swing_zero_readback']['native_angle_rad'],frame['frame_contract']['swing_zero_mapping'])
        assert abs(frame['source_clock_before_s']-frame['source_clock_after_s'])<1e-9
        assert abs(frame['trajectory']['time_quantization_error_s'])<=1/120+1e-6
        frames.append(frame);stamps.add(t)
assert len(frames)==report['groups']==len(stamps)
assert all(counts[k]==v for k,v in report['counts'].items())
assert {k:v.hexdigest() for k,v in digests.items()}==report['digests'],'Recorded message digest mismatch'
assert tf_count=={len(registry['lidars'])+len(registry['cameras'])+2}
for topic in types:
    if topic not in ('/sensor_visualizer/run_metadata','/sensor_visualizer/camera_metadata'):assert counts[topic]==len(frames),(topic,counts[topic])
assert [x['group_id'] for x in frames]==list(range(len(frames)))
assert all(b['simulation_time_ns']>a['simulation_time_ns'] for a,b in zip(frames,frames[1:]))
for frame in frames:
    t=frame['simulation_time_ns'];transforms=tf_by_stamp[t]
    mapping=frame['frame_contract']['swing_zero_mapping']
    assert abs(joints[t][mapping['joint_name']]-mapping['native_zero_rad'])<=mapping['tolerance_rad']
    def world(name,seen=None):
        if name=='world':return np.eye(4)
        seen=set() if seen is None else set(seen);assert name not in seen,'TF cycle';seen.add(name)
        parent,local=transforms[name];return world(parent,seen)@local
    transform_errors.append(float(np.max(np.abs(world('swing_coordinate')-pose_matrix(roots[t])))))
    for sensor in registry['lidars']:
        expected=np.asarray(frame['lidars'][sensor['id']]['to_world'],dtype=float).T
        if sensor.get('binding',{}).get('category')=='world_static':assert transforms[sensor['frame_id']][0]=='world'
        transform_errors.append(float(np.max(np.abs(world(sensor['frame_id'])-expected))))
    for cid in cameras:
        expected=np.asarray(frame['cameras'][cid]['to_world'],dtype=float).T@np.diag([1,-1,-1,1])
        if cameras[cid].get('binding',{}).get('category')=='world_static':assert transforms['camera_'+cid+'_optical'][0]=='world'
        transform_errors.append(float(np.max(np.abs(world('camera_'+cid+'_optical')-expected))))
        transform_errors.append(float(np.max(np.abs(camera_poses[t,cid]-expected))))
assert max(transform_errors)<2e-5,'TF / source sensor matrix mismatch'
fixed_errors=[];root_mount_errors=[]
for kind in ('cameras','lidars'):
    for device in registry[kind]:
        category=device.get('binding',{}).get('category')
        if category not in ('world_static','robot_root'):continue
        matrices=[]
        for frame in frames:
            value=np.asarray(frame[kind][device['id']]['to_world'])
            if category=='robot_root':value=value@np.linalg.inv(pose_matrix(roots[frame['simulation_time_ns']]).T)
            matrices.append(value)
        differences=[float(np.max(np.abs(v-matrices[0]))) for v in matrices]
        (fixed_errors if category=='world_static' else root_mount_errors).extend(differences)
assert max(fixed_errors,default=0)<2e-5,'World fixed sensor moved with excavator'
assert max(root_mount_errors,default=0)<2e-5,'Root-mounted sensor did not follow the excavator'
if source:
    for frame in frames:
        t=frame['simulation_time_ns'];expected=place_state(source.sample(frame['trajectory']['trajectory_time_s']),job['replay'].get('placement'));actual=roots[t]
        root_errors.append(max(abs(getattr(actual.position,n)-v) for n,v in zip('xyz',expected['position_world_m'])))
        a=[getattr(actual.orientation,n) for n in 'xyzw'];b=expected['quaternion_xyzw']
        quat_errors.append(min(math.sqrt(sum((x-y)**2 for x,y in zip(a,b))),math.sqrt(sum((x+y)**2 for x,y in zip(a,b)))))
        joint_errors.append(max(abs(joints[t][n]-math.radians(v)) for n,v in expected['joints_deg'].items()))
    assert max(root_errors)<2e-5 and max(quat_errors)<2e-5 and max(joint_errors)<2e-5,(max(root_errors),max(quat_errors),max(joint_errors))
out={'passed':True,'session':str(p),'groups':len(frames),'topics':len(types),'messages':sum(counts.values()),
     'lidars':len(registry['lidars']),'cameras':len(registry['cameras']),'image_shapes':image_shapes,'tf_edges':list(tf_count),
     'source_times':[x['trajectory']['trajectory_time_s'] for x in frames],
     'native_times_ns':[x['simulation_time_ns'] for x in frames],
     'point_count_ranges':{k:[min(v),max(v)] for k,v in point_counts.items()},
     'mcap_bytes':sum(x.stat().st_size for x in (p/'bag_unified').glob('*.mcap')),
     'root_sha256':assets['root_sha256'],'root_unchanged':True,'calibration_validated':True,
     'frame_contract_version':CONTRACT['frame_contract_version'],'swing_zero_validated_every_group':True,
     'tf_matrix_max_abs_error':max(transform_errors),
     'writer_digests_match':True,'world_fixed_max_error':max(fixed_errors,default=0),
     'root_mount_max_error':max(root_mount_errors,default=0),
     'source_root_max_error_m':max(root_errors) if root_errors else None,
     'source_quaternion_max_error':max(quat_errors) if quat_errors else None,
     'source_joint_max_error_rad':max(joint_errors) if joint_errors else None,
     'timings':{k:v for k,v in report['timings'].items() if k.endswith('_total_s') or k=='preview_errors'}}
print('VALIDATION_JSON='+json.dumps(out))
