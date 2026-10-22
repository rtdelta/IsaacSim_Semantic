"""Bounded complete-stage offline comparison and metadata predictions."""
import collections,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import save,sha
from tools.native_rotation_localization.compare_layers import compare,read_run
from tools.native_rotation_localization.compare_interventions import analyze as intervention
from tools.native_rotation_localization.analyze_header_models import analyze as header_models
from tools.native_rotation_localization.analyze_output_reference import analyze as output_reference
from tools.native_rotation_localization.math_independent import wrap
SUITE=ROOT/'reports/native_rotation_localization/native007_20261015_v1'
def run(stage):
 sequence={'main':'main_m02','B3':'extension_B3_q01','speed':'extension_speed_m01','T3':'extension_T3_q01','confirm':'extension_confirm_m01','coded':'extension_coded_m01'}[stage]
 if stage=='T3' and (ROOT/'config/native_rotation_localization/v1/T3_resume_release.json').is_file():sequence=json.loads((ROOT/'config/native_rotation_localization/v1/T3_resume_release.json').read_text())['sequence']
 state=json.loads((SUITE/'sequences'/sequence/'status.json').read_text())
 if state['state'] not in ('COMPLETE','TERMINAL_WITH_BLOCKED_BRANCHES'):raise RuntimeError('Requested stage not complete')
 dest=SUITE/'stage_analysis'/stage;dest.mkdir(parents=True,exist_ok=False);pairs=[];models=[];world=[]
 runs=[Path(r['result']['path']) for r in state['runs'] if r['result']['state']=='COMPLETE']
 for path in runs:
  spec=json.loads((path/'run_spec.json').read_text());label='_'.join(spec[k] for k in ('condition','profile','repeat','run_id'))
  if spec['profile'] not in ('S0','S5'):
   d=header_models(path);save(dest/('header_'+label+'.json'),d);models.append({k:v for k,v in d.items() if k!='targets'})
   if spec['sensor_overrides']['omni:sensor:Core:outputFrameOfReference']=='WORLD':
    d=output_reference(path);save(dest/('output_'+label+'.json'),d);world.append({'run':str(path),'previous1_passed':sum(r['candidate_direction_errors_rad']['previous1']['0.95']<=1e-6 for r in d['targets']),'N':len(d['targets'])})
  left=None
  if stage=='main' and spec['condition'] in ('B1','B2'):left=SUITE/'A0'/spec['profile']/spec['repeat']/spec['run_id']
  if stage=='B3':left=SUITE/'B1'/spec['profile']/'r01/q02'
  if stage=='speed' and spec['condition'] in ('B1','B2'):left=SUITE/'A0'/spec['profile']/spec['repeat']/spec['run_id']
  if stage=='T3':left=SUITE/'A0'/spec['profile']/'r01/q02'
  if stage=='confirm' and spec['condition']!='A0':left=SUITE/'A0'/spec['profile']/spec['repeat']/spec['run_id']
  if stage=='coded' and spec['condition']!='A0':left=SUITE/'A0'/spec['profile']/spec['repeat']/spec['run_id']
  if left:
   d=intervention(left,path) if stage in ('T3','confirm','coded') and spec['condition'].startswith('C') else compare(left,path)
   save(dest/('pair_'+label+'.json'),d);pairs.append({k:v for k,v in d.items() if k not in ('targets','scan_semantics')})
 common=[]
 if stage=='coded':
  from tools.native_rotation_localization.coded_input_review import review
  coded=[review(p) for p in runs];save(dest/'coded_input_review.json',coded)
  if not all(r['full_preregistered_table_matches'] and r['recorded_capture_hash_matches'] and r['runtime_frozen_before_motion'] for r in coded):raise RuntimeError('Coded full-input evidence differs from preregistration')
 if stage=='speed':
  for path in runs:
   slow=read_run(path);spec=slow['spec'];fast=read_run(SUITE/spec['condition']/'R6P'/spec['repeat']/'m02');rows=[]
   for k in range(50):
    a,b=slow['metrics'][2*k+1],fast['metrics'][k]
    rows.append({'yaw_deg':math.degrees(a['actual_yaw_rad']),'orientation_difference_rad':abs(wrap(a['actual_yaw_rad']-b['actual_yaw_rad'])),
     'R3P_index':2*k+1,'R6P_index':k,'R3P_candidate':a['candidate']['best_members'],'R6P_candidate':b['candidate']['best_members'],
     'R3P_yaw_error_rad':a['geometry']['yaw_error_rad'],'R6P_yaw_error_rad':b['geometry']['yaw_error_rad']})
   d={'condition':spec['condition'],'repeat':spec['repeat'],'N':50,'all_orientations_match':all(r['orientation_difference_rad']<=1e-6 for r in rows),'candidate_differences':sum(r['R3P_candidate']!=r['R6P_candidate'] for r in rows),'rows':rows}
   common.append(d)
  save(dest/'common_orientations.json',common)
 result={'stage':stage,'sequence':sequence,'runs':len(runs),'blocked_rows':[r for r in state['runs'] if r['result']['state'].startswith('BLOCKED')],'pairs':pairs,'header_predictions':models,'world_output_predictions':world,
   'all_pair_qualified':all(d['comparison_qualified'] for d in pairs),'common_orientation_summaries':[{k:v for k,v in d.items() if k!='rows'} for d in common],
   'analysis_sources':[{ 'path':str(Path(x).relative_to(ROOT)),'sha256':sha(Path(x))} for x in ( __file__,str(ROOT/'tools/native_rotation_localization/analyze_header_models.py'),str(ROOT/'tools/native_rotation_localization/compare_interventions.py'))],
   'formal_continuous_acceptance':False}
 save(dest/'summary.json',result);print(json.dumps(result))
if __name__=='__main__':run(sys.argv[1])
