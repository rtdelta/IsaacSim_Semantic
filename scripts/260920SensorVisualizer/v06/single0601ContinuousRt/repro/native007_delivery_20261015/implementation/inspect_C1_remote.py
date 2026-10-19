import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');p=root/'reports/native_rotation_localization/native007_20261015_v1/C1/S0/r01/cq01'
out={'files':[str(f.relative_to(p)) for f in p.rglob('*') if f.is_file()]}
for name in ('continuous_terminal.json','coordinator_status.json','official_parser_crosscheck.json'):
 f=p/name
 if f.is_file():
  d=json.loads(f.read_text());out[name]={k:v for k,v in d.items() if k!='files'}
for name in ('launch.log','analysis.log'):
 f=p/name
 if f.is_file():
  t=f.read_text(errors='replace');out[name+'_tail']=t[-7000:];out[name+'_relevant']=[l for l in t.splitlines() if any(s in l.lower() for s in ('error','exception','traceback','critical','unsupported','accumulate'))][-35:]
print(json.dumps(out))
