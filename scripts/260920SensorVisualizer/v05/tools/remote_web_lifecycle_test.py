"""Loopback HTTP -> IPC -> real owner receipts; never expose the control token."""
import json,sys,threading,time,urllib.request,uuid
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05');sys.path.insert(0,str(root))
from sensor_visualizer_v05.web_service import WebService,make_server
directory=root/'reports/native_owner';owner=json.loads((directory/'owner.json').read_text())
service=WebService(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v05',owner['socket'])
server=make_server(service,port=17866);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));url='http://127.0.0.1:17866';checks=[]
def command(action,payload=None,expected='applied'):
    cid=uuid.uuid4().hex
    req=urllib.request.Request(url+'/api/command',json.dumps({'action':action,'payload':payload or {},'command_id':cid}).encode(),
        headers={'X-SV05-Token':service.token,'Content-Type':'application/json'})
    queued=json.load(opener.open(req,timeout=3));assert queued['state']=='queued',queued
    end=time.monotonic()+45
    while time.monotonic()<end:
        state=json.load(opener.open(url+'/api/status',timeout=3))['engine']
        receipt=next((r for r in state.get('receipts',[]) if r['command_id']==cid),None)
        if receipt:
            assert receipt['state']==expected,receipt
            checks.append({'action':action,'receipt':receipt['state'],'phase':state['phase'],'motion_state':state.get('motion_state')})
            return state
        time.sleep(.05)
    raise TimeoutError(action)
try:
    state=command('play');assert state['playing']
    state=command('keyboard',{'enabled':False});assert not state['keyboard_enabled']
    state=command('keyboard',{'enabled':True});assert state['keyboard_enabled']
    state=command('stop');assert state['motion_state']=='stopped' and not state['playing']
    state=command('play');assert state['playing']
    state=command('pause');assert not state['playing']
    state=command('exit');assert state['phase']=='exited'
    command('play',expected='failed')
    state=command('reinitialize');assert state['phase']=='interactive_ready' and state['motion_state']=='paused'
    state=command('play');assert state['playing']
    command('pause')
    report={'passed':True,'checks':checks,'socket_preserved':Path(owner['socket']).exists()}
    (directory/'web_lifecycle_fix.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    service.closed=True;server.shutdown();server.server_close();thread.join(timeout=3)
