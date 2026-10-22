"""Capture and independently read back native scene-binding fixtures."""
import hashlib
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


def main():
    native=json.loads((ROOT/'reports/scene_binding_native.json').read_text())
    out=Path(native['output']);report_path=ROOT/'reports/scene_binding_matrix.json'
    report={'state':'running','cases':[]}
    if report_path.exists():
        previous=json.loads(report_path.read_text())
        write_json(ROOT/'reports/attempts'/('matrix_'+str(time.time_ns())+'.json'),previous)
        report['cases']=[r for r in previous.get('cases',[]) if r.get('passed')]
    def save():write_json(report_path,report)
    save()
    supervisor=CaptureSupervisor(ROOT,out,out/'runtime/unneeded.sock')
    trajectories={r['name']:r['trajectory'] for r in native['cases']}
    def capture(name,source,options=None,error=None):
        if any(r['name']==name and r.get('passed') for r in report['cases']):return
        payload={'trajectory':source,'capture_scope':'full_trajectory','sample_hz':10,**(options or {})}
        identity={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(source).iterdir() if p.is_file()}
        result=supervisor.start(payload)
        row={'name':name,'task':result,'expected_error':error};report['cases'].append(row);save()
        deadline=time.monotonic()+300
        while True:
            state=next(t for t in supervisor.status() if t['task_id']==result['task_id'])
            row['status']=state;save()
            if not state['running'] and state['resource_lock_released']:break
            if time.monotonic()>deadline:raise TimeoutError('Owned capture timed out: '+result['task_id'])
            time.sleep(1)
        if error:
            assert state['state']=='failed' and error in state.get('error',''),state
            assert not (Path(state['session'])/'bag_unified').exists()
        else:
            assert state['state']=='finished' and state['exit_code']==0 and state['capture_complete'] and state['record_drain_complete'],state
            env=os.environ.copy()
            for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
            check=subprocess.run(['/bin/bash','--noprofile','--norc','-c',
                'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"',
                'scene-binding-readback',str(ROOT/'tools/validate_capture_data.py'),state['session']],
                env=env,capture_output=True,text=True,timeout=90)
            lines=[line for line in check.stdout.splitlines() if line.startswith('VALIDATION_JSON=')]
            row['validation']=json.loads(lines[-1].split('=',1)[1]) if lines else {'error':check.stdout[-1500:]+check.stderr[-2500:]}
            assert check.returncode==0 and row['validation']['passed'],row['validation']
        assert identity=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(source).iterdir() if p.is_file()}
        row['source_trajectory_unchanged']=True;row['passed']=True;save()
    try:
        for name in ('baseline','camera_only','lidar_only','mixed','renamed'):
            if name in trajectories:capture(name,trajectories[name])
        if 'zero' in trajectories:
            capture('zero_sensors_rejected_before_writer',trajectories['zero'],error='No selected capture-ready sensors')
            capture('new_target_sensors_from_motion_only_trajectory',trajectories['zero'],
                {'scene_policy':'environment','target_scene':native['fixtures']['camera_only'],'sensor_policy':'target_scene',
                 'sensors':{'camera_resolution':[320,240]},'placement':{'translation_m':[.4,.1,.05],'yaw_deg':15}})
        if 'mixed' in trajectories:
            capture('recorded_sensors_with_placement',trajectories['mixed'],
                {'scene_policy':'environment','target_scene':native['fixtures']['mixed'],
                 'placement':{'translation_m':[.4,.1,.05],'yaw_deg':15}})
        report['state']='passed'
    except Exception:report.update(state='failed',error=traceback.format_exc())
    save();print(json.dumps({'state':report['state'],'cases':[(r['name'],r.get('passed',False)) for r in report['cases']],
                            'error':report.get('error')}),flush=True)
    return 0 if report['state']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
