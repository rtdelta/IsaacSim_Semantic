"""Audited sequential chunk transfer and checked promotion; no package downloads."""
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'-X','utf8',str(root/'tools/build_deployment.py')],check=True)
plan=json.loads((root/'reports/deployment/upload_plan.json').read_text());ops=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py')
for index,script in enumerate(plan['upload_scripts']+[plan['promote']]):
    r=subprocess.run([sys.executable,'-X','utf8',str(ops),'exec','--target','isaac-new','--task','sensor-perf-deploy-v06-'+str(index),
        '--purpose','传输本项目生成的源代码分块并校验提升v06，保留v05与资产','--script',script,'--intent','write','--timeout','60'],capture_output=True,text=True,encoding='utf-8')
    if r.returncode:raise RuntimeError('Deployment did not complete; verify current state before retry: '+r.stdout[-2000:]+r.stderr[-1000:])
    operation=json.loads(r.stdout);assert operation['status']=='succeeded' and operation['result']['exit_code']==0,operation
    print(json.dumps({'operation_id':operation['operation_id'],'result':json.loads(operation['result']['stdout'])}))
