"""Compare core pose, calibration and scoped timing; never claim schemas identical."""
import collections,json,sys,statistics,math
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

def summary(v):
 return {'n':len(v),'median':statistics.median(v),'min':min(v),'max':max(v),'mean':statistics.mean(v)} if v else {'n':0}
def matrix(p,q):
 x,y,z,w=q;r=np.eye(4);r[:3,3]=p;r[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]];return r
def first_legacy_frame(session):
 reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
 types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
 while reader.has_next():
  topic,data,t=reader.read_next()
  if topic=='/sensor_visualizer/frame_index':return json.loads(deserialize_message(data,types[topic]).data)
 raise RuntimeError('No legacy frame index')
def main():
 root=Path(__file__).resolve().parents[1];oldinfo=json.loads((root/'reports/latest_reference.json').read_text());newinfo=json.loads((root/'reports/latest_native_reference.json').read_text())
 olds=json.loads((Path(oldinfo['directory'])/'reference_result.json').read_text());news=json.loads((Path(newinfo['directory'])/'reference_native_result.json').read_text());result={'legacy':[],'native':[],'alignment':[]}
 new_frame=json.loads((Path(news[0]['directory'])/'groups.jsonl').read_text().splitlines()[0]);native_manifest=json.loads((Path(news[0]['directory'])/'sensor_manifest.json').read_text());ns={s['id']:s for s in native_manifest['sensors']}
 reference_tf=new_frame['expected_tf'];tr=reference_tf['swing_coordinate'];base=matrix(tr['translation'],tr['quaternion_xyzw'])
 def native_world(frame):
  tr=reference_tf[frame];return base@matrix(tr['translation'],tr['quaternion_xyzw'])
 for case in olds:
  directory=Path(case['directory']);r=json.loads((directory/'result.json').read_text());session=Path(r['capture']['session']);frame=first_legacy_frame(session);registry=json.loads((session/'sensor_registry.json').read_text())
  errors={};calibration={};parameters={}
  for kind in ('cameras','lidars'):
   for sensor in registry[kind]:
    sid=sensor['id'];want=np.asarray(frame[kind][sid]['to_world']).T
    if kind=='cameras':want=want@np.diag([1,-1,-1,1])
    errors[kind+'/'+sid]=float(np.max(np.abs(want-native_world(ns[sid]['frame_id']))))
    if kind=='cameras':
     calibration[sid]=sensor['calibration']['intrinsics']==ns[sid]['calibration'] and [sensor['calibration']['width'],sensor['calibration']['height']]==ns[sid]['size']
    else:parameters[sid]={k:{'legacy':sensor.get('parameters',{}).get(k),'native':v} for k,v in ns[sid]['parameters'].items()}
  result['alignment'].append({'directory':str(directory),'pose_errors':errors,'max_pose_error':max(errors.values()),'calibration_match':calibration,'lidar_parameters':parameters,'source_sha256':json.loads((session/'asset_manifest.json').read_text())['root_sha256']})
  rows=[]
  for p in (directory/'captures/runs').glob('*/diagnostics/events_*.jsonl'):rows.extend(json.loads(l) for l in p.read_text().splitlines())
  scoped=collections.defaultdict(list);groups={}
  for row in rows:
   if row.get('event')!='span_end' or row.get('group_id') is None:continue
   name=row.get('name');g=row['group_id'];scoped[name].append(row['duration_ns']/1e9)
   if name=='lab.SceneStepper.advance_clock':groups.setdefault(g,{})['start']=row['start_ns']
   if name=='lab.SensorDrivers.acquire':groups.setdefault(g,{})['end']=row['start_ns']+row['duration_ns']
  ready=[(v['end']-v['start'])/1e9 for v in groups.values() if 'end' in v and 'start' in v]
  render_by_group=collections.Counter()
  for row in rows:
   if row.get('event')=='span_end' and row.get('name')=='render_wait' and row.get('group_id') is not None:render_by_group[row['group_id']]+=row['duration_ns']/1e9
  result['legacy'].append({'repeat':case['repeat'],'policy':case['policy'],'directory':str(directory),'capture':r['capture'],'process_wall_s':r['process_wall_s'],'validation':r['validation'],'owned_payload_scope_s':summary(ready),'render_calls_s':summary(list(render_by_group.values())),'stages_s':{k:summary(v) for k,v in scoped.items() if k.startswith('lab.SceneStepper.') or k in ('lab.SensorDrivers.warm_cameras','lab.SensorDrivers.acquire','lab.RecordPipeline.submit')}})
 for case in news:
  directory=Path(case['directory']);r=json.loads((directory/'result.json').read_text());rows=[json.loads(l) for l in (directory/'groups.jsonl').read_text().splitlines()]
  result['native'].append({'repeat':case['repeat'],'directory':str(directory),'state':r['state'],'capture':r['capture'],'process_wall_s':r['process_wall_s'],'mcap_bytes':sum(p.stat().st_size for p in (directory/'bag').glob('*.mcap')),'validation':{k:r['group_validation'][k] for k in ('ok','errors')},'render_calls_s':summary([v['warm_s']+v['formal_s'] for v in rows]),'payload_observed_scope_s':summary([v['payload_observed_scope_s'] for v in rows]),'observation_s':summary([v['evidence_s'] for v in rows]),'settings':json.loads((directory/'sensor_manifest.json').read_text())['settings'],'duplicate_counts':{topic:sum(g['counts'].get(topic,0) for g in r['group_validation']['groups']) for topic in rows[0]['images']}})
 result['alignment_passed']=all(r['max_pose_error']<=2e-3 and all(r['calibration_match'].values()) for r in result['alignment'])
 result['limits']=['Compare core output semantics, not byte-identical bag schemas. Camera TF aliases differ.',
  'Native emits Image; legacy emits PNG CompressedImage and extra pose/index/metadata/horizontal-TF topics.',
  'Native render_calls excludes extra observation; legacy render_wait may include callback materialization. Both are actual SDK-call scopes.',
  'Legacy owned_payload_scope and native payload_observed_scope both include six-step movement/pose preparation plus fresh-output proof, but hash/ownership work differs.',
  'Native measurement window excludes final SDK drain and bag close; legacy capture.wall_s includes pipeline tail. Whole process includes distinct startup costs.',
  'Native snapshot observation is extra diagnostic work; repeated native publications add storage/DDS work. No pure scheduler speedup is inferred from wall time alone.']
 path=root/'reports/reference_comparison.json';path.write_text(json.dumps(result,indent=2));print(json.dumps({'alignment_passed':result['alignment_passed'],'output':str(path),'legacy':len(olds),'native':len(news)}))
if __name__=='__main__':main()
