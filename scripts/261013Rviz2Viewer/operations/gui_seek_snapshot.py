import json, subprocess, time, urllib.request
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
request=urllib.request.Request('http://127.0.0.1:8767/api/control',data=json.dumps({'action':'seek','group':150}).encode(),headers={'Content-Type':'application/json'})
assert urllib.request.urlopen(request,timeout=5).status==202
time.sleep(2)
status=json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=5))
assert status['group']==150 and not status['error'],status
result=subprocess.run(['/usr/bin/python3',str(root/'screenshot_rviz.py'),str(root/'reports/rviz_frame150.png')],capture_output=True,text=True,timeout=20)
print(json.dumps({'status':status,'screenshot_result':result.stdout,'stderr':result.stderr,'exit_code':result.returncode}))
assert result.returncode==0
