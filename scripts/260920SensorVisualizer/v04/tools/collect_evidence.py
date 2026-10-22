"""Local evidence collection through the reviewed SSH audit wrapper."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--ops',required=True);args=parser.parse_args()
proc=subprocess.run([sys.executable,'-X','utf8',args.ops,'exec','--target','isaac-new','--task','sv04-deploy-20261008',
    '--purpose','Collect task-owned native acceptance evidence','--script',str(ROOT/'tools/remote_collect_evidence.py'),
    '--intent','read','--timeout','30'],capture_output=True,text=True,encoding='utf-8',timeout=60)
if proc.returncode:raise RuntimeError(proc.stderr or proc.stdout)
envelope=json.loads(proc.stdout)
if envelope.get('result',{}).get('exit_code')!=0:raise RuntimeError(proc.stdout)
data=json.loads(envelope['result']['stdout'])
data['collection_audit']={k:envelope[k] for k in ('operation_id','audit_log','status')}
path=ROOT/'reports/native_evidence.json';path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'path':str(path),'runs':len(data['runs']),'active':data['active_task_processes']}))
