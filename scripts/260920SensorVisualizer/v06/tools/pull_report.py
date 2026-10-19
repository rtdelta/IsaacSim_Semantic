"""Pull only generated report JSON through the configured audited target alias."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('script');p.add_argument('destination');p.add_argument('--task',default='sensor-perf-pull');p.add_argument('--purpose',default='读取本任务生成的脱敏性能报告并存档');p.add_argument('--timeout',default='180');a=p.parse_args()
ops=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py')
r=subprocess.run([sys.executable,'-X','utf8',str(ops),'exec','--target','isaac-new','--task',a.task,'--purpose',a.purpose,'--script',str(Path(a.script).resolve()),'--intent','write','--timeout',a.timeout],capture_output=True,text=True,encoding='utf-8')
if r.returncode:raise RuntimeError(r.stdout[-2000:]+r.stderr[-2000:])
operation=json.loads(r.stdout);assert operation['status']=='succeeded',operation
result=operation['result'];assert result['exit_code']==0 and not any(result.get('output_omitted',[])),result
data=json.loads(result['stdout']);destination=Path(a.destination);destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'saved':str(destination.resolve()),'bytes':destination.stat().st_size,'operation_id':operation['operation_id']}))
