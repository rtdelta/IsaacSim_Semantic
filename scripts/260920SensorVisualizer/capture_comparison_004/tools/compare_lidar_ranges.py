"""Post-run first-target MCAP XYZ diagnostics; no renderer or data modification."""
import csv,json,sys
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from decode_case import stamp

def read(p):return json.loads(p.read_text())
def run(root):
 root=Path(root);rows=[];missing=[]
 for cid in ('01_v06_gated','02_v06_keepalive','05_native_frozen_rt_default'):
  for repeat in (1,2,3):
   case=root/cid/f'round_{repeat:02d}';d=read(case/'decoded.json')
   index=list(csv.DictReader((case/'frames.csv').open()));target=int(next(r['group_stamp_ns'] for r in index if int(r['group'])==0))
   reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=d['bag_path'],storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
   topics=[t.name for t in reader.get_all_topics_and_types() if t.name.endswith('/points')];reader.set_filter(rosbag2_py.StorageFilter(topics=topics))
   cls=get_message('sensor_msgs/msg/PointCloud2');seen=set()
   while reader.has_next():
    topic,data,record_stamp=reader.read_next();m=deserialize_message(data,cls)
    if topic in seen or abs(stamp(m.header.stamp)-target)>2:continue
    fields={f.name:f for f in m.fields};coords=[]
    for axis in ('x','y','z'):
     f=fields[axis]
     if f.datatype!=7 or f.count!=1:raise RuntimeError('Expected FLOAT32 XYZ')
     coords.append(np.ndarray((m.height,m.width),dtype=('>' if m.is_bigendian else '<')+'f4',buffer=m.data,offset=f.offset,strides=(m.row_step,m.point_step)).reshape(-1).astype(np.float64))
    xyz=np.stack(coords,axis=1);finite=np.isfinite(xyz).all(axis=1);good=xyz[finite];distance=np.linalg.norm(good,axis=1);zero=(good==0).all(axis=1)
    row={'id':cid,'round':repeat,'group':0,'topic':topic,'frame_id':m.header.frame_id,'header_stamp_ns':stamp(m.header.stamp),
     'points':len(xyz),'finite_points':int(finite.sum()),'zero_xyz':int(zero.sum()),
     **{f'count_distance_le_{v:g}m':int((distance<=v).sum()) for v in (0.1,0.5,1,2,5,10,60)},
     **{f'distance_p{q:g}_m':float(np.percentile(distance,q)) if len(distance) else None for q in (0,1,5,50,95,99,100)}}
    rows.append(row);seen.add(topic)
    if len(seen)==len(topics):break
   if set(topics)-seen:missing.append({'id':cid,'round':repeat,'topics':sorted(set(topics)-seen)})
 out=root/'analysis';out.mkdir(exist_ok=True)
 with (out/'lidar_ranges.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 result={'rows':rows,'missing':missing,'limits':['First MCAP message at group 0 only; duplicate publications not merged.','Distances calculated from message XYZ, assuming the SENSOR frame declared by the source pipeline.','No nearest-neighbor correspondence or surface-label ground truth; counts alone do not prove geometry correctness.']}
 (out/'lidar_ranges.json').write_text(json.dumps(result,indent=2));print(json.dumps({'sensor_samples':len(rows),'missing':missing}))
 return 2 if missing else 0
if __name__=='__main__':raise SystemExit(run(sys.argv[1]))
