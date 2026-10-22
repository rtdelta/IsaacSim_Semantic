"""Owned bounded C/F batches, separate evidence namespace and qualification gate."""
import argparse,hashlib,json,os,shutil,signal,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');sys.path.insert(0,str(ROOT))
from tools.experiments.storage import save,digest
from tools.experiments.start_paired_remote import kits
from tools.clock_state.common import parent_for
from tools.clock_state.candidates import RULES


def run_pair(spec_path):
    from run_capture import launch_spec
    spec=json.loads(spec_path.read_text());parent=parent_for(ROOT,spec);parent.mkdir(parents=True,exist_ok=False)
    save(parent/'experiment_spec.json',spec);save(parent/'analysis_rules.json',RULES)
    status={'state':'starting','pid':os.getpid(),'spec_sha256':digest(spec_path),'planned_target_count':spec['targets']}
    for side,entry in [('continuous','tools/clock_state/run_continuous.py'),('frozen_room','tools/experiments/run_room_frozen_reference.py')]:
        if kits():raise RuntimeError('Competing Kit; refuse start')
        if side!='continuous' and json.loads((parent/'continuous_terminal.json').read_text())['status']!='EXPERIMENT_COMPLETE':raise RuntimeError('C incomplete')
        os.environ['S0601_EXPERIMENT_SPEC']=str(spec_path);os.environ['DISPLAY']=':20'
        if side=='continuous':os.environ.pop('S0601_FORCE_BARRIER',None)
        else:os.environ['S0601_FORCE_BARRIER']='1'
        command,env,install=launch_spec(ROOT/'config/mixed_pair.json',ROOT/entry)
        with (parent/(side+'_launch.log')).open('xb') as log:
            child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            status.update(state=side,kit_pid=child.pid);save(parent/'coordinator_status.json',status)
            try:code=child.wait(timeout=(spec['wall_timeout_s'] if side=='continuous' else spec['frozen_timeout_s'])+120)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                raise RuntimeError('Owned process watchdog '+side)
        if code:raise RuntimeError('Kit failed '+side+' exit='+str(code))
    status.update(state='analyzing');save(parent/'coordinator_status.json',status)
    analysis_env=os.environ.copy()
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):analysis_env[key]='1'
    with (parent/'analysis.log').open('x') as log:
        result=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/clock_state/analyze.py'),str(parent)],env=analysis_env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:raise RuntimeError('Analysis failed')
    from tools.clock_state.phase_analysis import analyze as analyze_phase
    analyze_phase(parent)
    summary=json.loads((parent/'analysis/summary.json').read_text())
    status.update(state='COMPLETE' if summary['run_qualified'] else 'FAILED_QUALIFICATION',measurement_qualified=summary['measurement_qualified'],lifecycle_qualified=summary['lifecycle_qualified'],run_qualified=summary['run_qualified']);save(parent/'coordinator_status.json',status)
    return summary


def batch(path):
    spec=json.loads(path.read_text());directory=ROOT/'reports/clock_state_consistency/batches'/spec['batch_id']
    state={'schema_version':1,'batch_id':spec['batch_id'],'state':'running','pid':os.getpid(),'runs':[],
        'planned_order':spec['planned_order'],'spec_sha256':digest(path)};save(directory/'status.json',state)
    try:
        for rel in spec['specs']:
            path_case=ROOT/rel;case=json.loads(path_case.read_text());parent=parent_for(ROOT,case)
            if shutil.disk_usage(ROOT).free<2*case['disk_bytes']+spec['free_reserve_bytes']:raise RuntimeError('Free disk reserve before next pair')
            state['active_spec']=rel;save(directory/'status.json',state)
            try:summary=run_pair(path_case)
            except Exception as exc:
                save(parent/'coordinator_status.json',{'state':'FAILED','failure':str(exc),'traceback':traceback.format_exc()});raise
            state['runs'].append({'spec':rel,'directory':str(parent),'measurement_qualified':summary['measurement_qualified'],'lifecycle_qualified':summary['lifecycle_qualified'],'run_qualified':summary['run_qualified']});save(directory/'status.json',state)
            if not summary['run_qualified']:raise RuntimeError('Measurement or lifecycle qualification failed; retain data, stop dependent cases')
        state['state']='COMPLETE'
    except Exception as exc:state.update(state='FAILED',failure=str(exc),traceback=traceback.format_exc())
    save(directory/'status.json',state)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--batch',required=True);parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    path=Path(args.batch).resolve()
    if ROOT not in path.parents:raise ValueError('Spec outside project')
    if args.worker:batch(path)
    else:
        spec=json.loads(path.read_text());directory=ROOT/'reports/clock_state_consistency/batches'/spec['batch_id']
        if kits():raise RuntimeError('Existing Kit')
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                command=(proc/'cmdline').read_bytes()
                if str(ROOT).encode() in command and b'--worker' in command:raise RuntimeError('Existing owned coordinator; it may launch another Kit')
            except (FileNotFoundError,PermissionError,ProcessLookupError):pass
        if len(spec['specs'])>6:raise RuntimeError('Batch exceeds six pairs')
        if shutil.disk_usage(ROOT).free<spec['disk_budget_bytes']+spec['free_reserve_bytes']:raise RuntimeError('Insufficient batch disk reserve')
        directory.mkdir(parents=True,exist_ok=False);save(directory/'condition_manifest.json',spec)
        env=os.environ.copy()
        for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
        with (directory/'coordinator.log').open('xb') as log:
            child=subprocess.Popen(['/usr/bin/python3','-B',str(ROOT/'tools/clock_state/coordinator.py'),'--batch',str(path),'--worker'],
                cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        print(json.dumps({'batch_pid':child.pid,'directory':str(directory),'spec_sha256':digest(path)}))
