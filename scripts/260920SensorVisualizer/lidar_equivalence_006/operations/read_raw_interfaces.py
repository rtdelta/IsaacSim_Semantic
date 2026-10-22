import json
from pathlib import Path
root=Path('/root/isaacsim');rows=[]
bases=[root/'exts/isaacsim.sensors.experimental.rtx',root/'exts/isaacsim.sensors.rtx.nodes']
for base in bases:
 for p in base.rglob('*'):
  if not p.is_file() or p.suffix not in ('.py','.h','.hpp','.ogn','.pyi'):continue
  if p.stat().st_size>200000:continue
  s=p.read_text(errors='replace')
  if any(x in s for x in ('GenericModelOutput','generic_model_output','frameId')) and ('Database' not in p.name):
   lines=s.splitlines();hits=[i for i,l in enumerate(lines) if any(x in l for x in ('def get_data','class Generic','frameId','gmo','GenericModelOutput','def get_frame','def get_scan'))]
   if hits:rows.append({'path':str(p),'snippets':'\n'.join('\n'.join(lines[max(0,i-5):i+18]) for i in hits[:15])})
print(json.dumps(rows))
