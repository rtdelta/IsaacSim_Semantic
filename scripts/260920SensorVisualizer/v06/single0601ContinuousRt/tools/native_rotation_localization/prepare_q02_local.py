"""Freeze fresh qualifications after raw-vs-Cartesian crosscheck repair and approved official asset arrival."""
import copy,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'config/native_rotation_localization/v1'
def save(name,data):
 p=CFG/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Refuse overwrite '+str(p))
 p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
old=json.loads((CFG/'qualification_sequence.json').read_text());order=[]
for row in old['runs']:
 s=json.loads((ROOT/row['spec']).read_text());s['run_id']='q02';s['output_relative']=s['output_relative'].rsplit('/',1)[0]+'/q02'
 s['revision_reason']='Fresh q02: correct raw-vs-normalized offline crosscheck; add explicit output enum checks and nominal rotary model; approved official asset now local. Numeric gates and A0 capture schedule unchanged.'
 r=copy.deepcopy(row);r['spec']=r['spec'].replace('_q01.json','_q02.json');r['capability']='qualification_pending'
 if s['condition'] in ('A2','A3'):
  s.update(scene_asset='/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/assets/native_rotation_localization/official/Example_Rotary.usda',source_prim='/Example_Rotary',asset_id='official',asset_sha256='0812faf5c310f40316d5a11ab0c6786e19e18ac12cea10edc2e7ee44fc56c8c6')
  r['allow_static_qualification_failure']=True
 save(Path(r['spec']).relative_to('config/native_rotation_localization/v1'),s);order.append(r)
save('qualification_q02_sequence.json',dict(old,id='qualification_q02',runs=order))
save('official_asset_qualification_preregistration.json',{'asset_sha256':'0812faf5c310f40316d5a11ab0c6786e19e18ac12cea10edc2e7ee44fc56c8c6','asset_prim':'/Example_Rotary','variants':[],
 'external_dependencies':[],'download_operation':'20261015T062502Z_67b9502583f1','transfer_operation':'20261015T062755Z_bb4e3a8a6414',
 'source_specific_parameters_preserved':{'azimuthErrorStd':0.015,'fireTimeNs_max':24500,'rangeResolutionM':0.004,'reportRateBaseHz_authored_legacy_name':36000},
 'nominal_rotary_model':'clockwise azimuth = emitter azimuth + start offset + 360*scanRate*(tickId/patternFiringRate + fireTimeNs*1e-9); validate actual installed patternFiringRate, retain noise and emitter timings',
 'qualification_policy':'S0/S5 numeric threshold unchanged; failure blocks dynamic branch, not other assets; no stochastic-noise fitting',
 'resource_estimate':'At 3600 ticks*128 emitters and 1 return, owned GMO about 32 MiB/event; short 18 events with API dual copies roughly 1.3 GiB, within 2 GiB. Actual sizes decide main-round resource qualification.'})
print({'fresh_qualification_runs':len(order),'targets':sum(x['targets'] for x in order)})
