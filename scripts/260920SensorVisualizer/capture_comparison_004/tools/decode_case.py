"""ROS-standard MCAP decoder. Runs after capture; never repairs message timestamps."""
import collections,csv,hashlib,io,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
CAMERAS=('front','back','left','right')
def stamp(s):return s.sec*10**9+s.nanosec
def cid(topic):return topic.split('/')[2].removeprefix('fisheye_')
def matrix(p,q):
 x,y,z,w=q;m=np.eye(4);m[:3,3]=p;m[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]];return m
def decode(case):
 case=Path(case);cfg=json.loads((case/'config.json').read_text());capture=case/'capture';r=json.loads((capture/'result.json').read_text());legacy=cfg['family']=='v06'
 if legacy:
  session=Path(r['capture']['session']);bag=session/'bag_unified';native_groups=[];capture_ok=r.get('exit_code')==0 and r.get('validation',{}).get('passed',False)
 else:
  session=capture;bag=session/'bag';native_groups=[json.loads(l) for l in (capture/'groups.jsonl').read_text().splitlines()] if (capture/'groups.jsonl').exists() else [json.loads(l) for l in (capture/'frames.jsonl').read_text().splitlines()]
  capture_ok=r.get('state')=='completed'
 if not bag.exists():raise RuntimeError('No completed bag to decode')
 def reader():
  x=rosbag2_py.SequentialReader();x.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('',''));return x,{t.name:get_message(t.type) for t in x.get_all_topics_and_types()}
 core=collections.defaultdict(collections.Counter);stats=collections.defaultdict(lambda:{'messages':0,'cdr_bytes':0});tf=collections.defaultdict(dict);joint={};cal={};frames=[];cloud_counts=collections.defaultdict(list)
 x,types=reader()
 while x.has_next():
  topic,data,bt=x.read_next();stats[topic]['messages']+=1;stats[topic]['cdr_bytes']+=len(data)
  if topic.endswith('/image_raw') or topic.endswith('/image_raw/compressed'):
   # Payload is decoded on the second pass, only for experiment target frames.
   m=deserialize_message(data,types[topic]);core[stamp(m.header.stamp)][topic]+=1;continue
  m=deserialize_message(data,types[topic]);h=getattr(m,'header',None)
  if h:core[stamp(h.stamp)][topic]+=1
  if topic=='/sensor_visualizer/frame_index':frames.append(json.loads(m.data))
  elif topic=='/joint_states':joint[stamp(m.header.stamp)]=dict(zip(m.name,m.position))
  elif topic=='/tf':
   for tr in m.transforms:
    t=tr.transform.translation;q=tr.transform.rotation;tf[stamp(tr.header.stamp)][tr.child_frame_id]=(tr.header.frame_id,matrix([t.x,t.y,t.z],[q.x,q.y,q.z,q.w]))
  elif topic.endswith('/camera_info'):
   cal[(stamp(m.header.stamp),cid(topic))]={'width':m.width,'height':m.height,'model':m.distortion_model,'k':list(m.k),'d':list(m.d),'frame_id':m.header.frame_id}
  elif topic.endswith('/points'):cloud_counts[topic].append(m.width*m.height)
 if not legacy:
  frames=[dict(g,group_id=g.get('group',g.get('frame',i)),simulation_time_ns=round(g['native_time_s']*1e9)) for i,g in enumerate(native_groups)]
 rows=[];found={};meta={};errors=[];expected_topics={t for t in types if t.endswith('/points') or t.endswith('/camera_info') or t.endswith('/image_raw') or t.endswith('/image_raw/compressed')}|{'/joint_states'}
 for f in frames:
  target=f['simulation_time_ns'];candidates=[s for s in core if abs(s-target)<=2];counts=collections.Counter()
  for s in candidates:counts.update(core[s])
  f['_missing_core']=sorted(expected_topics-set(counts))
 x,types=reader()
 while x.has_next():
  topic,data,bt=x.read_next()
  if not(topic.endswith('/image_raw') or topic.endswith('/image_raw/compressed')):continue
  camera=cid(topic)
  if camera not in CAMERAS:continue
  m=deserialize_message(data,types[topic]);s=stamp(m.header.stamp)
  candidates=[]
  for i,f in enumerate(frames):
   target=f['simulation_time_ns'];exact=abs(s-target)<=2
   alternate=f.get('native_sensor_times_s',{}).get(topic)
   diagnostic=(not exact and alternate is not None and abs(s-round(alternate*1e9))<=2)
   if exact or diagnostic:candidates.append((i,f,exact))
  if not candidates:continue
  if legacy:
   png=bytes(m.data);rgb=np.ascontiguousarray(np.asarray(Image.open(io.BytesIO(png)).convert('RGB')))
  else:
   encoding=m.encoding.lower();channels=4 if encoding in ('rgba8','bgra8') else 3 if encoding in ('rgb8','bgr8') else None
   if channels is None:raise RuntimeError('Unsupported actual native encoding '+encoding)
   rgb=np.ndarray((m.height,m.width,channels),dtype='u1',buffer=m.data,strides=(m.step,channels,1))[:,:,:3]
   if encoding.startswith('bgr'):rgb=rgb[:,:,::-1]
   rgb=np.ascontiguousarray(rgb);png=None
  digest=hashlib.sha256(rgb.tobytes()).hexdigest()
  for i,f,exact in candidates:
   wanted=f.get('images',{}).get(topic,{}).get('sha256')
   if wanted and wanted!=digest:continue
   key=(i,camera)
   if key in found:continue
   valid=capture_ok and exact and not f['_missing_core']
   folder='images' if valid else 'diagnostic_images';path=case/folder/camera/f'frame_{i:04d}_{s}.png';path.parent.mkdir(parents=True,exist_ok=True)
   if png is not None:path.write_bytes(png)
   else:Image.fromarray(rgb).save(path,compress_level=1)
   row={'group':i,'camera':camera,'image':path.relative_to(case).as_posix(),'header_stamp_ns':s,'group_stamp_ns':f['simulation_time_ns'],'bag_receive_stamp_ns':bt,'header_matches_group':exact,'matches_observed_pixels':wanted is None or wanted==digest,'valid':valid,'width':rgb.shape[1],'height':rgb.shape[0],'rgb_sha256':digest,'rgb_mean':float(rgb.mean()),'rgb_std':float(rgb.std()),'original_topic':topic,'original_type':types[topic].__name__}
   found[key]=row;rows.append(row)
   calib=next((v for (t,c),v in cal.items() if c==camera and abs(t-s)<=2),None)
   transform_time=next((t for t in tf if abs(t-s)<=2),None)
   graph=tf.get(transform_time,{})
   def world(frame,seen=None):
    seen=set() if seen is None else seen
    if frame=='world':return np.eye(4)
    if frame in seen or frame not in graph:return None
    seen.add(frame);parent,local=graph[frame];base=world(parent,seen);return None if base is None else base@local
   pose=world(m.header.frame_id)
   meta[str(i)+'/'+camera]={'camera_info':calib,'optical_world_matrix':pose.tolist() if pose is not None else None,'joints_rad':next((v for t,v in joint.items() if abs(t-s)<=2),None),'missing_core_at_group':f['_missing_core'],'source_index':{k:f.get(k) for k in ('group_id','request_id','attempt_id','native_time_s','native_sensor_times_s','requested_pt_total_spp','sdk_subframes_at_capture')}}
 for i,f in enumerate(frames):
  missing=[c for c in CAMERAS if (i,c) not in found]
  if missing:errors.append({'group':i,'missing_images':missing})
 (case/'frames.csv').parent.mkdir(parents=True,exist_ok=True)
 fields=['group','camera','image','header_stamp_ns','group_stamp_ns','bag_receive_stamp_ns','header_matches_group','matches_observed_pixels','valid','width','height','rgb_sha256','rgb_mean','rgb_std','original_topic','original_type']
 with (case/'frames.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(sorted(rows,key=lambda r:(r['group'],r['camera'])))
 result={'capture_valid':bool(capture_ok),'requested_groups':cfg['requested_groups'],'indexed_groups':len(frames),'images':len(rows),'valid_images':sum(r['valid'] for r in rows),'errors':errors,'all_expected_images_valid':capture_ok and len(frames)==cfg['requested_groups'] and len(rows)==len(frames)*4 and all(r['valid'] for r in rows),'topics':dict(stats),'point_counts':{k:{'min':min(v),'max':max(v),'mean':sum(v)/len(v)} for k,v in cloud_counts.items()},'bag_bytes':sum(p.stat().st_size for p in bag.glob('*.mcap')),'bag_path':str(bag),'decoder_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'limits':['All image files are decoded from the actual MCAP; no re-rendering or stamp repair.','Diagnostic pixel association does not turn a failed timing group into valid data.','Native streaming has no custom group-id header; selection uses logged physical time and payload hash when available.']}
 (case/'frame_metadata.json').write_text(json.dumps(meta,indent=2));(case/'decoded.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('topics','point_counts','limits')}));return 0 if result['all_expected_images_valid'] else 2
if __name__=='__main__':raise SystemExit(decode(sys.argv[1]))
