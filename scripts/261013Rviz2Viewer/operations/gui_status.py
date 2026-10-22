import json, urllib.request
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
result={}
for name in ('gui_process.json',):
    p=root/'reports'/name
    if p.exists():result[name]=json.loads(p.read_text()) if name.endswith('.json') else p.read_text()[-4000:]
if result.get('gui_process.json'):
    log=Path(result['gui_process.json']['log'])
    if log.is_file():result['gui_stdout.log']=log.read_text()[-4000:]
try:result['web_status']=json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=5))
except Exception as exc:result['web_error']=str(exc)
print(json.dumps(result))
