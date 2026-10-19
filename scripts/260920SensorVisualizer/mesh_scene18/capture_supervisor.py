"""Use the preserved v06 capture implementation; own only this test's processes."""
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
BASE=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
WORK=BASE/'mesh_scene18';FROZEN=BASE/'single06_lab/frozen_runtime'
case=Path(sys.argv[1]).resolve()
assert case.is_relative_to(Path('/root/gpufree-data/semantic/output/mesh_scene18').resolve())
sys.path.insert(0,str(FROZEN))
from run_capture import launch_spec
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Kit process; no process stopped')
    except OSError:pass
scene=Path(json.loads((case/'job.json').read_text())['scene']);before=hashlib.sha256(scene.read_bytes()).hexdigest()
args,env,cwd=launch_spec(case/'job.json',entry=FROZEN/'kit_replay_entry.py')
env['ROS_DOMAIN_ID']='193';env['ROS_LOCALHOST_ONLY']='1'
started=time.monotonic();result={'state':'running','case':str(case)}
(case/'result.json').write_text(json.dumps(result))
with (case/'engine.log').open('xb') as log:
    child=subprocess.Popen(args,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    result['kit_pid']=child.pid;(case/'result.json').write_text(json.dumps(result))
    try:child.wait(timeout=480)
    except subprocess.TimeoutExpired:
        (case/'control.json').write_text('{"action":"stop"}')
        try:child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=20)
    result.update(exit_code=child.returncode,process_wall_s=time.monotonic()-started)
status=case/'capture_status.json'
if status.exists():result['capture']=json.loads(status.read_text())
def ros(argv):return subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','scene18-validation',*map(str,argv)],capture_output=True,text=True,timeout=180)
if result['exit_code']==0 and result.get('capture',{}).get('state')=='finished':
    session=Path(result['capture']['session'])
    p=ros([BASE/'single06_lab/tools/validate_capture_data.py',session]);(case/'validation.log').write_text(p.stdout+p.stderr)
    result['validation_exit_code']=p.returncode
    for line in p.stdout.splitlines():
        if line.startswith('VALIDATION_JSON='):result['validation']=json.loads(line.split('=',1)[1])
    (case/'capture').mkdir(exist_ok=True);(case/'capture/result.json').write_text(json.dumps(result))
    p=ros([BASE/'capture_comparison_004/tools/decode_case.py',case]);(case/'decode.log').write_text(p.stdout+p.stderr);result['decode_exit_code']=p.returncode
result['scene_unchanged']=hashlib.sha256(scene.read_bytes()).hexdigest()==before
result['state']='completed' if result.get('validation',{}).get('passed') and result.get('decode_exit_code')==0 and result['scene_unchanged'] else 'failed'
(case/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
