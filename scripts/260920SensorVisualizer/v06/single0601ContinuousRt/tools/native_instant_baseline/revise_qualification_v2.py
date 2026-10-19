"""Retain q01 failure; fresh q02 after bounded-GMO-span decoder correction."""
import json,shutil
from pathlib import Path
from tools.native_instant_baseline.io import save,sha
root=Path(__file__).resolve().parents[2];cfg=root/'config/native_instant_baseline'
order=json.loads((cfg/'run_order.json').read_text());save(cfg/'run_order_v1.json',order)
rules=json.loads((cfg/'analysis_rules_v1.json').read_text());rules.update(schema_version=2,
    revision_reason='ABI buffer allocation can exceed serialized GMO header size; all original bytes retained; field bounds and final cursor must match declared span. All numeric thresholds unchanged.')
save(cfg/'analysis_rules_v2.json',rules)
for phase in ('qualification','main'):
    new=[]
    for rel in order[phase]:
        s=json.loads((root/rel).read_text());old=s['run_id'];s['run_id']='q02' if phase=='qualification' else 'main_v2'
        s['output_relative']=s['output_relative'].rsplit('/',1)[0]+'/'+s['run_id'];s['analysis_rules_path']='config/native_instant_baseline/analysis_rules_v2.json';s['analysis_rules_sha256']=sha(cfg/'analysis_rules_v2.json')
        s['revision_reason']=rules['revision_reason'];dest=rel.replace('_'+old+'.json','_'+s['run_id']+'.json');save(root/dest,s);new.append(dest)
    order[phase]=new
oldbatches=order['batches'];order['batches']=[b.replace('_v1','_v2') for b in oldbatches]
for i,(old,new) in enumerate(zip(oldbatches,order['batches'])):
    b=json.loads((cfg/(old+'.json')).read_text());b['batch_id']=new;b['previous_batch']=order['batches'][i-1] if i else None
    b['specs']=[p.replace('_q01.json','_q02.json').replace('_main_v1.json','_main_v2.json') for p in b['specs']]
    b['revision_reason']=rules['revision_reason'];save(cfg/(new+'.json'),b)
order['supersedes_unrun_order']='run_order_v1.json; q01 failure and its raw data preserved';save(cfg/'run_order.json',order)
print(json.dumps({'new_batches':order['batches']}))
