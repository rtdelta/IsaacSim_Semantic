"""Offline D/U/P paired analysis; preserve full native identity set differences."""
import collections,gzip,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows,save,sha
from tools.native_rotation_localization.math_independent import decode,difference,quantiles
from tools.native_rotation_localization.normalizer import normalize
def read_run(directory):
 p=Path(directory);c=p/'continuous'
 return {'path':p,'c':c,'spec':json.loads((p/'run_spec.json').read_text()),'summary':json.loads((p/'analysis/summary.json').read_text()),
  'metrics':json.loads((p/'analysis/target_metrics.json').read_text()),'raw':{r['receipt_seq']:r for r in rows(c/'raw_events.jsonl')},
  'states':{r['physical_step']:r['matrix'] for r in rows(c/'baseline_physics.jsonl') if r['phase']=='physics_post_actual'},
  'fingerprint':json.loads((c/'configuration_fingerprint.json').read_text()),'sensor':json.loads((c/'sensor_manifest.json').read_text())['attributes']}
def cloud(run,target):
 r=run['raw'][target['receipt_seq']];b=gzip.decompress((run['c']/r['native_event']['packet_path']).read_bytes());h,a,xyz=decode(b);valid=(a['flags']&64)!=0
 ids=np.column_stack([a[k][valid] for k in ('emitter_id','channel_id','tick_id','echo_id')]);order=np.lexsort(ids.T[::-1]);ids=ids[order]
 n=normalize(h,xyz[valid][order],run['states'][target['physical_step']]);return ids,n
def compare(left,right):
 a,b=read_run(left),read_run(right);targets=[]
 expected_diffs={k for k in set(a['spec']['sensor_overrides'])|set(b['spec']['sensor_overrides']) if a['spec']['sensor_overrides'].get(k)!=b['spec']['sensor_overrides'].get(k)}
 actual_diffs={k for k in set(a['sensor'])|set(b['sensor']) if a['sensor'].get(k)!=b['sensor'].get(k)}
 params_ok=actual_diffs==expected_diffs
 fp_ok=all(a['fingerprint'][k]==b['fingerprint'][k] for k in ('environment','effective','scene'))
 for x,y in zip(a['metrics'],b['metrics']):
  row={'target_index':x['target_index'],'motion_step':x['motion_step'],'same_motion_step':x['motion_step']==y['motion_step']}
  pe,re=difference(a['states'][x['physical_step']],b['states'][y['physical_step']]);row.update(input_position_difference_m=pe,input_rotation_difference_rad=re)
  ia,na=cloud(a,x);ib,nb=cloud(b,y);same=np.array_equal(ia,ib)
  row['same_full_valid_ray_set']=same;row['valid_counts']=[len(ia),len(ib)]
  if same:
   row['radial_difference_m']=quantiles(abs(na['distance']-nb['distance']))
   row['world_point_difference_m']=quantiles(np.linalg.norm(na['world']-nb['world'],axis=1))
  else:
   sa={tuple(i) for i in ia};sb={tuple(i) for i in ib};row.update(left_only_ids=len(sa-sb),right_only_ids=len(sb-sa))
  keys=('distance_ok','direction_ok','geometry_absolute_ok','native_pose_ok')
  row['different_quality_categories']=[k for k in keys if x.get(k)!=y.get(k)]
  row['candidate_difference']=x['candidate']['best_members']!=y['candidate']['best_members']
  row['candidates']=[x['candidate']['best_members'],y['candidate']['best_members']];targets.append(row)
 input_ok=len(targets)==a['spec']['targets']==b['spec']['targets'] and all(r['same_motion_step'] and r['input_position_difference_m']<=1e-5 and r['input_rotation_difference_rad']<=1e-6 for r in targets)
 qualified=params_ok and fp_ok and input_ok and all(r['same_full_valid_ray_set'] for r in targets) and all(r['summary']['measurement_qualified'] is True for r in (a,b))
 return {'left':str(left),'right':str(right),'comparison_qualified':qualified,'input_qualified':input_ok,'parameters_qualified':params_ok,'environment_effective_scene_equal':fp_ok,
  'actual_sensor_differences':sorted(actual_diffs),'expected_sensor_differences':sorted(expected_diffs),
  'scope':'API plus topology' if a['spec']['api']!=b['spec']['api'] else 'output mode',
  'quality_differing_targets':sum(bool(r['different_quality_categories']) for r in targets),'candidate_differing_targets':sum(r['candidate_difference'] for r in targets),
  'distance_difference_p95_max_m':max((r.get('radial_difference_m',{}).get('0.95',0.) for r in targets),default=None),'targets':targets}
if __name__=='__main__':
 result=compare(sys.argv[1],sys.argv[2]);save(Path(sys.argv[3]),result);print(json.dumps({k:v for k,v in result.items() if k!='targets'}))
