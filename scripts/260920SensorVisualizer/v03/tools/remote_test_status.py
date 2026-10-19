from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03')
info=json.loads((root/'reports/latest_test.json').read_text());out=Path(info['directory']);result=dict(info)
for name in ('phase.json','supervisor_result.json','process.json'):
    p=out/name
    if p.exists():result[name]=json.loads(p.read_text())
p=out/'acceptance.json'
if p.exists():
    doc=json.loads(p.read_text())
    result['acceptance']={k:v for k,v in doc.items() if k not in ('assets_before','captures')}
    result['captures']=[{k:v for k,v in c.items() if k not in ('writer','requested_updates_after')} for c in doc['captures']]
p=out/'kit.log'
if p.exists():
    lines=p.read_text(errors='replace').splitlines()
    issues=[l for l in lines if any(s in l for s in ('[SV03','Traceback','Error:','Exception:','[Error]'))]
    result['kit_log']={'bytes':p.stat().st_size,'tail':lines[-8:],'issues':issues[-20:]}
p=out/'supervisor.log'
if p.exists() and p.stat().st_size:result['supervisor_tail']=p.read_text(errors='replace')[-3000:]
print(json.dumps(result))
