"""Start an owned concurrent capture and measure applied controls under load."""
import json,sys,time,uuid
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05');sys.path.insert(0,str(root))
from sensor_visualizer_v05.control_ipc import request
from sensor_visualizer_v05.capture_supervisor import CaptureSupervisor
info=json.loads((root/'reports/native_owner/owner.json').read_text());socket=info['socket']
spec=root/'reports/native_owner/live_test_spec.json'
mode=json.loads(spec.read_text())['mode'] if spec.exists() else 'live_latest'
def applied(action,payload=None):
    cid=uuid.uuid4().hex;request(socket,{'action':action,'payload':payload or {},'command_id':cid});end=time.monotonic()+5
    while time.monotonic()<end:
        state=request(socket,{'action':'status'});receipt=next((r for r in state.get('receipts',[]) if r['command_id']==cid),None)
        if receipt:
            assert receipt['state']=='applied',receipt
            return state,(receipt['completed_ns']-receipt['accepted_ns'])/1e6
        time.sleep(.01)
    raise TimeoutError(action)
state=request(socket,{'action':'status'});assert state['phase']=='interactive_ready'
applied('hold');applied('keyboard',{'enabled':True});applied('play')
supervisor=CaptureSupervisor(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v05',socket)
task=supervisor.start({'mode':mode,'groups':3,'sample_hz':10,'ros_preview':True})
(root/'reports/native_owner'/(mode+'_task.json')).write_text(json.dumps(task))
samples=[]
for _ in range(80):
    state,latency=applied('keys',{'source':'web:concurrency-test','keys':['U','Q']});samples.append(latency);time.sleep(.1)
applied('keys',{'source':'web:concurrency-test','keys':[]});applied('pause')
if mode=='live_complete':state,_=applied('record_stop')
values=sorted(samples);result={'mode':mode,'task':task,'commands':len(samples),'p50_ms':values[len(values)//2],
    'p95_ms':values[int(.95*len(values))],'max_ms':max(values),'owner_slow_updates':state['statistics']['slow_updates'],
    'owner_max_ms':state['statistics']['max_owner_ms'],'test_note':'Headless controls during capture startup; separate steady capture test also required'}
(root/'reports/native_owner'/('concurrent_'+mode+'.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result))
