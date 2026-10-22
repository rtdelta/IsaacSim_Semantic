"""Transfer reviewed project files with optimistic conflict checks and backups."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
OPS=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py')
FILES=['sensor_visualizer/unified_bag.py','sensor_visualizer/performance.py','sensor_visualizer/bag_export.py',
 'sensor_visualizer/camera_capture.py','sensor_visualizer/camera_rig.py','sensor_visualizer/simulation_pacing.py',
 'sensor_visualizer/recording.py','sensor_visualizer/articulation_motion.py','sensor_visualizer/runtime.py',
 'config/sensors.json','tools/build_surround_stage.py','tools/pack_session_mcap.py','tools/monitor_resources.py',
 'tools/test_unified_bag.py','tools/validate_unified_runtime.py','docs/unified_mcap_and_performance.md','README.md']
if len(sys.argv)>1:FILES=sys.argv[1:]
probe=json.loads(json.loads((HERE/'probe_result.json').read_text(encoding='utf-8-sig'))['result']['stdout'])
state_path=HERE/'deployed.json'
baseline=json.loads(state_path.read_text()) if state_path.exists() else probe['files']
payload=[]
for name in FILES:
    raw=(ROOT/name).read_bytes().replace(b'\r\n',b'\n')
    payload.append(dict(path=name,expected=baseline.get(name),sha256=hashlib.sha256(raw).hexdigest(),content=base64.encodebytes(raw).decode()))
script='''import base64, hashlib, json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer').resolve()
rows=json.loads(DATA)
prepared=[]
for row in rows:
 p=(root/row['path']).resolve()
 if not p.is_relative_to(root):raise ValueError('Outside project')
 before=p.read_bytes() if p.exists() else None
 old=hashlib.sha256(before.replace(b'\\r\\n',b'\\n')).hexdigest() if before is not None else None
 if old not in [row['expected'],row['sha256']]:raise ValueError('Unreviewed concurrent change: '+row['path'])
 raw=base64.b64decode(row['content'])
 if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Transfer mismatch')
 prepared.append((row,p,before,raw))
for row,p,before,raw in prepared:
 backup=root/'reports/unified_bag/before'/row['path']
 if before is not None and not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(before)
 p.parent.mkdir(parents=True,exist_ok=True)
 temp=p.with_name(p.name+'.unified-upload');temp.write_bytes(raw);temp.replace(p)
path=root/'reports/unified_bag/deployment.json';path.parent.mkdir(parents=True,exist_ok=True)
report={r['path']:r for r in json.loads(path.read_text())} if path.exists() else {}
for r in rows:
 item={k:v for k,v in r.items() if k!='content'}
 backup=root/'reports/unified_bag/before'/r['path']
 item['original_sha256']=hashlib.sha256(backup.read_bytes()).hexdigest() if backup.exists() else None
 report[r['path']]=item
path.write_text(json.dumps(list(report.values()),indent=2))
print(json.dumps({'files':len(rows),'verified':all(hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'] for r,p,_,_ in prepared)}))
'''.replace('DATA',repr(json.dumps(payload)))
source=HERE/'deploy_payload.py';source.write_text(script,encoding='utf-8')
r=subprocess.run([sys.executable,'-X','utf8',str(OPS),'exec','--target','isaac-new','--task','unified-mcap-20260922',
 '--purpose','Deploy camera MCAP packaging and bounded performance instrumentation with baseline checks and backups',
 '--script',str(source),'--intent','write','--timeout','45'],capture_output=True,text=True,encoding='utf-8')
(HERE/'deployment_result.json').write_text(r.stdout,encoding='utf-8')
result=json.loads(r.stdout)
if r.returncode or result.get('result',{}).get('exit_code')!=0:print(json.dumps(result,ensure_ascii=False));raise SystemExit(1)
baseline.update({r['path']:r['sha256'] for r in payload});state_path.write_text(json.dumps(baseline,indent=2))
print(json.dumps({'status':result['status'],'result':result['result']['stdout'],'audit_log':result['audit_log']}))
