"""Full q02 replay with final analysis, fixed pair checks and main-round release."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import save,sha
from tools.native_rotation_localization.compare_layers import compare
from tools.native_rotation_localization.analyze_output_reference import analyze as output_reference
suite=ROOT/'reports/native_rotation_localization/native007_20261015_v1'
def run():
 state=json.loads((suite/'sequences/qualification_q02/status.json').read_text())
 if state['state']!='TERMINAL_WITH_BLOCKED_BRANCHES':raise RuntimeError('Qualification sequence not terminal')
 results=[];env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
 for row in state['runs']:
  if row['result']['state'].startswith('BLOCKED'):continue
  path=Path(row['result']['path'])
  with (path/'analysis_final_replay.log').open('xb') as log:
   subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_rotation_localization/analyze_independent.py'),str(path),'analysis_final'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=True)
  old=json.loads((path/'analysis/summary.json').read_text());new=json.loads((path/'analysis_final/summary.json').read_text())
  is_official=row['condition'] in ('A2','A3')
  keys=('measurement_qualified','distance_ok','direction_ok','native_pose_ok','geometry_absolute_ok','geometry_increment_ok','candidate_counts')
  stable=all(old[k]==new[k] for k in keys)
  results.append({'condition':row['condition'],'profile':row['profile'],'path':str(path),'measurement_qualified':new['measurement_qualified'],'decision_regression_equal':stable,
      'full_GMO_decoded':new['readback']['full_GMO_independently_decoded'],'old_analysis_sha':sha(path/'analysis/summary.json'),'final_analysis_sha':sha(path/'analysis_final/summary.json')})
  if not stable and not is_official:raise RuntimeError('Unexpected solid-state analysis decision change')
  if row['condition'] in ('A0','A1','B1','B2') and new['measurement_qualified'] is not True:raise RuntimeError('Qualified mandatory condition failed final replay')
 pairs=[]
 for profile in ('S0','S5','R6P','R3P'):
  for condition in ('A1','B1','B2'):
   value=compare(suite/'A0'/profile/'r01/q02',suite/condition/profile/'r01/q02');pairs.append(value)
   save(suite/'comparisons'/('q02_A0_'+condition+'_'+profile+'.json'),value)
   if not value['comparison_qualified']:raise RuntimeError('Pair input/model/identity prerequisite failed '+condition+' '+profile)
 for condition in ('B1',):
  for profile in ('R6P','R3P'):save(suite/'comparisons'/('q02_output_reference_'+condition+'_'+profile+'.json'),output_reference(suite/condition/profile/'r01/q02'))
 release={'released_conditions':['A0','A1','B1','B2'],'official_dynamic_block':'A2/A3 retain angular noise; static nominal-ray residual exceeds unchanged threshold; dynamic inference unavailable',
  'replays':results,'pairs':[{k:v for k,v in p.items() if k!='targets'} for p in pairs],
  'trigger_B3':any(p['quality_differing_targets'] or p['candidate_differing_targets'] for p in pairs if '/B1/' in p['right'] or '/B2/' in p['right']),
  'formal_continuous_acceptance':False}
 save(suite/'qualification_release.json',release);print(json.dumps({'replayed':len(results),'decoded':sum(r['full_GMO_decoded'] for r in results),'pairs':len(pairs),'B3_triggered':release['trigger_B3']}))
if __name__=='__main__':run()
