"""Owned GUI soak plus a full-quality 100-group offline replay; no external downloads."""
import json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
from sensor_visualizer_v06.capture_supervisor import CaptureSupervisor
from sensor_visualizer_v06.trajectory import Trajectory
from sensor_visualizer_v06.contracts import write_json
directory=root/'reports/native_owner';owner=json.loads((directory/'owner.json').read_text());socket=owner['socket']
status_path=directory/'soak_status.json';started=time.monotonic();samples=[];capture=None;recorded=None
supervisor=CaptureSupervisor(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v06',socket)
def apply(action,payload=None):
    cid=uuid.uuid4().hex;request(socket,{'action':action,'payload':payload or {},'command_id':cid});end=time.monotonic()+5
    while time.monotonic()<end:
        state=request(socket,{'action':'status'});r=next((r for r in state.get('receipts',[]) if r['command_id']==cid),None)
        if r:
            assert r['state']=='applied',r;samples.append((r['completed_ns']-r['accepted_ns'])/1e6)
            if action=='record_start':state['trajectory_path']=r['path']
            return state
        time.sleep(.01)
    raise TimeoutError(action)
def publish(phase,state=None,**values):
    write_json(status_path,{'state':phase,'elapsed_wall_s':time.monotonic()-started,'commands':len(samples),
        'owner':owner['pid'],'capture':capture,'trajectory':recorded,**values})
try:
    assert owner.get('gui'),'This test requires the real GUI owner'
    assert shutil.disk_usage('/root/gpufree-data/semantic/output').free>6*1024**3,'Insufficient test output space'
    state=request(socket,{'action':'status'});assert state['phase']=='interactive_ready'
    apply('hold');names=list(state['joint_controls'])
    apply('motion',{'joints':{n:{'mode':'periodic','lower':-10,'upper':10,'speed':5} for n in names},
        'tilt':{n:{'mode':'periodic','lower':-2,'upper':2,'speed':1} for n in ('pitch','roll')}})
    state=apply('record_start');recorded=state['trajectory_path'];control_origin=state['state']['t_sim_s']
    apply('keyboard',{'enabled':True});apply('play');publish('recording_source')
    while True:
        state=apply('keys',{'source':'web:soak','keys':[]})
        if state['state']['t_sim_s']-control_origin>=9.91:break
        if time.monotonic()-started>240:raise TimeoutError('Source trajectory too slow')
        publish('recording_source',source_time_s=state['state']['t_sim_s']-control_origin);time.sleep(.5)
    apply('record_stop');trajectory=Trajectory.load(recorded);assert trajectory.duration>=9.9
    capture=supervisor.start({'mode':'offline','trajectory':recorded,'groups':100,'sample_hz':10,'ros_preview':True})
    write_json(directory/'soak_task.json',capture);publish('soak_and_capture',source_rows=len(trajectory.states))
    with (directory/'soak_resources.jsonl').open('x',encoding='utf-8') as resources:
        while time.monotonic()-started<1800:
            state=apply('keys',{'source':'web:soak','keys':['Q']});time.sleep(.1)
            state=apply('keys',{'source':'web:soak','keys':[]})
            tasks=supervisor.status();task=next(x for x in tasks if x['task_id']==capture['task_id'])
            if task.get('state')=='failed':raise RuntimeError(task.get('error','Capture failed'))
            stats=state['statistics'];values=sorted(samples)
            proc=Path('/proc')/str(owner['pid'])
            resource={'monotonic_ns':time.monotonic_ns(),'owner_stat':(proc/'stat').read_text(),
                'owner_rss_kib':int(next(l.split()[1] for l in (proc/'status').read_text().splitlines() if l.startswith('VmRSS:'))),
                'gpu':subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5).stdout.strip(),
                'capture_state':task['state'],'groups':task.get('groups',0)}
            resources.write(json.dumps(resource)+'\n');resources.flush()
            publish('soak_and_capture',capture_status=task,applied_p95_ms=values[int(.95*len(values))],
                applied_max_ms=max(values),owner_statistics={k:v for k,v in stats.items() if not k.endswith('samples')})
            time.sleep(4.5)
    apply('pause');task=next(x for x in supervisor.status() if x['task_id']==capture['task_id'])
    assert task['state']=='finished' and task['groups']==100 and not task['running'],task
    values=sorted(samples);publish('passed',passed=True,capture_status=task,applied_p50_ms=values[len(values)//2],
        applied_p95_ms=values[int(.95*len(values))],applied_max_ms=max(values),owner_statistics=state['statistics'])
except Exception as exc:
    publish('failed',error=str(exc))
    try:
        apply('pause')
        if request(socket,{'action':'status'}).get('recording'):apply('record_stop')
        if capture:supervisor.control(capture['task_id'],'stop')
    except Exception:pass
    raise
