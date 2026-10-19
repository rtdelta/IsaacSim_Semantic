"""Exploratory numerical descriptors; never claims the GPU uses NumPy arithmetic."""
import collections,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import save
suite=ROOT/'reports/native_rotation_localization/native007_20261015_v1';runs=[]
for repeat in ('r01','r02','r03'):
 p=suite/'A0/CODED'/repeat/'code01';metrics=json.loads((p/'analysis/target_metrics.json').read_text());headers=json.loads((suite/'stage_analysis/coded'/('header_A0_CODED_'+repeat+'_code01.json')).read_text())['targets'];out=[]
 for m,r in zip(metrics,headers):
  q0=np.array(m['native_header']['frame_start']['quaternion_raw'],dtype=np.float64);q1=np.array(m['native_header']['frame_end']['quaternion_raw'],dtype=np.float64)
  dot64=float(q0@q1);dot32=float(np.sum(q0.astype(np.float32)*q1.astype(np.float32),dtype=np.float32));normalized=float(dot64/(np.linalg.norm(q0)*np.linalg.norm(q1)))
  out.append({'target_index':m['target_index'],'motion_step':m['motion_step'],'physical_increment_deg':round(math.degrees(r['physical_increment_rad']),8),
   'distance_candidate':m['candidate']['best_members'],'status':m['candidate']['status'],'header_end_current':r['header_end_matches_current'],'header_midpoint_pass':r['header_midpoint_distance_p95_m']<=1e-5,
   'raw_quaternion_dot_float64':dot64,'component_product_sum_float32':dot32,'normalized_dot_float64':normalized,
   'float32_dot_ge_one':dot32>=1.0,'float32_epsilon':float(np.finfo(np.float32).eps)})
 groups=[]
 for delta in sorted({r['physical_increment_deg'] for r in out}):
  rr=[r for r in out if r['physical_increment_deg']==delta];groups.append({'increment_deg':delta,'targets':len(rr),'candidates':dict(collections.Counter('|'.join(r['distance_candidate']) for r in rr)),
   'header_end_current':sum(r['header_end_current'] for r in rr),'midpoint_failures':sum(not r['header_midpoint_pass'] for r in rr),'float32_dot_ge_one':sum(r['float32_dot_ge_one'] for r in rr)})
 runs.append({'repeat':repeat,'groups':groups,'rows':out})
result={'status':'EXPLORATORY_AFTER_CODED_RESULTS','scope':'Descriptive floating-point arithmetic on reported quaternions. No fitted threshold, no claim that SDK/GPU uses this formula, reduction order, normalization or branch condition. Requires independent instrumentation/version experiment for causality.','runs':runs}
save(suite/'stage_analysis/coded/exploratory_small_rotation.json',result);print(json.dumps({'scope':result['scope'],'groups_by_repeat':[{k:v for k,v in r.items() if k!='rows'} for r in runs]}))
