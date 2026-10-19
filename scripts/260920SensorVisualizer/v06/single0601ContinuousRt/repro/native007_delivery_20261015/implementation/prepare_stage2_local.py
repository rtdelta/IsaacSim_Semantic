"""Freeze confirmation selected by terminal T3 results and the fixed coded C0 test."""
import copy,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'config/native_rotation_localization/v1'
def save(name,data):
 p=CFG/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Refuse overwrite '+str(p))
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return p
def prepare():
 receipt=ROOT/'reports/remote/reports/native_rotation_localization/native007_20261015_v1/stage_analysis/T3/summary.json'
 result=json.loads(receipt.read_text())
 boundary=receipt.parent/'intervention_confirmation_release.json';review=json.loads(boundary.read_text())
 if not review['eligible_for_full_output_repeat']:raise RuntimeError('T3 full-output repetition prerequisites failed')
 changed=sorted({Path(p['right']).parts[-4] for p in result['pairs'] if ('/R6P/' in p['right'] or '/R3P/' in p['right']) and (p['quality_differing_targets'] or p['candidate_differing_targets'])})
 rows=[]
 for r,cs in [('r01',['A0']+changed),('r02',list(reversed(['A0']+changed))),('r03',['A0']+changed)]:
  for c in cs if changed else []:
   src=CFG/(f'specs/{c}_R6P_r01_'+('q02' if c=='A0' else 'cq01')+'.json');s=json.loads(src.read_text())
   s.update(repeat=r,run_id='cm01',targets=100,phase='T3_confirmation',output_relative=f'reports/native_rotation_localization/native007_20261015_v1/{c}/R6P/{r}/cm01')
   name=f'specs/{c}_R6P_{r}_cm01.json';save(name,s);rows.append({'spec':'config/native_rotation_localization/v1/'+name,'condition':c,'profile':'R6P','repeat':r,'targets':100,'phase':'T3_confirmation','capability':'qualified_T3_short'})
 save('extension_confirm_m01_sequence.json',{'id':'extension_confirm_m01','runs':rows,'requires_lock':True,'max_batch_runs':4,'reserve_bytes':8589934592,'trigger':'T3 single-factor full-output changes; repeat all outputs and independent per-run metrics, no intersection filtering. Strict full valid-return-set pairing remains unqualified where sets differ. No engineering repair claim.','changed_conditions':changed,'T3_summary_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),'boundary_review_sha256':hashlib.sha256(boundary.read_bytes()).hexdigest(),'strict_pair_gate_preserved':True})
 yaw=0.;table=[]
 for n in range(1,613):
  delta=(.02,.05,.10)[((17*n+5)%31)%3];yaw+=delta;table.append({'motion_step':n,'increment_deg':delta,'yaw_deg':yaw,'yaw_rad':math.radians(yaw)})
 frozen=save('coded_input_100_targets.json',{'algorithm':'values=[0.02,0.05,0.10]; j=((17*n+5)%31)%3; n=1..612; cumulative degrees then radians','targets':100,'stride':6,'drain_steps':12,'rows':table})
 rows=[]
 for r in ('r01','r02','r03'):
  s=json.loads((CFG/'specs/A0_R6P_r01_q02.json').read_text());s.update(profile='CODED',block='CODED',repeat=r,run_id='code01',targets=100,phase='T4',motion='coded',yaw_rate_deg_s=0.,
   frozen_input_path=frozen.relative_to(ROOT).as_posix(),frozen_input_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest(),output_relative=f'reports/native_rotation_localization/native007_20261015_v1/A0/CODED/{r}/code01')
  name=f'specs/A0_CODED_{r}_code01.json';save(name,s);rows.append({'spec':'config/native_rotation_localization/v1/'+name,'condition':'A0','profile':'CODED','repeat':r,'targets':100,'phase':'T4','capability':'C0_static_qualified'})
 save('extension_coded_m01_sequence.json',{'id':'extension_coded_m01','runs':rows,'requires_lock':True,'max_batch_runs':4,'reserve_bytes':8589934592,'trigger':'Reported-endpoint and constant-speed candidates remain observational predictions; actual consumption unavailable. Fixed nonuniform C0 input tests predictions without fitting; no change to sensor/render settings.'})
 print(json.dumps({'changed_conditions':changed,'confirmation_runs':len(changed)*3+3 if changed else 0,'coded_runs':3,'coded_input_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest()}))
if __name__=='__main__':prepare()
