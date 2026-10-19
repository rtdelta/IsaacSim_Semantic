"""Exercise actual HTTP -> IPC -> native Timeline, then leave the GUI paused and idle."""
import json
from pathlib import Path
import time
import urllib.request
import uuid

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
report=json.loads((root/'reports/ready_v002.json').read_text())
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
base='http://127.0.0.1:17877'
def status():return json.load(opener.open(base+'/api/status',timeout=3))['engine']
engine=status()
if engine.get('phase')!='interactive_ready':
    print(json.dumps({'state':'waiting','phase':engine.get('phase'),'error':engine.get('error')}))
    raise SystemExit(0)
assert engine['metadata']['implementation_version']=='0.2.0'
html=opener.open(base,timeout=3).read().decode()
configuration=html.split('window.CONTROL_TOKEN',1)[1].split('=',1)[1].split(';',1)[0]
csrf_value=json.loads(configuration)
def command(action,payload=None):
    identifier=uuid.uuid4().hex
    body=json.dumps({'action':action,'payload':payload or {},'command_id':identifier}).encode()
    message=urllib.request.Request(base+'/api/command',data=body,headers={'Content-Type':'application/json'})
    message.add_header('X-S0602-Token',csrf_value)
    accepted=json.load(opener.open(message,timeout=3));assert accepted['state']=='queued',accepted
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        current=status()
        for receipt in current.get('receipts',[]):
            if receipt['command_id']==identifier:
                assert receipt['state']=='applied',receipt
                return current
        time.sleep(.1)
    raise TimeoutError('No applied receipt for '+action)
command('play');command('keyboard',{'enabled':True})
before=status()['state']['t_sim_s'];time.sleep(.6);after=status()
assert after['playing'] and after['state']['t_sim_s']>before
command('keyboard',{'enabled':False});command('hold')
before=status()['state']['t_sim_s'];time.sleep(.6);after=status()
assert after['playing'] and after['state']['t_sim_s']>before
command('pause');command('stop');command('play')
deadline=time.monotonic()+10
while not status().get('binding_ready') and time.monotonic()<deadline:time.sleep(.1)
assert status().get('binding_ready')
command('pause');final=status()
assert final['simulation_state']=='paused' and not final['playing'] and not final['keyboard_enabled']
assert not final['recording'] and not final['trajectory_draining']
report.update(state='ready',web_smoke_passed=True,simulation_state=final['simulation_state'],
    keyboard_enabled=final['keyboard_enabled'],recording=final['recording'],
    binding_ready=final['binding_ready'],session_id=final['session_id'],
    implementation_version=final['metadata']['implementation_version'])
(root/'reports/ready_v002.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
