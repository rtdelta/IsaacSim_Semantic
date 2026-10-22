"""Deploy explicit task files via the existing audited SSH script transport."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
OPS=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py')
FILES=['sensor_visualizer/base_control.py','sensor_visualizer/base_panel.py',
       'sensor_visualizer/tilt_panel.py','sensor_visualizer/articulation_motion.py',
       'sensor_visualizer/camera_capture.py','sensor_visualizer/runtime.py',
       'config/terrain.json','tools/build_terrain_blender.py','tools/build_terrain_stage.py',
       'tools/open_terrain_stage.sh','tools/test_base_control.py']
if len(sys.argv)>1:FILES=sys.argv[1:]
state_path=HERE/'deployed_expected.json'
state=json.loads(state_path.read_text()) if state_path.exists() else {}
payload=[]
for name in FILES:
    p=ROOT/name
    if not p.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Outside project')
    raw=p.read_bytes().replace(b'\r\n',b'\n')
    before=ROOT/'reports/tilt_terrain/before'/name
    previous=state.get(name,hashlib.sha256(before.read_bytes().replace(b'\r\n',b'\n')).hexdigest() if before.exists() else None)
    payload.append({'path':name,'expected_before':previous,'sha256':hashlib.sha256(raw).hexdigest(),
                    'content':base64.encodebytes(raw).decode()})
script='''import base64,hashlib,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer').resolve()
rows=json.loads(DATA)
prepared=[]
for row in rows:
 p=(root/row['path']).resolve()
 if root not in p.parents:raise ValueError('Outside project')
 raw=base64.b64decode(row['content']);before=p.read_bytes() if p.exists() else None
 old=hashlib.sha256(before.replace(b'\\r\\n',b'\\n')).hexdigest() if before is not None else None
 if old not in [row['expected_before'],row['sha256']]:raise ValueError('Concurrent or unreviewed change: '+row['path'])
 if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Transfer hash mismatch')
 prepared.append((row,p,raw,before))
for row,p,raw,before in prepared:
 b=root/'reports/tilt_terrain/before'/row['path']
 if before is not None and not b.exists():b.parent.mkdir(parents=True,exist_ok=True);b.write_bytes(before)
 p.parent.mkdir(parents=True,exist_ok=True)
 temp=p.with_name(p.name+'.tilt-terrain-upload');temp.write_bytes(raw);temp.replace(p)
manifest=[{k:v for k,v in r.items() if k!='content'} for r in rows]
report=root/'reports/tilt_terrain/deployment_latest.json';report.parent.mkdir(parents=True,exist_ok=True)
report.write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest))
'''.replace('DATA',repr(json.dumps(payload)))
script_path=HERE/'deploy_payload.py';script_path.write_text(script,encoding='utf-8')
r=subprocess.run([sys.executable,'-X','utf8',str(OPS),'exec','--target','isaac-new','--task','tilt-terrain-20260922',
    '--purpose','Deploy reviewed project code with baseline checks, backups and content hashes','--script',str(script_path),
    '--intent','write','--timeout','40'],capture_output=True,text=True,encoding='utf-8')
(HERE/'deployment_result.json').write_text(r.stdout,encoding='utf-8')
out=json.loads(r.stdout)
if r.returncode or out.get('result',{}).get('exit_code')!=0:
    print(json.dumps(out,ensure_ascii=False));raise SystemExit(1)
for row in payload:state[row['path']]=row['sha256']
state_path.write_text(json.dumps(state,indent=2))
print(json.dumps({'status':out['status'],'files':len(payload),'audit_log':out['audit_log']}))
