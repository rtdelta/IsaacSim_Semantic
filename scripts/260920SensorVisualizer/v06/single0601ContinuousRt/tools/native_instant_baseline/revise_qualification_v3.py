"""Preserve q02; align configuration snapshot lifecycle and enforce all-event timing."""
import json
from pathlib import Path
from tools.native_instant_baseline.io import save,sha
root=Path(__file__).resolve().parents[2];cfg=root/'config/native_instant_baseline'
if (cfg/'run_order_v2.json').exists():raise RuntimeError('Already revised')
order=json.loads((cfg/'run_order.json').read_text());save(cfg/'run_order_v2.json',order)
rules=json.loads((cfg/'analysis_rules_v2.json').read_text());rules.update(schema_version=3,
    revision_reason='Read effective configuration after the fixed 24-update warmup, matching E probe lifecycle; preserve before-warmup snapshot. Enforce unique time association for every raw event, including warmup/drain. Account P baseline trace bytes and use current initialization RSS. All numeric thresholds and requested settings unchanged.')
save(cfg/'analysis_rules_v3.json',rules)
for phase in ('qualification','main'):
    new=[]
    for rel in order[phase]:
        s=json.loads((root/rel).read_text());old=s['run_id'];s['run_id']='q03' if phase=='qualification' else 'main_v3'
        s['output_relative']=s['output_relative'].rsplit('/',1)[0]+'/'+s['run_id'];s['analysis_rules_path']='config/native_instant_baseline/analysis_rules_v3.json';s['analysis_rules_sha256']=sha(cfg/'analysis_rules_v3.json')
        s['revision_reason']=rules['revision_reason'];dest=rel.replace('_'+old+'.json','_'+s['run_id']+'.json');save(root/dest,s);new.append(dest)
    order[phase]=new
oldbatches=order['batches'];order['batches']=[b.replace('_v2','_v3') for b in oldbatches]
for i,(old,new) in enumerate(zip(oldbatches,order['batches'])):
    b=json.loads((cfg/(old+'.json')).read_text());b['batch_id']=new;b['previous_batch']=order['batches'][i-1] if i else None
    b['specs']=[p.replace('_q02.json','_q03.json').replace('_main_v2.json','_main_v3.json') for p in b['specs']]
    b['revision_reason']=rules['revision_reason'];save(cfg/(new+'.json'),b)
order['supersedes_unrun_order']='run_order_v2.json; all q01/q02 evidence preserved';save(cfg/'run_order.json',order)
print(json.dumps({'new_batches':order['batches']}))
