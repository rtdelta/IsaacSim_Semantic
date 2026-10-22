"""Real owned Kit acceptance. Never terminate another project's processes."""
import json,runpy,sys,time,traceback
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
from sensor_visualizer_v06.capture_supervisor import CaptureSupervisor
directory=root/'reports/native_owner';directory.mkdir(parents=True,exist_ok=True)
results={};active=None;owner_started=False

def save():
    (directory/'acceptance_status.json').write_text(json.dumps(results,indent=2))

def tool(name):
    runpy.run_path(str(root/'tools'/name),run_name='__main__')

def wait_task(supervisor,task,timeout=360):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        row=next(x for x in supervisor.status() if x['task_id']==task['task_id'])
        results['active_task']=row;save()
        if not row['running'] and not row.get('cleanup_pending'):
            assert row['state']=='finished',row
            return row
        time.sleep(.5)
    raise TimeoutError('Owned capture did not finish')

try:
    results['phase']='owner_start';save()
    (directory/'owner_test_options.json').write_text(json.dumps({'gui':True,'native_event_test':True}))
    tool('remote_start_owner_test.py');owner_started=True
    owner=json.loads((directory/'owner.json').read_text());sock=owner['socket']
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        p=directory/'native_keyboard_fix.json'
        if p.exists():
            native=json.loads(p.read_text());assert native['passed'];results['native_keyboard']=native;break
        time.sleep(.5)
    else:raise TimeoutError('Native key test incomplete; inspect owned Kit log and window focus')
    results['phase']='lifecycle';save();tool('remote_lifecycle_fix_test.py')
    results['lifecycle']=json.loads((directory/'lifecycle_fix.json').read_text())
    results['phase']='motion_mount_trajectory';save();tool('remote_owner_interaction_test.py')
    results['interaction']=json.loads((directory/'interaction.json').read_text())
    tool('remote_motion_modes_test.py');results['motion_modes']=json.loads((directory/'motion_modes.json').read_text())
    results['phase']='http';save();tool('remote_web_runtime_test.py')
    results['http']=json.loads((directory/'http_runtime.json').read_text())
    s=CaptureSupervisor(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v06',sock)
    trajectory=results['interaction']['trajectory']
    try:s.start({'mode':'offline','trajectory':trajectory,'groups':3,'gpu':'GPU-unavailable-test-device'})
    except ValueError:results['invalid_gpu_rejected']=True
    else:raise AssertionError('Unavailable GPU launched a child')
    results['phase']='offline_recovery_pause';save()
    active=s.start({'mode':'offline','trajectory':trajectory,'groups':3,'sample_hz':10,'ros_preview':False,'gpu':0})
    (directory/'offline_task.json').write_text(json.dumps(active))
    recovered=CaptureSupervisor(root,s.output,sock)
    try:recovered.start({'mode':'offline','trajectory':trajectory,'groups':3})
    except ValueError:pass
    else:raise AssertionError('Recovered active child allowed duplicate capture')
    recovered.control(active['task_id'],'pause');deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        row=next(x for x in recovered.status() if x['task_id']==active['task_id'])
        if row.get('state')=='paused':break
        assert row['running'],row;time.sleep(.5)
    else:raise TimeoutError('Pause boundary did not acknowledge')
    count=row['groups'];time.sleep(.5)
    assert next(x for x in recovered.status() if x['task_id']==active['task_id'])['groups']==count
    recovered.control(active['task_id'],'run')
    results['offline']=wait_task(s,active);active=None
    assert results['offline']['groups']==3,results['offline']
    results['recovery']={'passed':True,'duplicate_blocked':True,'paused_group':count,'resume_finished':True}
    for mode,entry in (('live_latest','remote_live_capture_test.py'),('live_complete','remote_start_complete_test.py')):
        results['phase']=mode;save()
        (directory/'live_test_spec.json').write_text(json.dumps({'mode':mode}))
        tool(entry);active=json.loads((directory/(mode+'_task.json')).read_text())
        s=CaptureSupervisor(root,s.output,sock);results[mode]=wait_task(s,active);active=None
        assert results[mode]['groups']==3,results[mode]
        if mode=='live_latest':request(sock,{'action':'pause'})
    results['phase']='stop_boundary';save()
    active=s.start({'mode':'offline','trajectory':trajectory,'groups':8,'sample_hz':10,'ros_preview':False})
    (directory/'stop_task.json').write_text(json.dumps(active))
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        row=next(x for x in s.status() if x['task_id']==active['task_id'])
        if row.get('groups',0)>=1:break
        assert row['running'],row;time.sleep(.5)
    else:raise TimeoutError('Stop test produced no group')
    s.control(active['task_id'],'stop');stopped=wait_task(s,active)
    assert stopped['stopped'] and 1<=stopped['groups']<8,stopped
    results['stop_boundary']=stopped;active=None
    results['phase']='finished';results['passed']=True;save()
except Exception:
    results.update(phase='failed',passed=False,error=traceback.format_exc());save();raise
finally:
    if active:
        try:
            s.control(active['task_id'],'stop');wait_task(s,active,90)
        except Exception:results['cleanup_capture_error']=traceback.format_exc();save()
    if owner_started:
        try:tool('remote_stop_owner_test.py');results['owner_cleanup']=True;save()
        except Exception:results['cleanup_owner_error']=traceback.format_exc();save()
