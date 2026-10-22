"""Real camera/LiDAR acceptance using disposable USD wrappers and task-owned copies."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.contracts import DEFAULT,write_json
from single0602_headless.offline_job import snapshot_trajectory

report={'state':'running','cases':[]}
report_path=ROOT/'reports/scene_replay_matrix.json'
if report_path.is_file():
    previous=json.loads(report_path.read_text())
    write_json(ROOT/'reports/test_attempts'/('scene_replay_matrix_'+str(time.time_ns())+'.json'),previous)
    report['cases']=[case for case in previous.get('cases',[]) if case.get('passed')]
def save():write_json(report_path,report)

def main():
    native=json.loads((ROOT/'reports/scene_replay_native.json').read_text())
    assert native['state']=='passed'
    output=Path('/root/gpufree-data/semantic/output/s0602_scene_replay')
    output.mkdir(parents=True,exist_ok=True)
    destination=output/'trajectories'/('source_'+str(time.time_ns()))
    snapshot_trajectory(native['trajectory'],destination)
    source=Path(native['editable_scene']);assert source.is_relative_to(Path(native['output']))
    base_path=Path(DEFAULT['scene'])
    initial=re.sub(r'@([^@]+)@',lambda m:'@'+str((base_path.parent/m.group(1)).resolve())+'@'
                   if not m.group(1).startswith('/') else m.group(0),base_path.read_text()).encode('utf-8')
    source.write_bytes(initial)
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file()}
    supervisor=CaptureSupervisor(ROOT,output,output/'runtime/unused.sock')
    base=DEFAULT['scene'];dome=DEFAULT['render']['background_dome']
    prefix=initial.decode('utf-8')
    def robot_override(text,content):
        pattern=r'(    over "Excavator" \([\s\S]*?    \)\n    \{\n)'
        changed,count=re.subn(pattern,lambda m:m.group(1)+content+'\n',text,count=1)
        assert count==1
        return changed

    def capture(name,options,success=True,expected_error=None):
        if any(case['name']==name and case.get('passed') for case in report['cases']):return
        payload={'trajectory':str(destination),'capture_scope':'full_trajectory','sample_hz':10,**options}
        task=supervisor.start(payload);row={'name':name,'task_id':task['task_id'],'expected_success':success}
        report['cases'].append(row);save()
        deadline=time.monotonic()+240
        while True:
            state=next(x for x in supervisor.status() if x['task_id']==task['task_id'])
            row['task']=state;save()
            if not state['running'] and state['resource_lock_released']:break
            if time.monotonic()>deadline:raise TimeoutError('Owned capture still running: '+task['task_id'])
            time.sleep(1)
        if success:
            assert state['state']=='finished' and state['exit_code']==0 and state['capture_complete'] and state['record_drain_complete'],state
            env=os.environ.copy()
            for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
            args=['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','scene-replay-readback',str(ROOT/'tools/validate_capture_data.py'),state['session']]
            check=subprocess.run(args,env=env,capture_output=True,text=True,timeout=90)
            lines=[line for line in check.stdout.splitlines() if line.startswith('VALIDATION_JSON=')]
            row['validation']=json.loads(lines[-1].split('=',1)[1]) if lines else {'error':check.stdout[-1200:]+check.stderr[-1800:]}
            assert check.returncode==0 and row['validation']['passed'],row['validation']
            assert row['validation']['source_root_max_error_m']<=1e-5
            assert row['validation']['source_joint_max_error_rad']<=1e-4
            assert row['validation']['source_quaternion_max_error']<=5e-6
            identity=json.loads((Path(state['session'])/'replay_identity.json').read_text())
            assert identity['source_trajectory_file_hashes'] and identity['target_scene']==task['scene_selection']['target_scene']
        else:
            assert state['state']=='failed' and expected_error in state.get('error',''),state
            assert not (Path(state['session'])/'bag_unified').exists(),'Invalid interface created a formal bag'
        row['passed']=True;save()

    capture('original_reproduction',{})
    # The user-reported edit is applied only to a disposable wrapper, never source assets.
    cube='    over "Cube"\n    {\n        double3 xformOp:scale = (3.1, 1, 1)\n        double3 xformOp:translate = (6.4938325266, -1.6563331261, 1.0621100652)\n    }\n'
    edited=prefix.replace('    over "Excavator" (',cube+'    over "Excavator" (',1)
    assert edited!=prefix
    source.write_text(edited,encoding='utf-8')
    capture('original_rejects_saved_edit',{},False,'Scene changed since trajectory')
    env={'scene_policy':'environment','target_scene':str(source),'background_dome':dome}
    capture('same_path_edited_environment',env)
    target=output/'target_environment.usda';target.write_text(edited,encoding='utf-8')
    preserved=source.with_suffix('.preserved.usda');source.replace(preserved)
    capture('new_environment_source_missing_with_placement',{'scene_policy':'environment','target_scene':str(target),
             'background_dome':dome,'placement':{'translation_m':[.4,.1,.05],'yaw_deg':15}})
    bad=output/'bad_axis.usda'
    bad.write_text(robot_override(prefix,'        over "Joints"\n        {\n            over "boom"\n            {\n                uniform token physics:axis = "X"\n            }\n        }'),encoding='utf-8')
    capture('reject_changed_joint_axis',{'scene_policy':'environment','target_scene':str(bad),'background_dome':dome},False,'excavator.joints.boom.axis')
    bad_camera=output/'bad_camera.usda'
    bad_camera.write_text(robot_override(prefix,'        over "swing_link"\n        {\n            over "FisheyeFront"\n            {\n                float omni:lensdistortion:opencvFisheye:fx = 999\n            }\n        }'),encoding='utf-8')
    capture('reject_changed_camera_calibration',{'scene_policy':'environment','target_scene':str(bad_camera),'background_dome':dome},False,'interface.sensors.camera_front.configuration')
    old=ROOT/'reports/capture_migration_interactive.json'
    if old.is_file():
        legacy=json.loads(old.read_text())['first_trajectory']
        legacy_copy=output/'trajectories'/('legacy_'+str(time.time_ns()))
        snapshot_trajectory(legacy,legacy_copy)
        capture('legacy_trajectory_environment',{'trajectory':str(legacy_copy),'scene_policy':'environment','target_scene':str(target),
                'background_dome':dome,'capture_scope':'group_limit','groups':2})
    assert all(hashlib.sha256((destination/name).read_bytes()).hexdigest()==digest for name,digest in source_hashes.items())
    assert hashlib.sha256(Path(base).read_bytes()).hexdigest()=='e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79'
    report.update(state='passed',source_trajectory_unchanged=True,source_asset_unchanged=True)

save()
try:main()
except Exception:report.update(state='failed',error=traceback.format_exc())
save();print(json.dumps(report));raise SystemExit(0 if report['state']=='passed' else 1)
