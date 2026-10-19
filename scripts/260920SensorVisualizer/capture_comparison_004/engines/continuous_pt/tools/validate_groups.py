"""Strict post-run group validation: native stamps AND matching current RGB bytes."""
import collections,hashlib,json,sys,math
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

def main(directory):
 out=Path(directory);groups=[json.loads(l) for l in (out/'groups.jsonl').read_text().splitlines()]
 sensors=json.loads((out/'sensor_manifest.json').read_text())['sensors'];mapping={s['topic']:s for s in sensors}
 expected=set(mapping)|{s['info_topic'] for s in sensors if s['kind']=='camera'}|{'/joint_states'}
 reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(out/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
 types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()};by_stamp=collections.defaultdict(collections.Counter)
 hashes=collections.defaultdict(lambda:collections.defaultdict(set));joints=collections.defaultdict(list);bounds=collections.defaultdict(lambda:[None,None]);tf_stamps=collections.Counter();transforms=collections.defaultdict(dict);xyz_hashes=collections.defaultdict(lambda:collections.defaultdict(set))
 while reader.has_next():
  topic,data,t=reader.read_next();msg=deserialize_message(data,types[topic]);h=getattr(msg,'header',None)
  if h:
   stamp=h.stamp.sec*10**9+h.stamp.nanosec;by_stamp[stamp][topic]+=1
   limits=bounds[topic];limits[0]=stamp if limits[0] is None else min(limits[0],stamp);limits[1]=stamp if limits[1] is None else max(limits[1],stamp)
   if topic in mapping and mapping[topic]['kind']=='camera':
    channels=3 if msg.encoding=='rgb8' else 4
    rgb=np.ndarray((msg.height,msg.width,channels),dtype='u1',buffer=msg.data,strides=(msg.step,channels,1))[:,:,:3]
    hashes[stamp][topic].add(hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest())
   if topic in mapping and mapping[topic]['kind']=='lidar':
    fields={f.name:f for f in msg.fields};xyz=np.empty((msg.height,msg.width,3),dtype='<f4')
    for i,name in enumerate(('x','y','z')):
     f=fields[name]
     if f.datatype!=7:raise RuntimeError('Unsupported native XYZ field '+name)
     xyz[:,:,i]=np.ndarray((msg.height,msg.width),dtype='>f4' if msg.is_bigendian else '<f4',buffer=msg.data,offset=f.offset,strides=(msg.row_step,msg.point_step))
    xyz_hashes[stamp][topic].add(hashlib.sha256(xyz.tobytes()).hexdigest())
   if topic=='/joint_states':joints[stamp].append(dict(zip(msg.name,msg.position)))
  elif topic=='/tf':
   for tr in msg.transforms:
    stamp=tr.header.stamp.sec*10**9+tr.header.stamp.nanosec;tf_stamps[stamp]+=1
    t=tr.transform.translation;q=tr.transform.rotation
    transforms[stamp][tr.child_frame_id]={'parent':tr.header.frame_id,'translation':[t.x,t.y,t.z],'quaternion_xyzw':[q.x,q.y,q.z,q.w]}
 results=[];errors=[]
 for g in groups:
  stamp=round(g['native_time_s']*1e9);candidate=[k for k in by_stamp if abs(k-stamp)<=2]
  counts=collections.Counter();actual_hashes=collections.defaultdict(set)
  for k in candidate:
   counts.update(by_stamp[k])
   for topic,values in hashes[k].items():actual_hashes[topic].update(values)
  missing=sorted(expected-set(counts));mismatch=[];lidar_mismatch=[]
  for topic,im in g['images'].items():
   if im['sha256'] not in actual_hashes[topic]:mismatch.append(topic)
   if im['camera_pose_max_abs_error']>2e-3:errors.append(f"Group {g['group']} rendered camera pose mismatch {topic}")
  for topic,point in g.get('lidars',{}).items():
   if 'observation_error' in point:errors.append(f"Group {g['group']} native LiDAR observer failed {topic}");continue
   actual=set().union(*(xyz_hashes[k][topic] for k in candidate))
   if point['sha256_xyz'] not in actual:lidar_mismatch.append(topic)
   if point['render_pose_max_abs_error']>2e-3:errors.append(f"Group {g['group']} rendered LiDAR pose mismatch {topic}")
  if lidar_mismatch:errors.append(f"Group {g['group']} MCAP/current XYZ hash mismatch: {lidar_mismatch}")
  if missing:errors.append(f"Group {g['group']} missing fresh messages: {missing}")
  if mismatch:errors.append(f"Group {g['group']} MCAP/current RGB hash mismatch: {mismatch}")
  found=[j for k in candidate for j in joints[k]]
  joint_error=min((max(abs(j.get(n,float('inf'))-v) for n,v in g['joints_rad'].items()) for j in found),default=float('inf'))
  if joint_error>1e-3:errors.append(f"Group {g['group']} joint state mismatch")
  if not any(abs(k-stamp)<=2 for k in tf_stamps):errors.append(f"Group {g['group']} missing TF at frozen stamp")
  actual_tf={child:tr for k,values in transforms.items() if abs(k-stamp)<=2 for child,tr in values.items()};tf_errors=[]
  for child,want in g.get('expected_tf',{}).items():
   got=actual_tf.get(child)
   if got is None or got['parent']!=want['parent'] or max(abs(x-y) for x,y in zip(got['translation'],want['translation']))>2e-3 or abs(np.dot(got['quaternion_xyzw'],want['quaternion_xyzw']))<1-2e-5:tf_errors.append(child)
  if tf_errors:errors.append(f"Group {g['group']} numeric TF mismatch: {tf_errors}")
  results.append({'group':g['group'],'case':g['case'],'expected_stamp_ns':stamp,'missing':missing,'matching_image_bytes':not mismatch,'matching_xyz_bytes':not lidar_mismatch,'tf_errors':tf_errors,'counts':dict(counts),'joint_error_rad':joint_error})
 if not groups:errors.append('No completed groups')
 if len({round(g['native_time_s']*1e9) for g in groups})!=len(groups):errors.append('Cross-group native stamps are not unique')
 spec=json.loads((out/'spec.json').read_text())
 budget_results=[]
 if spec.get('experiment')=='continuous_pt':
  from PIL import Image
  if len(groups)!=spec['measure_frames']:errors.append('Incomplete requested continuous logical frame count')
  for g in groups:
   total=spec['pt_total_spp'];spp=spec['pt_spp'];s=g['settings'];png_errors=[]
   budget=(g.get('sdk_subframes_at_capture')==total//spp and g.get('accumulation_reset') is True and
    s.get('/rtx/rendermode')=='PathTracing' and s.get('/rtx/pathtracing/totalSpp')==total and
    s.get('/rtx/pathtracing/spp')==spp and s.get('/rtx/pathtracing/adaptiveSampling/enabled') is False and
    s.get('/rtx/resetPtAccumOnAnimTimeChange') is True)
   if not budget:errors.append(f"Group {g['group']} per-image high-SPP completion not verified")
   for sensor in sensors:
    if sensor['kind']!='camera' or not spec.get('extra_capture_png',True):continue
    paths=[p for p in (out/'native_basic_images').rglob(f"rgb_{g['group']:04d}.png") if any('NativeBaseline_'+sensor['id'] in part for part in p.parts)]
    if len(paths)!=1:png_errors.append(sensor['id']+': expected one native BasicWriter reference image');continue
    rgb=np.asarray(Image.open(paths[0]).convert('RGB'))
    if hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest()!=g['images'][sensor['topic']]['sha256']:
     png_errors.append(sensor['id']+': BasicWriter/current-observer bytes differ')
   if png_errors:errors.append(f"Group {g['group']} native final-capture PNG mismatch {png_errors}")
   budget_results.append({'group':g['group'],'budget_completion':budget,'basic_writer_image_errors':png_errors})
 result={'ok':not errors,'errors':errors,'groups':results,'topic_stamp_bounds':dict(bounds),
  'limits':['Image byte equality ties MCAP to observed output, not real-world ground truth.','Requested PT sample settings do not prove hardware executed exactly that many rays.','Repeated headers within a frozen group are expected; cross-group stamps must differ.']}
 result['continuous_pt_budget_validation']=budget_results
 (out/'group_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps({'ok':result['ok'],'groups':len(groups),'errors':errors}));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
