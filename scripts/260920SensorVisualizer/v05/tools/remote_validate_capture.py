"""Validate only owned test tasks using the already installed ROS/Pillow stack."""
import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05')
child=r'''
import io,json,sys,math
from collections import Counter
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from PIL import Image
p=Path(sys.argv[1]);registry=json.loads((p/'sensor_registry.json').read_text())
sys.path.insert(0,'/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05')
from sensor_visualizer_v05.trajectory import Trajectory
job=json.loads((p/'job_spec.json').read_text());source=None
if job['replay']['mode']=='offline':source=Trajectory.load(job['replay']['trajectory'])
report=json.loads((p/'writer_report.json').read_text());assert report['state']=='finished',report
r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=str(p/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
types={x.name:get_message(x.type) for x in r.get_all_topics_and_types()}
counts=Counter();frames=[];stamps=set();image_shapes={};point_counts={};tf_count=set();cameras={c['id']:c for c in registry['cameras']}
roots={};joints={};root_errors=[];joint_errors=[];quat_errors=[]
def stamp(s):return s.sec*10**9+s.nanosec
while r.has_next():
    topic,data,t=r.read_next();m=deserialize_message(data,types[topic]);counts[topic]+=1
    if hasattr(m,'header'):assert stamp(m.header.stamp)==t,(topic,t)
    if topic=='/clock':assert stamp(m.clock)==t
    if topic=='/excavator/root_pose':roots[t]=m.pose
    if topic=='/joint_states':joints[t]=dict(zip(m.name,m.position))
    if topic=='/tf':
        assert all(stamp(v.header.stamp)==t for v in m.transforms)
        children=[v.child_frame_id for v in m.transforms];assert len(children)==len(set(children));tf_count.add(len(children))
    if topic.endswith('/image_raw/compressed'):
        cid=topic.split('/')[2];image=Image.open(io.BytesIO(bytes(m.data)));image.load()
        expected=cameras[cid]['calibration'];assert image.size==(expected['width'],expected['height'])
        assert image.mode=='RGB';image_shapes[cid]=[image.width,image.height]
        assert any(hi-lo>2 for lo,hi in image.getextrema()),'Uniform image frame'
    if topic.endswith('/camera_info'):assert m.distortion_model=='equidistant' and len(m.d)==4
    if hasattr(m,'point_step'):assert m.point_step==12 and m.row_step==m.width*12 and len(m.data)==m.row_step;point_counts.setdefault(topic,[]).append(m.width)
    if topic=='/sensor_visualizer/frame_index':
        frame=json.loads(m.data);assert frame['simulation_time_ns']==t;assert 'trajectory' in frame
        assert abs(frame['trajectory']['time_quantization_error_s'])<=1/120+1e-6
        frames.append(frame);stamps.add(t)
assert len(frames)==report['groups']==len(stamps)
assert tf_count=={len(registry['lidars'])+len(registry['cameras'])+2}
for topic in types:
    if topic not in ('/sensor_visualizer/run_metadata','/sensor_visualizer/camera_metadata'):assert counts[topic]==len(frames),(topic,counts[topic])
assert [x['group_id'] for x in frames]==list(range(len(frames)))
assert all(b['simulation_time_ns']>a['simulation_time_ns'] for a,b in zip(frames,frames[1:]))
if source:
    for frame in frames:
        t=frame['simulation_time_ns'];expected=source.sample(frame['trajectory']['trajectory_time_s']);actual=roots[t]
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
     'source_root_max_error_m':max(root_errors) if root_errors else None,
     'source_quaternion_max_error':max(quat_errors) if quat_errors else None,
     'source_joint_max_error_rad':max(joint_errors) if joint_errors else None,
     'timings':{k:v for k,v in report['timings'].items() if k.endswith('_total_s') or k=='preview_errors'}}
print('VALIDATION_JSON='+json.dumps(out))
'''
results=[]
allowed=('offline_task.json','live_latest_task.json','live_complete_task.json','soak_task.json')
selected=os.environ.get('SV05_VALIDATE_TRACKS')
tracks=selected.split(',') if selected else allowed
assert all(name in allowed for name in tracks),'Unknown owned test track'
for filename in tracks:
    track=root/'reports/native_owner'/filename
    if not track.exists():continue
    info=json.loads(track.read_text());status=json.loads((Path(info['directory'])/'status.json').read_text())
    if not status.get('session'):continue
    session=Path(status['session'])
    if not (session/'writer_report.json').exists():continue
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
    p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -u "$@"','sv05-validate','-c',child,str(session)],env=env,capture_output=True,text=True,timeout=180)
    if p.returncode:raise RuntimeError(p.stdout[-1000:]+p.stderr[-4000:])
    value=json.loads(p.stdout.split('VALIDATION_JSON=')[-1]);value['mode']=info['mode'];results.append(value)
    label='soak_100' if filename=='soak_task.json' else info['mode']
    (root/'reports/native_owner'/('validation_'+label+'.json')).write_text(json.dumps(value,indent=2))
print(json.dumps([{k:v for k,v in r.items() if k not in ('source_times','native_times_ns','point_count_ranges')} for r in results]))
