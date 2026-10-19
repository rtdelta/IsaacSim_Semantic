import json,sys,time,uuid
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
info=json.loads((root/'reports/native_owner/owner.json').read_text());sock=info['socket'];assert 'test_engine.sock' in sock
def status():return request(sock,{'action':'status'})
def command(action,payload=None):
    cid=uuid.uuid4().hex;request(sock,{'action':action,'payload':payload or {},'command_id':cid});end=time.monotonic()+45
    while time.monotonic()<end:
        s=status();r=next((r for r in s.get('receipts',[]) if r['command_id']==cid),None)
        if r:return r,s
        time.sleep(.1)
    raise TimeoutError(action)
for _ in range(2):
    r,s=command('exit');assert r['state']=='applied' and s['phase']=='exited',(r,s)
    r,s=command('play');assert r['state']=='failed'
    r,s=command('reinitialize');assert r['state']=='applied' and s['phase']=='interactive_ready',(r,s)
    r,s=command('play');assert r['state']=='applied' and s['playing']
    r,s=command('stop');assert r['state']=='applied' and s['motion_state']=='stopped'
report={'passed':True,'exit_reinitialize_cycles':2,'socket_preserved':Path(sock).exists(),'final_phase':s['phase'],'final_motion_state':s['motion_state']}
(root/'reports/native_owner/lifecycle_fix.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
