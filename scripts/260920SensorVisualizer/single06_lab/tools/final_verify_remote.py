"""Read-only formal-source and owned-process audit after tests and deployment."""
import hashlib,json,os,zipfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
baseline=root/'backups/single06_before_lab_20261011_101200.zip'
changed=[];checked=0
with zipfile.ZipFile(baseline) as z:
 for rel in z.namelist():
  if rel.endswith('/'):continue
  p=root/'v06'/rel
  if not p.resolve().is_relative_to(root/'v06'):raise RuntimeError('Unsafe baseline member')
  checked+=1
  if not p.is_file() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(z.read(rel)).digest():changed.append(rel)
frozen=[]
for p in (root/'single06_lab/frozen_runtime').rglob('*'):
 if not p.is_file() or '__pycache__' in p.parts:continue
 original=root/'v06'/p.relative_to(root/'single06_lab/frozen_runtime')
 if not original.is_file() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(original.read_bytes()).digest():frozen.append(p.name)
live=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  cmd=(p/'cmdline').read_bytes();cwd=Path(os.readlink(p/'cwd'))
  if b'single06_lab/kit_' in cmd or cwd.is_relative_to(root/'single06_lab'):
   live.append({'pid':int(p.name),'executable':cmd.split(b'\0')[0].decode(errors='replace'),'cwd':str(cwd)})
 except (OSError,ValueError):pass
print(json.dumps({'formal_files_checked':checked,'formal_changes':changed,'frozen_source_mismatches':frozen,
 'live_project_processes':live,'passed':not changed and not frozen and not live},indent=2))
