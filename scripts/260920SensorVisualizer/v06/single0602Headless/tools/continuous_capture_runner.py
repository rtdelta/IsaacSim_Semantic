"""Sequential all-sensor regression for native-clock and completed legacy trajectories."""
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
from single0602_headless.trajectory import Trajectory

path=ROOT/'reports/continuous_capture_regression.json'
report={'state':'running','cases':[]}
native_only='--native-only' in sys.argv
if native_only and path.is_file():
    previous=json.loads(path.read_text())
    assert previous['state']=='passed',previous
    (ROOT/'reports/continuous_capture_regression_previous.json').write_bytes(path.read_bytes())
    report['cases']=[row for row in previous['cases'] if row['label']=='legacy_clock']
write_json(path,report)
try:
    gui=json.loads((ROOT/'reports/continuous_gui.json').read_text())
    process=json.loads((ROOT/'reports/continuous_gui_process.json').read_text())
    assert gui['state']=='passed' and process['state']=='exited' and process['exit_code']==0
    legacy=json.loads((ROOT/'reports/isaac_acceptance.json').read_text())
    assert legacy['state']=='passed'
    output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
    supervisor=CaptureSupervisor(ROOT,output,output/'runtime/engine.sock')
    assert not any(t['running'] or t.get('cleanup_pending') for t in supervisor.status())
    cases=[('native_clock',gui['first_trajectory'])]
    if not native_only:cases.append(('legacy_clock',legacy['trajectory']))
    for label,source in cases:
        trajectory=Trajectory.load(source)
        case={'label':label,'source':source,'time_base':trajectory.metadata['time_base'],'state':'starting'}
        report['cases'].append(case);write_json(path,report)
        info=supervisor.start({'mode':'offline','trajectory':source,'groups':3,'sample_hz':10,'ros_preview':False})
        case['task_id']=info['task_id'];write_json(path,report)
        deadline=time.monotonic()+240
        while True:
            task=next(t for t in supervisor.status() if t['task_id']==info['task_id'])
            case.update(state=task['state'],groups=task.get('groups',0),task=task)
            write_json(path,report)
            if not task['running'] and task['resource_lock_released']:break
            if time.monotonic()>deadline:raise TimeoutError('Capture exceeded test deadline; task identity retained in report')
            time.sleep(.5)
        assert task['state']=='finished' and task['exit_code']==0 and task['groups']==3,task
        assert task['record_drain_complete'] and task['process_exited'] and task['resource_lock_released']
        env=os.environ.copy()
        for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(name,None)
        command=['/bin/bash','--noprofile','--norc','-c',
            'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"',
            's0602-continuous-validation',str(ROOT/'tools/validate_capture_data.py'),task['session']]
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=120)
        (ROOT/'reports'/('continuous_mcap_'+label+'.log')).write_text(result.stdout+'\n'+result.stderr)
        lines=[line for line in result.stdout.splitlines() if line.startswith('VALIDATION_JSON=')]
        validation=json.loads(lines[-1].split('=',1)[1]) if lines else {'passed':False,'error':result.stderr[-4000:]}
        case.update(validation=validation,validation_exit_code=result.returncode)
        assert result.returncode==0 and validation['passed'],case
        case['state']='passed';write_json(path,report)
    report['state']='passed'
except Exception:
    report.update(state='failed',error=traceback.format_exc())
write_json(path,report)
print(json.dumps(report))
raise SystemExit(0 if report['state']=='passed' else 1)
