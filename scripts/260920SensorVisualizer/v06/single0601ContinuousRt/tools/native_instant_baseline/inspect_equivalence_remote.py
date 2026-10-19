import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
frozen=json.loads((root/'config/native_instant_baseline/effective_E.json').read_text())['observed']
order=json.loads((root/'config/native_instant_baseline/run_order.json').read_text())
def diff(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        return [x for k in sorted(set(a)|set(b)) for x in diff(a.get(k),b.get(k),path+'/'+k)]
    if a!=b:return [{'field':path,'frozen':a,'actual':b}]
    return []
for s in order['qualification']:
    spec=json.loads((root/s).read_text());p=root/spec['output_relative']/'continuous/configuration_fingerprint.json'
    if p.exists():print(json.dumps({'spec':s,'differences':diff(frozen,json.loads(p.read_text()))}))
