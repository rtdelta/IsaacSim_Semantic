import json,subprocess
from pathlib import Path
rows=[]
for base in (Path('/root/isaacsim/exts'),Path('/root/isaacsim/extscache')):
 for d in base.glob('omni.replicator.core*'):
  p=d/'omni/replicator/core/scripts/orchestrator.py'
  if p.exists():
   lines=p.read_text().splitlines();indices=set()
   for i,l in enumerate(lines):
    if any(x in l for x in ('def start(', 'def start_async','def _get_pt_subframes_per_frame','def _validate_pt_settings','def get_status','def run(')):
     indices.update(range(max(0,i-3),min(len(lines),i+95)))
   indices.update(range(535,605));indices.update(range(1720,1775))
   rows.append({'path':str(p),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indices))})
  for name in ('scripts/settings.py','scripts/writers_default/basicwriter.py'):
   p=d/'omni/replicator/core'/name
   if not p.exists():continue
   lines=p.read_text().splitlines();indices=set()
   for i,l in enumerate(lines):
    if any(x in l for x in ('def set_render_pathtraced','def write(', 'def __init__','_frame_id','ReferenceTime','metadata','on_final_frame')):indices.update(range(max(0,i-3),min(len(lines),i+70)))
   if indices:rows.append({'path':str(p),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indices))[:18000]})
 for d in base.glob('omni.usd*'):
  for p in d.rglob('*.pyi'):
   lines=p.read_text(errors='replace').splitlines();indices=set()
   for i,l in enumerate(lines):
    if any(x in l.lower() for x in ('rendering_progress','rendering_status','sample_count','accumulation','frame_number')):indices.update(range(max(0,i-3),min(len(lines),i+18)))
   if indices:rows.append({'path':str(p),'text':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indices))})
procs=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  first=p.read_bytes().split(b'\0')[0]
  if first.endswith(b'/kit/kit'):procs.append({'pid':int(p.parent.name),'executable':first.decode()})
 except OSError:pass
print(json.dumps({'processes':procs,'gpu':subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used','--format=csv,noheader'],capture_output=True,text=True).stdout,'sdk':rows}))
