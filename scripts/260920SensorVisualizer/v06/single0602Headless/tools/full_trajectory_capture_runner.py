"""Short all-sensor integration evidence for automatic plans and partial stopping."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.contracts import write_json
from single0602_headless.trajectory import Trajectory,TrajectoryRecorder

output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
report_path=ROOT/'reports/full_trajectory_capture.json'
report={'state':'running','cases':[]}
write_json(report_path,report)
try:
    source=output/'trajectories/20261016_101220_123831_07271d'
    original=Trajectory.load(source)
    supervisor=CaptureSupervisor(ROOT,output,output/'runtime/engine.sock')
    assert not any(t['running'] or t.get('cleanup_pending') for t in supervisor.status())
    report['original_preview']=supervisor.preview({'trajectory':str(source),'capture_scope':'full_trajectory','sample_hz':10})
    assert report['original_preview']['capture_plan']['planned_groups']==266
    testroot=output/'test_trajectories'/time.strftime('%Y%m%d_%H%M%S')
    for label,duration,scope,limit in [('full_grid',.2,'full_trajectory',None),('full_tail',.25,'full_trajectory',None),('group_limit',.25,'group_limit',2),('pause_stop',2.,'full_trajectory',None)]:
        directory=testroot/label
        meta=deepcopy(original.metadata);meta.update(derived_test_source=str(source),derived_test_duration_s=duration)
        recorder=TrajectoryRecorder(directory,meta)
        recorder.append(original.sample(0));recorder.append(original.sample(duration));recorder.close()
        payload={'mode':'offline','trajectory':str(directory),'capture_scope':scope,'sample_hz':10}
        if limit is not None:payload['groups']=limit
        case={'label':label,'source':str(directory),'state':'starting'};report['cases'].append(case)
        info=supervisor.start(payload);case.update(task_id=info['task_id'],capture_plan=info['capture_plan'])
        write_json(report_path,report);deadline=time.monotonic()+300;pause_sent=False;resumed=False;stop_sent=False;pause_at=None
        while True:
            task=next(t for t in supervisor.status() if t['task_id']==info['task_id'])
            case.update(state=task['state'],groups=task.get('groups',0),task=task)
            if label=='pause_stop' and task['running']:
                if not pause_sent and task.get('groups',0)>=1:
                    supervisor.control(info['task_id'],'pause');pause_sent=True
                if task['state']=='paused' and pause_at is None:pause_at=time.monotonic();case['pause_groups']=task['groups']
                if pause_at is not None and not resumed and time.monotonic()-pause_at>=.7:
                    assert task['groups']==case['pause_groups'];supervisor.control(info['task_id'],'run');resumed=True;case['pause_stable']=True
                if resumed and not stop_sent and task.get('groups',0)>case['pause_groups']:
                    supervisor.control(info['task_id'],'stop');stop_sent=True
            write_json(report_path,report)
            if not task['running'] and task['resource_lock_released']:break
            if time.monotonic()>deadline:
                supervisor.control(info['task_id'],'stop')
                raise TimeoutError('Capture deadline; Stop + Drain requested, task identity saved')
            time.sleep(.15)
        assert task['state']=='finished' and task['exit_code']==0,task
        assert task['record_drain_complete'] and task['process_exited'] and task['resource_lock_released'],task
        if label=='pause_stop':
            assert resumed and stop_sent and case['pause_stable'] and not task['capture_complete'] and task['completion_reason']=='stopped_by_user',task
        else:
            assert task['groups']==info['capture_plan']['planned_groups'] and task['capture_complete'] and task['completion_reason']=='completed_plan',task
        env=os.environ.copy()
        for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(name,None)
        result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',
            'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"',
            's0602-full-validation',str(ROOT/'tools/validate_capture_data.py'),task['session']],env=env,capture_output=True,text=True,timeout=120)
        (ROOT/'reports'/('full_trajectory_'+label+'.log')).write_text(result.stdout+'\n'+result.stderr)
        lines=[s for s in result.stdout.splitlines() if s.startswith('VALIDATION_JSON=')]
        validation=json.loads(lines[-1].split('=',1)[1]) if lines else {'passed':False}
        case.update(validation=validation,validation_exit_code=result.returncode)
        assert result.returncode==0 and validation['passed'],case
        case['state']='passed';write_json(report_path,report)
    report['state']='passed'
except Exception:
    report.update(state='failed',error=traceback.format_exc())
write_json(report_path,report)
print(json.dumps({'state':report['state'],'cases':[{'label':c['label'],'state':c['state'],'task_id':c.get('task_id')} for c in report['cases']]}))
raise SystemExit(0 if report['state']=='passed' else 1)
