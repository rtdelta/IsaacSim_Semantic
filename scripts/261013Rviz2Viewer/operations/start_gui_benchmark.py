import json,time,urllib.request
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
def command(value):
    req=urllib.request.Request('http://127.0.0.1:8767/api/control',data=json.dumps(value).encode(),headers={'Content-Type':'application/json'})
    assert urllib.request.urlopen(req,timeout=5).status==202
command({'action':'seek','group':0})
time.sleep(1)
command({'action':'play'})
print(json.dumps({'started':time.time_ns(),'status':json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=5))}))
