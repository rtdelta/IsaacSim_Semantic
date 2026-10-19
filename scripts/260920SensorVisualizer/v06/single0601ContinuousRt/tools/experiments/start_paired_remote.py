"""Start one bounded owned C -> F -> read-only comparison coordinator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
sys.path.insert(0,str(ROOT))
from tools.experiments.storage import save


def kits():
    result=[]
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit():
            try:
                if b'/kit/kit' in (proc/'cmdline').read_bytes():result.append(int(proc.name))
            except FileNotFoundError:pass
    return result


def coordinate(spec_path):
    from run_capture import launch_spec
    spec=json.loads(Path(spec_path).read_text())
    parent=ROOT/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat'];parent.mkdir(parents=True,exist_ok=True)
    save(parent/'experiment_spec.json',spec)
    status={'spec':spec,'state':'starting','pid':os.getpid()};save(parent/'coordinator_status.json',status)
    for side,entry in [('continuous','run_continuous_experiment.py'),('frozen_v06' if spec['scene']=='scene18' else 'frozen_room',
                         'run_v06_frozen_reference.py' if spec['scene']=='scene18' else 'run_room_frozen_reference.py')]:
        if kits():raise RuntimeError('Kit still running; refuse second instance')
        if side!='continuous' and not (parent/'continuous_terminal.json').exists():raise RuntimeError('C not drained')
        if side!='continuous':
            c=json.loads((parent/'continuous_terminal.json').read_text())
            if c['status']!='EXPERIMENT_COMPLETE':raise RuntimeError('C incomplete; retain prefix before F')
        os.environ['S0601_EXPERIMENT_SPEC']=str(Path(spec_path).resolve());os.environ['DISPLAY']=':20'
        if side=='continuous':os.environ.pop('S0601_FORCE_BARRIER',None)
        else:os.environ['S0601_FORCE_BARRIER']='1'
        command,env,install=launch_spec(ROOT/'config/mixed_pair.json',ROOT/'tools/experiments'/entry)
        with (parent/(side+'_launch.log')).open('xb') as log:
            child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            status.update(state=side,kit_pid=child.pid,kit_entry=entry);save(parent/'coordinator_status.json',status)
            try:code=child.wait(timeout=(spec['wall_timeout_s'] if side=='continuous' else spec['frozen_timeout_s'])+120)
            except subprocess.TimeoutExpired:
                # Only this exact Popen process/session; never stop another Kit.
                import signal
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                status.update(state='FAILED',failure='owned process wall watchdog',side=side);save(parent/'coordinator_status.json',status);return
        if code:
            status.update(state='FAILED',failure='Kit exit '+str(code),side=side);save(parent/'coordinator_status.json',status);return
    status.update(state='analyzing');save(parent/'coordinator_status.json',status)
    result=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/experiments/compare_paired_outputs.py'),str(parent)],capture_output=True,text=True)
    (parent/'analysis_stdout.log').write_text(result.stdout+'\n'+result.stderr)
    if result.returncode==0:
        mechanism=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/experiments/analyze_mechanism_relations.py'),str(parent)],capture_output=True,text=True)
        (parent/'mechanism_stdout.log').write_text(mechanism.stdout+'\n'+mechanism.stderr)
        status['mechanism_returncode']=mechanism.returncode
    status.update(state='COMPLETE' if result.returncode==0 else 'FAILED',analysis_returncode=result.returncode)
    save(parent/'coordinator_status.json',status)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--spec',required=True);parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    if args.worker:
        try:coordinate(args.spec)
        except Exception as exc:
            import traceback
            spec=json.loads(Path(args.spec).read_text());parent=ROOT/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat']
            save(parent/'coordinator_status.json',{'state':'FAILED','failure':str(exc),'traceback':traceback.format_exc()});raise
    else:
        if kits():raise RuntimeError('Another Kit is running')
        spec_path=Path(args.spec).resolve()
        if ROOT not in spec_path.parents:raise ValueError('Spec outside own project')
        spec=json.loads(spec_path.read_text());parent=ROOT/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat']
        if parent.exists():raise RuntimeError('Refuse experiment evidence overwrite')
        parent.mkdir(parents=True)
        env=os.environ.copy()
        for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
        with (parent/'coordinator.log').open('xb') as log:
            child=subprocess.Popen(['/usr/bin/python3','-B',str(Path(__file__).resolve()),'--worker','--spec',str(spec_path)],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        print(json.dumps({'coordinator_pid':child.pid,'directory':str(parent),'spec_sha256':hashlib.sha256(spec_path.read_bytes()).hexdigest()}))
