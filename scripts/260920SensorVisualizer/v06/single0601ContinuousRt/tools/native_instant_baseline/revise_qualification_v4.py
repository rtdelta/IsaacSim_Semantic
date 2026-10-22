"""Re-freeze E at running lifecycle point, with a fresh qualification series."""
import datetime,json
from pathlib import Path
from tools.native_instant_baseline.io import save,sha
root=Path(__file__).resolve().parents[2];cfg=root/'config/native_instant_baseline'
if (cfg/'run_order_v3.json').exists():raise RuntimeError('Already revised')
order=json.loads((cfg/'run_order.json').read_text());save(cfg/'run_order_v3.json',order)
frozen=json.loads((cfg/'effective_E.json').read_text());save(cfg/'effective_E_paused_probe_v1.json',frozen)
probe=root/'reports/native005_effective_E_probe_r03_20261015.json';p=json.loads(probe.read_text())
assert p['result']['passed'] and p['result']['cleanup']['passed']
frozen.update(schema_version=2,frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),observed=p['fingerprint'],probe=str(probe.relative_to(root)),probe_sha256=sha(probe),
    lifecycle='Timeline running, after fixed 24 warmup updates; pause changes loop_manual_mode, so paused snapshots are separate evidence')
save(cfg/'effective_E.json',frozen)
rules=json.loads((cfg/'analysis_rules_v3.json').read_text());rules.update(schema_version=4,
    revision_reason='Correct reference E to fresh running-state probe, retain paused probe. Same requested values, capture/analyzer code and all numeric thresholds as q03; fresh q04 qualification.')
save(cfg/'analysis_rules_v4.json',rules)
for phase in ('qualification','main'):
    new=[]
    for rel in order[phase]:
        s=json.loads((root/rel).read_text());old=s['run_id'];s['run_id']='q04' if phase=='qualification' else 'main_v4'
        s['output_relative']=s['output_relative'].rsplit('/',1)[0]+'/'+s['run_id'];s['analysis_rules_path']='config/native_instant_baseline/analysis_rules_v4.json';s['analysis_rules_sha256']=sha(cfg/'analysis_rules_v4.json');s['configuration_sha256']=sha(cfg/'effective_E.json')
        s['revision_reason']=rules['revision_reason'];dest=rel.replace('_'+old+'.json','_'+s['run_id']+'.json');save(root/dest,s);new.append(dest)
    order[phase]=new
oldbatches=order['batches'];order['batches']=[b.replace('_v3','_v4') for b in oldbatches]
for i,(old,new) in enumerate(zip(oldbatches,order['batches'])):
    b=json.loads((cfg/(old+'.json')).read_text());b['batch_id']=new;b['previous_batch']=order['batches'][i-1] if i else None
    b['specs']=[p.replace('_q03.json','_q04.json').replace('_main_v3.json','_main_v4.json') for p in b['specs']]
    b['revision_reason']=rules['revision_reason'];save(cfg/(new+'.json'),b)
# A single justified D intervention: installed startup default history=8, retaining all output/compensation settings.
assert p['result']['startup_history_count_without_launch_override']==8
d=json.loads(json.dumps(frozen));d.update(schema_version=1,intervention={'setting':'/rtx/scenedb/maxHistoryTransformCount','E':64,'D':8,
    'reason':'Restore installed startup default measured without launch override; retain Motion BVH, Multi-Tick and per-sensor TLAS to preserve output semantics.',
    'evidence':str(probe.relative_to(root)),'evidence_sha256':sha(probe)})
d['requested_settings']['/rtx/scenedb/maxHistoryTransformCount']=8;d['observed']['effective']['settings']['/rtx/scenedb/maxHistoryTransformCount']=8
d['observed_note']='Expected effective fingerprint, to be verified in every D capture; only default history=8 has been observed at startup.'
save(cfg/'effective_D.json',d)
for phase,profiles,repeats,N,rid in [('D_qualification',['S0','S5','R3P'],['r01'],12,'q04'),('D_main',['S0','R3P'],['r01','r02','r03'],100,'main_v4')]:
    specs=[]
    for profile in profiles:
        for repeat in repeats:
            template=next(json.loads((root/r).read_text()) for r in order['qualification' if N==12 else 'main'] if json.loads((root/r).read_text())['group']=='M_E' and json.loads((root/r).read_text())['profile']==profile)
            s=template;s.update(group='M_D',repeat=repeat,requested_settings=d['requested_settings'],configuration_sha256=sha(cfg/'effective_D.json'),
                launch_overrides=['--/rtx/scenedb/maxHistoryTransformCount=8'],output_relative='reports/native_instant_baseline/%s/M_D/%s/%s/%s'%(order['experiment_id'],profile,repeat,rid))
            rel='config/native_instant_baseline/specs/M_D_%s_%s_%s.json'%(profile,repeat,rid);save(root/rel,s);specs.append(rel)
    order[phase]=specs
    for i in range(0,len(specs),3):
        bid='native005_'+phase.lower()+'_%02d_v4'%(i//3+1)
        save(cfg/(bid+'.json'),{'batch_id':bid,'experiment_id':order['experiment_id'],'phase':phase,'specs':specs[i:i+3],'free_reserve_bytes':8*1024**3,'previous_batch':order['batches'][-1]})
        order['batches'].append(bid)
order['D_status']='Predeclared history 64->8 only; 3 short qualifications then S0/R3P 100x3, fixed order.'
order['supersedes_unrun_order']='run_order_v3.json; all q01/q02/q03 evidence preserved';save(cfg/'run_order.json',order)
print(json.dumps({'new_batches':order['batches'],'E_sha256':sha(cfg/'effective_E.json'),'D_sha256':sha(cfg/'effective_D.json')}))
