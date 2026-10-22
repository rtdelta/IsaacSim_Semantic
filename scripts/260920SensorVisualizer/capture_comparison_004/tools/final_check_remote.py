"""Verify preserved sources and scene; inspect remaining owned processes. No kill."""
import hashlib,json,shutil,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004')
info=json.loads((root/'reports/latest_suite.json').read_text());out=Path(info['directory']);progress=json.loads((out/'progress.json').read_text())
old=json.loads((root/'reports/preserved_remote.json').read_text());changed=[]
for rel,want in old.items():
 p=root.parent/rel
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=want:changed.append(rel)
initial=json.loads((out/'suite_sources.json').read_text());runtime={k:v for k,v in initial.items() if k.startswith('engines/') or k in ('suite.py','config/suite.json','tools/decode_case.py')}
runtime_changed=[rel for rel,want in runtime.items() if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=want]
spec=json.loads((out/'suite_spec.json').read_text());scene_hash=hashlib.sha256(Path(spec['scene']).read_bytes()).hexdigest()
owned=[];kits=[];viewers=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  raw=p.read_bytes();args=raw.split(b'\0')
  if not args:continue
  if args[0].endswith(b'/kit/kit'):kits.append(int(p.parent.name))
  if any(str(out).encode() in a or str(root/'suite.py').encode()==a for a in args):
   item={'pid':int(p.parent.name),'executable':args[0].decode(errors='replace')}
   # A user viewing an output PNG is not a surviving capture worker.
   (viewers if Path(item['executable']).name in {'ristretto','eog','gwenview','feh'} else owned).append(item)
 except OSError:pass
gpu=subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15)
r={'suite_state':progress['state'],'completed_cases':len(progress['completed_cases']),'preserved_source_count':len(old),'preserved_source_changes':changed,'runtime_source_changes':runtime_changed,
 'root_usd_sha256':scene_hash,'root_usd_unchanged':scene_hash==spec['scene_sha256'],'remaining_owned_processes':owned,'output_viewer_processes_left_untouched':viewers,'active_kit_pids':kits,'gpu_query':gpu.stdout.strip(),'gpu_query_exit':gpu.returncode,
 'free_gib':shutil.disk_usage(out).free/1024**3,'limits':['Only preserved source manifest and root USD have before/after hash proof.','Not a whole-system security or disk-asset audit.']}
(out/'final_integrity.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
if progress['state']!='completed' or changed or runtime_changed or not r['root_usd_unchanged'] or owned:raise SystemExit(2)
