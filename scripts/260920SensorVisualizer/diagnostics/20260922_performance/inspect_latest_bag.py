"""Read and hash the latest completed recording; do not alter source data."""
import hashlib, json, os, subprocess
from pathlib import Path

root=Path('/root/gpufree-data/semantic/output/sensor_visualizer')
candidates=[p for p in root.iterdir() if p.is_dir() and (p/'bag/metadata.yaml').is_file() and list((p/'bag').glob('*.mcap'))]
folder=max(candidates,key=lambda p:max(f.stat().st_mtime for f in (p/'bag').glob('*.mcap')))
files=list((folder/'bag').glob('*.mcap'))+[folder/'bag/metadata.yaml']
files += [folder/n for n in ('session.json','capture_summary.json') if (folder/n).is_file()]
manifest=[]
for p in files:
    before=p.stat();h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    after=p.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Recording file still changing')
    manifest.append(dict(relative=p.relative_to(folder).as_posix(),bytes=after.st_size,mtime_ns=after.st_mtime_ns,sha256=h.hexdigest()))

code=r'''
import collections,json,sys
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
folder=Path(sys.argv[1])
reader=rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=str(folder/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
topics={t.name:t.type for t in reader.get_all_topics_and_types()}
classes={k:get_message(v) for k,v in topics.items()}
rows={k:dict(type=v,count=0,first_bag_ns=None,last_bag_ns=None,header_min_ns=None,header_max_ns=None) for k,v in topics.items()}
tf_edges={};clock_range=[]
def ns(s):return s.sec*10**9+s.nanosec
while reader.has_next():
    topic,data,stamp=reader.read_next();row=rows[topic]
    row['count']+=1
    if row['first_bag_ns'] is None:row['first_bag_ns']=stamp
    row['last_bag_ns']=stamp
    msg=deserialize_message(data,classes[topic])
    if hasattr(msg,'header'):
        t=ns(msg.header.stamp)
        row['header_min_ns']=t if row['header_min_ns'] is None else min(t,row['header_min_ns'])
        row['header_max_ns']=t if row['header_max_ns'] is None else max(t,row['header_max_ns'])
        row['frame_id']=msg.header.frame_id
    if row['type']=='sensor_msgs/msg/PointCloud2':
        n=msg.width*msg.height
        row['point_min']=min(row.get('point_min',n),n);row['point_max']=max(row.get('point_max',n),n)
        row['point_total']=row.get('point_total',0)+n
        if row['count']==1:
            row.update(width=msg.width,height=msg.height,point_step=msg.point_step,row_step=msg.row_step,
                is_bigendian=msg.is_bigendian,is_dense=msg.is_dense,
                fields=[dict(name=f.name,offset=f.offset,datatype=f.datatype,count=f.count) for f in msg.fields])
    elif topic in ('/tf','/tf_static'):
        row['transform_count']=row.get('transform_count',0)+len(msg.transforms)
        for t in msg.transforms:
            key=t.header.frame_id+' -> '+t.child_frame_id
            edge=tf_edges.setdefault(key,dict(topic=topic,count=0,first_ns=ns(t.header.stamp),last_ns=ns(t.header.stamp)))
            edge['count']+=1;edge['last_ns']=ns(t.header.stamp)
    elif topic=='/clock':
        t=ns(msg.clock)
        if not clock_range:clock_range=[t,t]
        else:clock_range[1]=t
    elif row['type']=='sensor_msgs/msg/JointState' and row['count']==1:
        row['joint_names']=list(msg.name);row['first_position']=list(msg.position)
        row['velocity_length']=len(msg.velocity);row['effort_length']=len(msg.effort)
    elif row['type']=='geometry_msgs/msg/PoseStamped' and row['count']==1:
        row['first_pose']=dict(position=[msg.pose.position.x,msg.pose.position.y,msg.pose.position.z],
           quaternion_xyzw=[msg.pose.orientation.x,msg.pose.orientation.y,msg.pose.orientation.z,msg.pose.orientation.w])
result=dict(topics=rows,tf_edges=tf_edges,clock_range_ns=clock_range,
            total_messages=sum(r['count'] for r in rows.values()))
if (folder/'session.json').is_file():
    s=json.loads((folder/'session.json').read_text());result['session_top_level_keys']=list(s)
    result['session_metadata']={k:s[k] for k in ('started_at','stopped_at','created_at') if k in s}
    scene=s.get('scene',{})
    if isinstance(scene,dict):
        result['scene_keys']=list(scene)
        result['scene_summary']={k:scene[k] for k in ('stage_identifier','stage','simulation_pacing','control_mode') if k in scene}
if (folder/'capture_summary.json').is_file():result['capture_summary']=json.loads((folder/'capture_summary.json').read_text())
result['camera_calibrations']={p.parent.name:json.loads(p.read_text()) for p in folder.glob('cameras/*/calibration.json')}
print(json.dumps(result))
'''
env=dict(os.environ)
for k in ('LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(k,None)
r=subprocess.run(['/bin/bash','--noprofile','--norc','-c',
    'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B - "$1"','bag-inspect',str(folder)],
    input=code,env=env,capture_output=True,text=True,timeout=45)
print(json.dumps(dict(session=str(folder),files=manifest,inspection_exit=r.returncode,stdout=r.stdout,stderr=r.stderr)))
raise SystemExit(r.returncode)
