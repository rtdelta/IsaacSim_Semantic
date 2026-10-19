"""Preregister unchanged M1 order with observed official-asset qualification block."""
import copy,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'config/native_rotation_localization/v1'
def save(name,data):
 p=CFG/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Refuse overwrite '+str(p))
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
old=json.loads((CFG/'main_sequence.json').read_text());order=[]
for row in old['runs']:
 r=copy.deepcopy(row);s=json.loads((ROOT/r['spec']).read_text());s['run_id']='m02';s['output_relative']=s['output_relative'].rsplit('/',1)[0]+'/m02'
 s['revision_reason']='Final full q02 replay release; immutable main capture and numeric thresholds. A3 blocked by retained official angular noise/static qualification, not missing asset.'
 r['spec']=r['spec'].replace('_m01.json','_m02.json');r['capability']='qualified_q02_final'
 if s['condition']=='A3':
  r['capability']='blocked_official_static_nominal_ray_qualification'
  q=json.loads((CFG/'specs/A3_S0_r01_q02.json').read_text())
  for k in ('scene_asset','source_prim','asset_id','asset_sha256'):s[k]=q[k]
 save(Path(r['spec']).relative_to('config/native_rotation_localization/v1'),s);order.append(r)
save('main_m02_sequence.json',dict(old,id='main_m02',runs=order,release_path='reports/native_rotation_localization/native007_20261015_v1/qualification_release.json'))
save('final_model_revision.json',{'revision':'pre-main-final','source':'A2 S0/S5 static-only diagnostic; no dynamic fit',
 'rotary_model':'emitter azimuth + scan-direction * 360 * scanRate * tickId / patternFiringRate + start offset',
 'fireTimeNs':'preserved as firing-time metadata; adding fireTimeNs to nominal angular offset rejected by static results',
 'noise':'source azimuthErrorStd 0.015 deg preserved; no stochastic fitting or noise removal',
 'historical_q02_analysis':'retained; all executed q02 runs replayed under analysis_final before release',
 'gates':'unchanged; static model requires distance/direction/absolute geometry pass'})
paths=[p for p in (ROOT/'tools/native_rotation_localization').glob('*.py') if p.name in ('run_layers.py','runtime.py','io.py','math_independent.py','normalizer.py','ray_model.py','official_crosscheck.py','analyze_independent.py','coordinator.py')]
paths += [CFG/'analysis_rules.json',CFG/'main_m02_sequence.json']+[ROOT/r['spec'] for r in order]
save('main_code_lock.json',{'version':'native007-final-main-lock','files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)],'formal_continuous_acceptance':False})
print({'planned':len(order),'executable':sum(not r['capability'].startswith('blocked') for r in order),'targets':sum(r['targets'] for r in order)})
