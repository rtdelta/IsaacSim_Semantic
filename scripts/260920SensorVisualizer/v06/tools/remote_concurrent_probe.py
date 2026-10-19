import json,sys,time,uuid
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
owner=json.loads((root/'reports/native_owner/owner.json').read_text());socket=owner['socket']
request(socket,{'action':'play'})
samples=[];phases=set();end=time.monotonic()+30
while time.monotonic()<end:
    cid=uuid.uuid4().hex;request(socket,{'action':'keys','payload':{'source':'web:steady-test','keys':['U','Q']},'command_id':cid})
    receipt=None;deadline=time.monotonic()+4
    while not receipt and time.monotonic()<deadline:
        state=request(socket,{'action':'status'});receipt=next((r for r in state.get('receipts',[]) if r['command_id']==cid),None)
        if not receipt:time.sleep(.01)
    assert receipt and receipt['state']=='applied',receipt
    samples.append((receipt['completed_ns']-receipt['accepted_ns'])/1e6)
    for track in (root/'reports/native_owner').glob('*_task.json'):
        info=json.loads(track.read_text());p=Path(info['directory'])/'status.json'
        if p.exists():phases.add(json.loads(p.read_text()).get('state'))
    time.sleep(.1)
request(socket,{'action':'keys','payload':{'source':'web:steady-test','keys':[]}})
values=sorted(samples);result={'commands':len(values),'p50_ms':values[len(values)//2],'p95_ms':values[int(.95*len(values))],
    'max_ms':max(values),'phases':sorted(phases),'owner_max_ms':state['statistics']['max_owner_ms'],
    'slow_updates':state['statistics']['slow_updates']}
(root/'reports/native_owner/steady_concurrency.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
