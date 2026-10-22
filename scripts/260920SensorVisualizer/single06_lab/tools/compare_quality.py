"""Compare same-pose camera samples, preserving original compressed payloads.

Metrics describe differences, not objective quality or strict 3DGS alignment.
Runs in the already installed ROS Python environment after capture completes.
"""
import argparse,io,json,math
from pathlib import Path
import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

def images(case,index=1):
 r=json.loads((case/'result.json').read_text());session=Path(r['capture']['session'])
 reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
 types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()};counts={};out={}
 while reader.has_next():
  topic,data,t=reader.read_next()
  if not topic.endswith('/image_raw/compressed'):continue
  counts[topic]=counts.get(topic,0)+1
  if counts[topic]!=index+1:continue
  m=deserialize_message(data,types[topic]);raw=bytes(m.data);image=Image.open(io.BytesIO(raw));image.load()
  out[topic.split('/')[2]]=(t,np.asarray(image).astype(np.float64),raw)
 return out

def edge_energy(rgb):
 gray=rgb.mean(axis=2)
 lap=gray[1:-1,:-2]+gray[1:-1,2:]+gray[:-2,1:-1]+gray[2:,1:-1]-4*gray[1:-1,1:-1]
 return float(np.mean(lap*lap))

def main():
 p=argparse.ArgumentParser();p.add_argument('baseline');p.add_argument('candidate');p.add_argument('--output',required=True);a=p.parse_args()
 output=Path(a.output);output.mkdir(parents=True,exist_ok=False)
 samples=[images(Path(case)) for case in (a.baseline,a.candidate)];assert samples[0].keys()==samples[1].keys()
 result={'group_id':1,'baseline':a.baseline,'candidate':a.candidate,'cameras':{},
   'limits':['Same source pose and native timestamp are checked by existing MCAP validators.',
    'JPEG/TAA/random rendering may differ. PSNR and edge energy are descriptive; no automatic visual-quality acceptance.',
    'These comparisons do not establish physical sensor realism or counterpart 3DGS alignment.']}
 for name,(stamp,before,raw) in samples[0].items():
  other,after,raw_after=samples[1][name];assert stamp==other and before.shape==after.shape
  mse=float(np.mean((before-after)**2))
  result['cameras'][name]={'native_stamp_ns':stamp,'shape':list(before.shape),
    'mean_absolute_rgb_error':float(np.mean(np.abs(before-after))),
    'psnr_db':10*math.log10(255**2/mse) if mse else None,
    'edge_energy_baseline':edge_energy(before),'edge_energy_candidate':edge_energy(after)}
  (output/(name+'_gated.jpg')).write_bytes(raw);(output/(name+'_keepalive.jpg')).write_bytes(raw_after)
 (output/'quality_comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
