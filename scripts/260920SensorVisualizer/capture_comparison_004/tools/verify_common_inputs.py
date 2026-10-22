"""Post-run comparison of actual MCAP TFs for every sensor, plus manifest parameters."""
import csv,json,sys
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from decode_case import stamp,matrix

def read(p):return json.loads(p.read_text())
def canonical(v):
 if isinstance(v,str):
  if v in ('True','False'):return v=='True'
  try:return float(v)
  except ValueError:return v
 return v
def extract(case):
 cfg=read(case/'config.json');r=read(case/'capture/result.json');legacy=cfg['family']=='v06';d=read(case/'decoded.json');bag=Path(d['bag_path'])
 if legacy:
  registry=read(Path(r['capture']['session'])/'sensor_registry.json');sensors={('camera' if kind=='cameras' else 'lidar')+'/'+s['id']:s for kind in ('cameras','lidars') for s in registry[kind]}
  meta=read(case/'frame_metadata.json')
  for key,s in sensors.items():
   if key.startswith('camera/'):
    info=next((v.get('camera_info') for k,v in meta.items() if k.endswith('/'+s['id']) and v.get('camera_info')),None)
    if not info:raise RuntimeError('Camera optical frame missing in actual MCAP metadata: '+key)
    s['frame_id']=info['frame_id']
 else:sensors={s['kind']+'/'+s['id']:s for s in read(case/'capture/sensor_manifest.json')['sensors']}
 graph={};reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('',''));reader.set_filter(rosbag2_py.StorageFilter(topics=['/tf']))
 cls=get_message('tf2_msgs/msg/TFMessage')
 while reader.has_next():
  topic,data,t=reader.read_next();m=deserialize_message(data,cls)
  for tr in m.transforms:
   p=tr.transform.translation;q=tr.transform.rotation
   graph.setdefault(stamp(tr.header.stamp),{})[tr.child_frame_id]=(tr.header.frame_id,matrix([p.x,p.y,p.z],[q.x,q.y,q.z,q.w]))
 index=list(csv.DictReader((case/'frames.csv').open()));groups={int(x['group']):int(x['group_stamp_ns']) for x in index};worlds={}
 for gid,t in groups.items():
  g={}
  for k,v in graph.items():
   if abs(k-t)<=2:g.update(v)
  def world(frame,seen=None):
   if frame=='world':return np.eye(4)
   seen=set() if seen is None else seen
   if frame in seen or frame not in g:return None
   seen.add(frame);parent,m=g[frame];w=world(parent,seen);return None if w is None else w@m
  for key,s in sensors.items():
   # Both families expose a camera optical frame in their registry.
   frame=s.get('optical_frame_id',s['frame_id']);w=world(frame)
   if w is not None:worlds[str(gid)+'/'+key]=w
 return {'capture_valid':d['all_expected_images_valid'],'sensors':sensors,'worlds':worlds,'group_stamps':groups}
def main(root):
 root=Path(root);p=read(root/'progress.json');all_cases={}
 for c in p['completed_cases']:
  case=root/c['id']/f'round_{c["round"]:02d}'
  if (case/'decoded.json').exists():all_cases[(c['id'],c['round'])]=extract(case)
 rows=[]
 for (cid,repeat),a in all_cases.items():
  b=all_cases.get(('05_native_frozen_rt_default',repeat))
  if b is None:continue
  missing=[];diff=[];errors=[]
  for key,s in a['sensors'].items():
   want=b['sensors'].get(key)
   if not want:missing.append(key);continue
   for name,value in s.get('parameters',{}).items():
    if name in want.get('parameters',{}) and canonical(value)!=canonical(want['parameters'][name]):diff.append({'sensor':key,'parameter':name,'actual':value,'reference':want['parameters'][name]})
   for gid in a['group_stamps']:
    w=a['worlds'].get(str(gid)+'/'+key);v=b['worlds'].get(str(gid)+'/'+key)
    if w is None or v is None:missing.append(str(gid)+'/'+key)
    else:errors.append({'group':gid,'sensor':key,'world_matrix_max_abs_error':float(np.max(np.abs(w-v)))})
  maxerr=max((r['world_matrix_max_abs_error'] for r in errors),default=None)
  rows.append({'id':cid,'round':repeat,'capture_valid':a['capture_valid'],'sensor_count':len(a['sensors']),'compared_sensor_groups':len(errors),'max_world_matrix_error':maxerr,'missing':missing,'parameter_differences':diff,'numeric_input_alignment_passed':not missing and not diff and maxerr is not None and maxerr<=2e-3,'pose_errors':errors,'target_stamps_ns':a['group_stamps']})
 out=root/'analysis';out.mkdir(exist_ok=True)
 result={'cases':rows,'all_valid_captures_input_aligned':all(r['numeric_input_alignment_passed'] for r in rows if r['capture_valid']),
  'limits':['Actual TF at each physical target stamp, not a proof of a failed capture becoming valid.','Only parameters present in both manifests compared; extra fields remain visible in originals.','All poses static; different native time grids are retained, not rewritten.']}
 (out/'common_inputs.json').write_text(json.dumps(result,indent=2));print(json.dumps({'cases':len(rows),'valid_captures_input_aligned':result['all_valid_captures_input_aligned'],'failures':[{'id':r['id'],'round':r['round'],'missing':r['missing'][:5],'max_error':r['max_world_matrix_error']} for r in rows if r['capture_valid'] and not r['numeric_input_alignment_passed']]}))
 return 0 if result['all_valid_captures_input_aligned'] else 2
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
