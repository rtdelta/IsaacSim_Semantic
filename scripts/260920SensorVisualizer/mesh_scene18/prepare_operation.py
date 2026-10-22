"""Prepare audited operations from locally reviewed project source, without secrets."""
import argparse,base64,hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
REMOTE='/root/gpufree-data/semantic/scripts/260920SensorVisualizer'
p=argparse.ArgumentParser()
p.add_argument('mode',choices=['analyze','deploy','build','validate'])
a=p.parse_args()
(HERE/'operations').mkdir(exist_ok=True)
if a.mode=='deploy':
    sources=[*sorted(HERE.glob('*.py')),HERE/'README.md',PROJECT/'docs/20261012_scene17_mesh_excavator_implementation_plan.md',PROJECT/'docs/20261012_scene18_mesh_excavator_execution_report.md']
    files={str(f.relative_to(PROJECT)).replace('\\','/'):{'text':f.read_text(encoding='utf-8'),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sources if f.name!='prepare_operation.py'}
    code='''import hashlib,json,datetime,shutil
from pathlib import Path
root=Path(REMOTE).resolve()
files=FILES
written=[]
for rel,item in files.items():
 target=root/rel
 assert target.resolve().is_relative_to(root)
 data=item['text'].encode('utf-8')
 assert hashlib.sha256(data).hexdigest()==item['sha256']
 if target.exists() and target.read_bytes()!=data:
  backup=root/'mesh_scene18/backups'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')/rel
  backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
 target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 assert hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']
 written.append({'path':str(target),'sha256':item['sha256']})
print(json.dumps({'deployed':written}))
'''.replace('REMOTE',repr(REMOTE)).replace('FILES',repr(files))
elif a.mode=='analyze':
    source=(HERE/'analyze_alignment.py').read_text(encoding='utf-8')
    code=(HERE/'runtime.py').read_text(encoding='utf-8')+'\n'+f'p=run({source!r});print(p.stdout);print(p.stderr);raise SystemExit(p.returncode)\n'
else:
    source=REMOTE+'/mesh_scene18/'+('build_assets.py' if a.mode=='build' else 'validate_assets.py')
    code=(HERE/'runtime.py').read_text(encoding='utf-8')+'\n'+f'p=run(Path({source!r}).read_text(), timeout=180);print(p.stdout);print(p.stderr);raise SystemExit(p.returncode)\n'
target=HERE/'operations'/f'{a.mode}_remote.py'
target.write_text(code,encoding='utf-8')
print(target)
