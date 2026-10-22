"""Decode standard MCAP images for a static, second-group cross-chain check."""
import io,json
from pathlib import Path
import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
oldroot=Path(json.loads((root/'reports/latest_reference.json').read_text())['directory'])
newroot=Path(json.loads((root/'reports/latest_native_reference.json').read_text())['directory'])
trace=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
out=trace.parent/'final_analysis/cross_images';out.mkdir(exist_ok=True)

def reader(path):
 r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=str(path),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
 return r,{t.name:get_message(t.type) for t in r.get_all_topics_and_types()}

def stamp(m):return m.header.stamp.sec*10**9+m.header.stamp.nanosec

def images(path,topics,target=None,legacy=False):
 r,types=reader(path);pending={};frames=0;found={}
 while r.has_next():
  topic,data,t=r.read_next()
  if topic in topics:
   m=deserialize_message(data,types[topic]);s=stamp(m)
   if legacy:
    array=np.asarray(Image.open(io.BytesIO(bytes(m.data))).convert('RGB'))
   else:
    assert m.encoding=='rgb8',m.encoding
    array=np.frombuffer(bytes(m.data),dtype=np.uint8).reshape(m.height,m.step)[:,:m.width*3].reshape(m.height,m.width,3).copy()
   pending.setdefault(s,{})[topics[topic]]=array
   if target==s:found[topics[topic]]=array
  elif legacy and topic=='/sensor_visualizer/frame_index':
   frames+=1
   if frames==2:
    target=json.loads(deserialize_message(data,types[topic]).data)['simulation_time_ns'];found=pending.get(target,{})
  if target is not None and len(found)==4:return target,found
 raise RuntimeError('Four current second-group images not found')

oldcases=json.loads((oldroot/'reference_result.json').read_text());newcases=json.loads((newroot/'reference_native_result.json').read_text());native={};rows=[]
for case in newcases:
 directory=Path(case['directory']);group=json.loads((directory/'groups.jsonl').read_text().splitlines()[1]);target=round(group['native_time_s']*1e9)
 topics={f'/camera/fisheye_{c}/image_raw':c for c in ('front','back','left','right')}
 time,values=images(directory/'bag',topics,target);native[case['repeat']]=(time,values)
 for c,array in values.items():Image.fromarray(array).save(out/f'native_{case["repeat"]}_{c}.png')
for case in oldcases:
 result=json.loads((Path(case['directory'])/'result.json').read_text());session=Path(result['capture']['session'])
 topics={f'/camera/{c}/image_raw/compressed':c for c in ('front','back','left','right')}
 time,values=images(session/'bag_unified',topics,legacy=True);newtime,other=native[case['repeat']]
 for c,array in values.items():
  want=other[c];assert want.shape==array.shape
  difference=array.astype(np.float32)-want.astype(np.float32);mse=float(np.mean(difference**2))
  rows.append({'repeat':case['repeat'],'policy':case['policy'],'camera':c,'legacy_stamp_ns':time,'native_stamp_ns':newtime,'rgb_mae':float(np.mean(np.abs(difference))),'psnr_db':float(10*np.log10(255**2/mse)) if mse else None,'legacy_rgb_mean':float(np.mean(array)),'native_rgb_mean':float(np.mean(want))})
  Image.fromarray(array).save(out/f'legacy_{case["repeat"]}_{case["policy"]}_{c}.png')
report={'group_index':1,'comparisons':rows,'limits':['Static pose and second group; distinct startup and accumulation histories remain.','Rendered reference difference is not a ground-truth quality score.','Native and legacy header epochs differ; each image was selected by its own exact group timestamp.']}
(out.parent/'cross_image_comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps({'comparisons':len(rows),'output':str(out.parent/'cross_image_comparison.json')}))
