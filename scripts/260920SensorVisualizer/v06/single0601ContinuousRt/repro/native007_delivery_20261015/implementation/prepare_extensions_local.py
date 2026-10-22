"""Freeze triggered B3, speed comparison and independent C1/C2 conditions."""
import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'config/native_rotation_localization/v1'
def save(path,data):
 p=CFG/path;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Refuse overwrite '+str(p))
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def spec(condition,profile,repeat,run,targets):
 s=json.loads((CFG/('specs/A0_'+profile+'_r01_q02.json')).read_text())
 s.update(condition=condition,group='M_'+condition,repeat=repeat,run_id=run,targets=targets,phase='extension',output_relative=f'reports/native_rotation_localization/native007_20261015_v1/{condition}/{profile}/{repeat}/{run}')
 s['revision_reason']='Triggered extension frozen before capture; unchanged main-locked code and numeric gates'
 if condition in ('B1','B3'):s['sensor_overrides']['omni:sensor:Core:outputFrameOfReference']='WORLD'
 if condition in ('B2','B3'):s['sensor_overrides']['omni:sensor:Core:elementsCoordsType']='SPHERICAL'
 if condition=='C1':s['sensor_overrides']['omni:sensor:Core:accumulateOutputs']=False
 if condition=='C2':s['requested_settings']['/renderer/raytracingMotion/enabled']=False;s['launch_overrides']=['--/renderer/raytracingMotion/enabled=false']
 name=f'specs/{condition}_{profile}_{repeat}_{run}.json';save(name,s)
 return {'spec':'config/native_rotation_localization/v1/'+name,'condition':condition,'profile':profile,'repeat':repeat,'targets':targets,'phase':'extension','capability':'qualification_pending'}
def sequence(name,rows,reason):
 save(name+'_sequence.json',{'id':name,'runs':rows,'max_batch_runs':4,'reserve_bytes':8589934592,'requires_lock':True,'trigger':reason})
sequence('extension_B3_q01',[spec('B3',p,'r01','xq01',12) for p in ('S0','S5','R6P','R3P')],
 'Final q02 all 12 pairs qualified; WORLD output changes direction category at all 12 targets in each dynamic profile while radial history candidate is unchanged. Spherical normalization independently checked before this trigger.')
sequence('extension_speed_m01',[spec(c,'R3P',r,'sm01',100) for r,cs in [('r01',['A0','B1','B2']),('r02',['B2','B1','A0']),('r03',['A0','B2','B1'])] for c in cs],
 'R3P short sequence switches previous1/half (6/6) while R6P short is half only; full 100x3 for A0 and both output-mode controls, plus fixed common-orientation 50-target subsets. A1 short identical to A0; no API bridge trigger.')
sequence('extension_T3_q01',[spec(c,p,'r01','cq01',12) for c in ('C1','C2') for p in ('S0','S5','R6P','R3P')],
 'C0 frozen to qualified A0 because A3 static model fails. T2 output-direction difference is isolated but does not explain the common radial history candidate. Independent accumulation and Motion BVH interventions test that remaining radial mechanism; complete-scan semantics checked before causal interpretation.')
print({'qualification_extensions':12,'speed_long_runs':9})
