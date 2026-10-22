"""Owned single-GPU batches; capture and offline interpretation are separate."""
import argparse,json,os,shutil,signal,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_instant_baseline.io import save,sha

def processes():
    out=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            c=(p/'cmdline').read_bytes()
            if b'/kit/kit' in c or (str(ROOT).encode() in c and b'--worker' in c):out.append(int(p.name))
        except OSError:pass
    return out

def static_gates(experiment):
    root=ROOT/'reports/native_instant_baseline'/experiment;out={}
    for g in ('M_E','P_E','M_D'):
        selected={}
        for profile in ('S0','S5'):
            candidates=[]
            for p in (root/g/profile).glob('r01/q*/analysis/summary.json'):
                s=json.loads(p.read_text())
                if s.get('capture_complete') and s.get('measurement_qualified') and s.get('cleanup_ok') and s.get('static_model_qualified'):candidates.append(p)
            if candidates:selected[profile]={'path':str(sorted(candidates)[-1]),'sha256':sha(sorted(candidates)[-1])}
        out[g]={'static_model_qualified':len(selected)==2,'evidence':selected}
    save(root/'qualification_status.json',out)

def run_one(path,state,batchdir):
    from run_capture import launch_spec
    spec=json.loads(path.read_text());out=ROOT/spec['output_relative'];out.mkdir(parents=True,exist_ok=False)
    config_path=ROOT/'config/native_instant_baseline'/('effective_D.json' if spec['group']=='M_D' else 'effective_E.json')
    if sha(config_path)!=spec['configuration_sha256']:raise RuntimeError('Configuration changed after preregistration')
    save(out/'run_spec.json',spec);rules=ROOT/spec.get('analysis_rules_path','config/native_instant_baseline/analysis_rules_v1.json')
    if sha(rules)!=spec['analysis_rules_sha256']:raise RuntimeError('Rules changed after preregistration')
    save(out/'analysis_rules.json',json.loads(rules.read_text()))
    os.environ['DISPLAY']=':20';os.environ['S0601_EXPERIMENT_SPEC']=str(path);os.environ.pop('S0601_FORCE_BARRIER',None)
    command,env,install=launch_spec(ROOT/'config/mixed_pair.json',ROOT/spec['entry'])
    if spec.get('launch_overrides'):command+=spec['launch_overrides']
    status={'state':'starting','spec_sha256':sha(path),'coordinator_pid':os.getpid(),'started_monotonic_s':time.monotonic()}
    save(out/'launch.json',{'argv':command,'launch_monotonic_ns':env['S0601_LAUNCH_MONOTONIC_NS'],'entry_sha256':sha(ROOT/spec['entry']),'display':':20','caches':'existing, not cleared'})
    with (out/'launch.log').open('xb') as log:
        child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        status.update(state='capturing',kit_pid=child.pid);save(out/'coordinator_status.json',status)
        try:code=child.wait(timeout=spec['wall_timeout_s'])
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            status.update(state='FAILED',failure='600 s owned-process watchdog');save(out/'coordinator_status.json',status);raise RuntimeError(status['failure'])
    if code:
        status.update(state='FAILED',failure='capture exit '+str(code));save(out/'coordinator_status.json',status);raise RuntimeError(status['failure'])
    status['state']='analyzing';save(out/'coordinator_status.json',status)
    analysis_env=os.environ.copy()
    for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):analysis_env[k]='1'
    with (out/'analysis.log').open('xb') as log:
        result=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_instant_baseline/analyze_independent.py'),str(out)],env=analysis_env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:
        status.update(state='FAILED',failure='offline analysis failed');save(out/'coordinator_status.json',status);raise RuntimeError(status['failure'])
    summary=json.loads((out/'analysis/summary.json').read_text())
    actual=json.loads((out/'continuous/configuration_fingerprint.json').read_text());expected=json.loads(config_path.read_text())['observed']
    effective_ok=all(actual[k]==expected[k] for k in ('sensor_attributes_sha256','environment','effective','scene'))
    effective_ok=effective_ok and {k:v for k,v in actual['topology'].items() if k!='initialization'}=={k:v for k,v in expected['topology'].items() if k!='initialization'}
    qualified=summary['measurement_qualified'] is True and summary['cleanup_ok'] is True and effective_ok
    status.update(state='COMPLETE' if qualified else 'FAILED_QUALIFICATION',effective_configuration_qualified=effective_ok,measurement_qualified=summary['measurement_qualified'],cleanup_ok=summary['cleanup_ok'],
      diagnostic_pass=summary['diagnostic_pass'],geometry_absolute_failed=summary['geometry_absolute_failed'],geometry_increment_failed=summary['geometry_increment_failed'])
    save(out/'coordinator_status.json',status);static_gates(spec['experiment_id'])
    state['runs'].append({'spec':str(path.relative_to(ROOT)),'path':str(out),'status':status});save(batchdir/'status.json',state)
    if not qualified:raise RuntimeError('Measurement, configuration or cleanup qualification failed; geometry failure alone does not stop')

def work(batchpath):
    b=json.loads(batchpath.read_text());bd=ROOT/'reports/native_instant_baseline/batches'/b['batch_id'];state={'batch_id':b['batch_id'],'pid':os.getpid(),'state':'running','planned':len(b['specs']),'runs':[]}
    try:
        for path in b['specs']:
            if processes():raise RuntimeError('Competing Kit or coordinator')
            if shutil.disk_usage(ROOT).free<2*1024**3+b['free_reserve_bytes']:raise RuntimeError('Per-run hard budget plus reserve unavailable')
            state['active_spec']=path;save(bd/'status.json',state);run_one(ROOT/path,state,bd)
        state['state']='COMPLETE'
    except Exception as exc:state.update(state='FAILED',failure=str(exc),traceback=traceback.format_exc())
    save(bd/'status.json',state)

def start(path):
    b=json.loads(path.read_text());bd=ROOT/'reports/native_instant_baseline/batches'/b['batch_id']
    if processes():raise RuntimeError('Competing Kit/coordinator')
    if not 1<=len(b['specs'])<=4:raise RuntimeError('Batch bound')
    if b.get('previous_batch'):
        previous=json.loads((bd.parent/b['previous_batch']/'status.json').read_text())
        if previous['state']!='COMPLETE':raise RuntimeError('Prior batch not complete')
    if b['phase'] in ('main','D_qualification','D_main'):
        lock=json.loads((ROOT/'config/native_instant_baseline/main_code_lock.json').read_text())
        for f in lock['files']:
            if sha(ROOT/f['path'])!=f['sha256']:raise RuntimeError('Main-round code lock differs: '+f['path'])
        gate=json.loads((ROOT/'reports/native_instant_baseline'/b['experiment_id']/'qualification_comparison.json').read_text())
        if gate['all_measurement_and_pair_qualified'] is not True:raise RuntimeError('Six short qualifications/pair equivalence incomplete')
        if b['phase']=='D_main':
            gate=json.loads((ROOT/'reports/native_instant_baseline'/b['experiment_id']/'D_qualification_comparison.json').read_text())
            if gate['all_measurement_and_pair_qualified'] is not True:raise RuntimeError('D short qualification/configuration equivalence incomplete')
    # Initially conservative: per-run hard cap; observed compression only refines later batch estimates.
    needed=len(b['specs'])*2*1024**3+b['free_reserve_bytes']
    if shutil.disk_usage(ROOT).free<needed:raise RuntimeError('Batch storage budget; split batch without removing conditions')
    bd.mkdir(parents=True,exist_ok=False);save(bd/'batch_manifest.json',b)
    env=os.environ.copy()
    for k in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(k,None)
    with (bd/'coordinator.log').open('xb') as log:
        p=subprocess.Popen(['/usr/bin/python3','-B',str(Path(__file__)),'--batch',str(path),'--worker'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({'pid':p.pid,'batch':b['batch_id'],'directory':str(bd)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--worker',action='store_true');a=p.parse_args();path=Path(a.batch).resolve()
    if ROOT not in path.parents:raise ValueError('batch outside project')
    work(path) if a.worker else start(path)
