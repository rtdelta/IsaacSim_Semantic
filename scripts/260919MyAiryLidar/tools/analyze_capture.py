"""Read actual ROS 2 MCAP messages, verify timing/TF, export one frame per sensor."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import sys
import numpy as np
import rosbag2_py
import rclpy
from rclpy.duration import Duration
from rclpy.time import Time
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from tf2_ros import Buffer

p = argparse.ArgumentParser()
p.add_argument('job', type=Path)
p.add_argument('--visualizer', type=Path, default=Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer'))
a = p.parse_args()
sys.path[:0] = [str(a.visualizer), str(a.visualizer/'mcap_unpacker')]
from lidar_visualizer.reference_frames import quaternion_matrix
from mcap_unpack.cloud import decode_xyz, transform_xyz, write_pcd


def stamp(t): return int(t.sec)*1_000_000_000+int(t.nanosec)


capture = json.loads((a.job/'capture_result.json').read_text())
assert capture['passed'], capture.get('error')
session = Path(capture['session'])
manifest = json.loads((session/'session.json').read_text())
out = session/'inspection'
out.mkdir(exist_ok=False)
expected = {s['topic']:s for s in manifest['sensors']}
assert len(expected) == 13
rclpy.init(args=[])
tf = Buffer(cache_time=Duration(seconds=120))


def reader():
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(session/'bag'),storage_id='mcap'), rosbag2_py.ConverterOptions('',''))
    return r


r = reader()
types = {t.name:get_message(t.type) for t in r.get_all_topics_and_types()}
counts = Counter(); edges = Counter(); clocks=[]; joints=[]; roots=[]
for_read = {'/tf','/tf_static','/clock','/joint_states','/excavator/root_pose'}
while r.has_next():
    topic, data, recorded = r.read_next(); counts[topic]+=1
    if topic not in for_read: continue
    msg = deserialize_message(data,types[topic])
    if topic in ('/tf','/tf_static'):
        for t in msg.transforms:
            edges[(t.header.frame_id,t.child_frame_id)]+=1
            (tf.set_transform_static if topic=='/tf_static' else tf.set_transform)(t,'recorded_bag')
    elif topic=='/clock': clocks.append(stamp(msg.clock))
    elif topic=='/joint_states': joints.append(list(msg.position))
    elif topic=='/excavator/root_pose':
        v,q=msg.pose.position,msg.pose.orientation
        roots.append([v.x,v.y,v.z,q.x,q.y,q.z,q.w])
del r
report = dict(passed=False, session=str(session), counts=dict(counts), sensors={},
              tf_edges=[dict(parent=k[0],child=k[1],messages=v) for k,v in sorted(edges.items())],
              exports='One nonempty frame per sensor in local coordinates and world; binary XYZ PCD')
issues=[]
if len(clocks)<2 or np.any(np.diff(clocks)<=0): issues.append('Clock is missing or non-monotonic')
if len(joints)<2 or np.max(np.ptp(np.asarray(joints),axis=0))>2e-5: issues.append('Joint states missing or moving')
if len(roots)<2 or np.max(np.ptp(np.asarray(roots),axis=0))>2e-5: issues.append('Root pose missing or moving')
report['joint_excursion_rad'] = np.ptp(np.asarray(joints),axis=0).tolist() if joints else None
report['root_excursion'] = np.ptp(np.asarray(roots),axis=0).tolist() if roots else None
W,H,S='world',manifest['scene']['reference_frames']['horizontal'],manifest['root_frame']
expected_edges={(W,H),(H,S)}|{(S,s['frame_id']) for s in expected.values()}
if set(edges)!=expected_edges: issues.append('TF edges do not match expected hierarchy')
stats={topic:dict(stamps=[],counts=[],nonfinite=0,tf_errors=0,max_tf_matrix_error=0.,
                  boundary_adjustments=0,ranges=[],minimum_z=float('inf'),fields=[]) for topic in expected}
samples={}; rows=[]; r=reader()
while r.has_next():
    topic,data,recorded=r.read_next()
    if topic not in expected: continue
    msg=deserialize_message(data,types[topic]); xyz=decode_xyz(msg); ns=stamp(msg.header.stamp)
    st=stats[topic];st['stamps'].append(ns);st['counts'].append(len(xyz))
    st['fields']=[f.name for f in msg.fields]
    finite=np.isfinite(xyz).all(axis=1);st['nonfinite']+=int((~finite).sum())
    points=xyz[finite]
    if msg.header.frame_id!=expected[topic]['frame_id']:issues.append('Wrong frame_id: '+topic)
    radius=np.linalg.norm(points,axis=1)
    if len(points):
        st['ranges'].append([float(radius.min()),float(radius.max())])
        st['minimum_z']=min(st['minimum_z'],float(points[:,2].min()))
    transform=None
    for offset in (0,1,-1):
        try:
            transform=tf.lookup_transform(W,msg.header.frame_id,Time(nanoseconds=ns+offset))
            if offset:st['boundary_adjustments']+=1
            break
        except Exception: pass
    if transform is None:st['tf_errors']+=1
    else:
        t,q=transform.transform.translation,transform.transform.rotation
        translation=[t.x,t.y,t.z];quaternion=[q.x,q.y,q.z,q.w]
        matrix=np.eye(4);matrix[:3,:3]=quaternion_matrix(quaternion);matrix[:3,3]=translation
        error=float(np.max(np.abs(matrix-np.asarray(capture['sensor_world_matrices'][msg.header.frame_id]))))
        st['max_tf_matrix_error']=max(st['max_tf_matrix_error'],error)
        if topic not in samples and len(points):
            world=transform_xyz(xyz,translation,quaternion)
            folder=out/expected[topic]['id'];folder.mkdir()
            write_pcd(folder/'local.pcd',xyz,msg.width,msg.height)
            write_pcd(folder/'world.pcd',world,msg.width,msg.height)
            samples[topic]=dict(world=world[finite],matrix=matrix,stamp_ns=ns)
            (folder/'frame.json').write_text(json.dumps(dict(topic=topic,stamp_ns=ns,record_time_ns=recorded,
                source_frame=msg.header.frame_id,target_frame=W,points=len(xyz),world_from_sensor=matrix.tolist()),indent=2)+'\n')
    rows.append(dict(topic=topic,stamp_ns=ns,record_time_ns=recorded,frame_id=msg.header.frame_id,
                     points=len(xyz),nonfinite=int((~finite).sum()),tf_available=transform is not None))
del r
for topic,st in stats.items():
    times=np.asarray(st['stamps'],dtype=np.int64); intervals=np.diff(times)/1e9
    rate=(len(times)-1)/((times[-1]-times[0])/1e9) if len(times)>1 and times[-1]>times[0] else 0
    ranges=np.asarray(st['ranges'])
    result=dict(messages=len(times),points_min=min(st['counts'],default=0),points_max=max(st['counts'],default=0),
        frequency_hz=rate,stamp_first_ns=int(times[0]) if len(times) else None,
        stamp_last_ns=int(times[-1]) if len(times) else None,
        period_min_s=float(intervals.min()) if len(intervals) else None,
        period_max_s=float(intervals.max()) if len(intervals) else None,
        nonfinite_points=st['nonfinite'],tf_lookup_failures=st['tf_errors'],
        tf_boundary_adjustments_1ns=st['boundary_adjustments'],max_tf_matrix_error=st['max_tf_matrix_error'],
        range_min_m=float(ranges[:,0].min()) if len(ranges) else None,
        range_max_m=float(ranges[:,1].max()) if len(ranges) else None,
        minimum_local_z=st['minimum_z'] if st['counts'] else None,fields=st['fields'])
    report['sensors'][topic]=result
    if len(times)<27 or not 9.9<=rate<=10.01 or np.any(intervals<=0) or np.any(intervals>.101):
        issues.append('Missing frames or unexpected cadence: '+topic)
    if not st['counts'] or min(st['counts'])==0 or st['nonfinite'] or st['tf_errors'] or st['max_tf_matrix_error']>2e-4:
        issues.append('Invalid points or TF: '+topic)
    if '/MyAiry_' in topic and st['minimum_z']<-.001:issues.append('Point outside MyAiry local hemisphere: '+topic)
report['clock_span_seconds']=(max(clocks)-min(clocks))/1e9 if clocks else None
report['total_cloud_frames']=sum(len(st['stamps']) for st in stats.values())
report['total_cloud_points']=sum(sum(st['counts']) for st in stats.values())
report['issues']=issues;report['passed']=not issues
with (out/'frames.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
# A static inspection figure; PCD files retain all points, the view shows +/-12 m.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
origin=np.asarray(capture['initial_state']['root_position'])
fig,axes=plt.subplots(3,2,figsize=(13,15))
for col,family in enumerate(('MyAiry_','MyNZ3_')):
    for color,(topic,sample) in zip(plt.cm.tab10.colors,[(t,s) for t,s in samples.items() if family in t]):
        points=sample['world']-origin
        points=points[(np.abs(points)<12).all(axis=1)]
        points=points[::max(1,len(points)//16000)]
        position=sample['matrix'][:3,3]-origin; direction=sample['matrix'][:3,2]
        for row,(i,j) in enumerate(((0,1),(0,2),(1,2))):
            ax=axes[row,col];ax.scatter(points[:,i],points[:,j],s=.15,color=color,alpha=.65,rasterized=True)
            ax.scatter(position[i],position[j],s=22,color=color,marker='^',label=expected[topic]['id'])
            ax.arrow(position[i],position[j],direction[i],direction[j],color=color,width=.025,length_includes_head=True)
    for row,(i,j) in enumerate(((0,1),(0,2),(1,2))):
        ax=axes[row,col];ax.set(xlim=(-12,12),ylim=(-12,12),aspect='equal',
            xlabel='XYZ'[i]+' (m)',ylabel='XYZ'[j]+' (m)',title=family.rstrip('_')+' / '+'XYZ'[i]+'XYZ'[j])
        ax.grid(alpha=.2)
    axes[0,col].legend(fontsize=7,loc='upper right')
fig.suptitle('Stage 12: first recorded frame per sensor; world axes, origin at swing reference\n'
             'View cropped to +/-12 m; arrows show sensor local +Z. Full coordinates are retained in PCD.')
fig.tight_layout(rect=(0,0,1,.96));fig.savefig(out/'pointcloud_overview.png',dpi=160);plt.close(fig)
print(json.dumps(report,indent=2),flush=True)
rclpy.shutdown()
raise SystemExit(0 if report['passed'] else 1)
