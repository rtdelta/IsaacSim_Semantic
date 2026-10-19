"""Extract only this task's already-redacted evidence from local audit records."""
from pathlib import Path
import argparse,json
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('audit_directory');a=p.parse_args()
records=[];by_id={}
for file in Path(a.audit_directory).glob('*.jsonl'):
    rows=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
    if not rows or rows[0].get('data',{}).get('task')!='sv04-deploy-20261008':continue
    first=rows[0];last=rows[-1]
    row={'operation_id':first['operation_id'],'time_utc':first['time_utc'],
         'purpose':first['data'].get('purpose'),'final_event':last['event'],
         'result':last.get('data',{}),'audit_file':str(file)}
    records.append(row);by_id[first['operation_id']]=rows
dest=ROOT/'reports';dest.mkdir(exist_ok=True)
(dest/'operations.json').write_text(json.dumps(sorted(records,key=lambda r:r['time_utc']),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for operation,name in [('20261008T072252Z_86c9bd37d92f','gui_acceptance_status.json'),
                       ('20261008T072318Z_ec37244ac0b1','gui_validation_results.json')]:
    rows=by_id[operation]
    result=[r['data'] for r in rows if r['event']=='ssh.command.completed'][-1]
    value=json.loads(result['stdout'])
    (dest/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'operations':len(records),'directory':str(dest)}))
