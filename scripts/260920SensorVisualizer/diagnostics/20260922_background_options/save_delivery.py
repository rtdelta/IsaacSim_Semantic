import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
response=json.loads((HERE/'restoration.json').read_text(encoding='utf-8-sig'))
assert response['status']=='succeeded'
result=json.loads(response['result']['stdout'])
assert result['exit_code']==0, result['stderr']
data=json.loads(result['stdout']);report=data['report']
folder=ROOT/'reports/background_options'/Path(report['backup']).parent.name
folder.mkdir(parents=True,exist_ok=True)
name=Path(report['scene']).name
for filename,text,expected in [(name,data['scene_text'],report['scene_sha256']),
                               ('before_'+name,data['before_scene_text'],report['before_sha256'])]:
    raw=text.encode('utf-8')
    assert hashlib.sha256(raw).hexdigest()==expected
    (folder/filename).write_bytes(raw)
(folder/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(ROOT/'scenes').mkdir(exist_ok=True)
(ROOT/'scenes'/name).write_bytes(data['scene_text'].encode('utf-8'))
print(json.dumps(dict(local_report=str(folder),scene_sha256=report['scene_sha256'])))
