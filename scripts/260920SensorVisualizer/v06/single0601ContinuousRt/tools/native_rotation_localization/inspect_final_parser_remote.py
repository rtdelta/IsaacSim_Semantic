import json,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_rotation_localization/native007_20261015_v1');out={}
p=root/'final_metadata_crosscheck.json'
if p.is_file():
 d=json.loads(p.read_text());out['result']={k:v for k,v in d.items() if k!='files'};out['errors']=[r for r in d['files'] if not r['passed']][:3]
p=root/'final_metadata_crosscheck.log'
if p.is_file():out['log_tail']=p.read_text(errors='replace')[-2000:]
out['kit_processes']=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  c=(p/'cmdline').read_bytes()
  if b'/kit/kit' in c:out['kit_processes'].append({'pid':p.name,'status':[l for l in (p/'status').read_text().splitlines() if l.startswith(('State:','VmRSS:','Threads:'))]})
 except OSError:pass
print(json.dumps(out))
