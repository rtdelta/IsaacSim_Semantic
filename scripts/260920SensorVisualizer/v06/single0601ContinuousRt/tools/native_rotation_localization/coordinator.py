"""Finite predeclared sequence, one owned Kit, batches of at most four."""
import argparse,json,os,shutil,signal,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import save,sha
REPORT=ROOT/'reports/native_rotation_localization/native007_20261015_v1'
def competitors():
 result=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit() or int(p.name)==os.getpid():continue
  try:
   c=(p/'cmdline').read_bytes()
   if b'/kit/kit' in c or str(ROOT).encode() in c and b'--worker' in c:result.append(int(p.name))
  except OSError:pass
 return result
def static_ready(condition):
 return all(any(json.loads(p.read_text()).get('static_model_qualified') is True and json.loads(p.read_text()).get('measurement_qualified') is True for p in (REPORT/condition/profile).glob('r01/*/analysis/summary.json')) for profile in ('S0','S5'))
def check_lock(path):
 lock=json.loads(path.read_text())
 for f in lock['files']:
  if sha(ROOT/f['path'])!=f['sha256']:raise RuntimeError('Frozen source differs '+f['path'])
def run_one(path):
 from run_capture import launch_spec
 spec=json.loads(path.read_text());out=ROOT/spec['output_relative'];out.mkdir(parents=True,exist_ok=False)
 save(out/'run_spec.json',spec)
 if sha(ROOT/spec['analysis_rules_path'])!=spec['analysis_rules_sha256']:raise ValueError('Frozen rule hash changed')
 os.environ['DISPLAY']=':20';os.environ['S0601_EXPERIMENT_SPEC']=str(path);os.environ.pop('S0601_FORCE_BARRIER',None)
 command,env,install=launch_spec(ROOT/'config/mixed_pair.json',ROOT/spec['entry'])
 command+=spec.get('launch_overrides',[])
 save(out/'launch.json',{'argv':command,'launch_monotonic_ns':env['S0601_LAUNCH_MONOTONIC_NS'],'entry_sha256':sha(ROOT/spec['entry']),'caches':'unchanged'})
 with (out/'launch.log').open('xb') as log:
  child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  save(out/'coordinator_status.json',{'state':'capturing','kit_pid':child.pid,'coordinator_pid':os.getpid()})
  try:code=child.wait(timeout=spec['wall_timeout_s'])
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
   raise RuntimeError('Owned Kit total watchdog')
 if code:return {'state':'FAILED_CAPTURE','exit_code':code,'path':str(out)}
 analysis_env=os.environ.copy()
 for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):analysis_env[k]='1'
 save(out/'coordinator_status.json',{'state':'analyzing'})
 with (out/'analysis.log').open('xb') as log:
  result=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_rotation_localization/analyze_independent.py'),str(out)],env=analysis_env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 if result.returncode:return {'state':'FAILED_ANALYSIS','path':str(out)}
 summary=json.loads((out/'analysis/summary.json').read_text());fingerprint=json.loads((out/'continuous/configuration_fingerprint.json').read_text())
 expected=json.loads((ROOT/'config/native_instant_baseline/effective_E.json').read_text())['observed']
 settings_expected=expected['effective'];settings_expected=json.loads(json.dumps(settings_expected))
 settings_expected['settings'].update(spec['requested_settings'])
 scene_ok=fingerprint['scene']==expected['scene']
 if spec.get('asset_id')=='official':
  scene_ok=fingerprint['scene']['walls']==expected['scene']['walls'] and any(x['path']==spec['scene_asset'] and x['sha256']==spec['asset_sha256'] for x in fingerprint['scene']['dependencies'])
 config_ok=fingerprint['effective']==settings_expected and fingerprint['environment']==expected['environment'] and scene_ok
 attrs=json.loads((out/'continuous/sensor_manifest.json').read_text())['attributes']
 override_ok=all(attrs.get(k,{}).get('value')==v for k,v in spec['sensor_overrides'].items())
 if spec['condition']=='A0':config_ok=config_ok and fingerprint['sensor_attributes_sha256']==expected['sensor_attributes_sha256']
 status={'state':'COMPLETE' if summary['measurement_qualified'] is True and summary['cleanup_ok'] is True and config_ok and override_ok else 'FAILED_QUALIFICATION',
  'path':str(out),'measurement_qualified':summary['measurement_qualified'],'effective_configuration_qualified':config_ok,'sensor_overrides_qualified':override_ok,
  'geometry_absolute_failed':summary['geometry_absolute_failed'],'distance_failed':summary['distance_failed'],'candidate_counts':summary['candidate_counts']}
 save(out/'coordinator_status.json',status);return status
def worker(path):
 manifest=json.loads(path.read_text());directory=REPORT/'sequences'/manifest['id'];state={'id':manifest['id'],'state':'running','pid':os.getpid(),'runs':[],'planned_runs':len(manifest['runs'])}
 try:
  check_lock(ROOT/'config/native_instant_baseline/main_code_lock.json')
  if manifest['requires_lock']:check_lock(ROOT/'config/native_rotation_localization/v1/main_code_lock.json')
  for index,row in enumerate(manifest['runs']):
   if index%4==0:
    batch=manifest['runs'][index:index+4];required=sum(not r['capability'].startswith('blocked') for r in batch)*2*1024**3+manifest['reserve_bytes']
    if shutil.disk_usage(ROOT).free<required:raise RuntimeError('Conservative batch disk budget unavailable; split sequence, preserve evidence')
   state['active']=row;save(directory/'status.json',state)
   if row['capability'].startswith('blocked'):result={'state':'BLOCKED_PREREQUISITE','reason':row['capability']}
   elif row['profile'] not in ('S0','S5') and not static_ready(row['condition']):result={'state':'BLOCKED_STATIC_QUALIFICATION'}
   else:
    if competitors():raise RuntimeError('Competing Kit or worker')
    if shutil.disk_usage(ROOT).free<2*1024**3+manifest['reserve_bytes']:raise RuntimeError('Per-run disk budget unavailable')
    result=run_one(ROOT/row['spec'])
   state['runs'].append(dict(row,result=result));save(directory/'status.json',state)
   if result['state'].startswith('FAILED') and not (row.get('allow_static_qualification_failure') and row['profile'] in ('S0','S5') and result['state']=='FAILED_QUALIFICATION'):
    raise RuntimeError('Inspect failure before further capture: '+result['state'])
  state['state']='TERMINAL_WITH_BLOCKED_BRANCHES' if any(r['result']['state'].startswith('BLOCKED') for r in state['runs']) else 'COMPLETE'
 except Exception as exc:state.update(state='STOPPED_FOR_INSPECTION',failure=str(exc),traceback=traceback.format_exc())
 save(directory/'status.json',state)
def start(path):
 m=json.loads(path.read_text());directory=REPORT/'sequences'/m['id']
 if competitors():raise RuntimeError('Competing Kit or worker')
 if m['max_batch_runs']>4:raise RuntimeError('Batch limit')
 directory.mkdir(parents=True,exist_ok=False);save(directory/'manifest.json',m)
 env=os.environ.copy()
 for k in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(k,None)
 with (directory/'worker.log').open('xb') as log:
  child=subprocess.Popen(['/usr/bin/python3','-B',str(Path(__file__)),'--sequence',str(path),'--worker'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 print(json.dumps({'pid':child.pid,'sequence':m['id'],'directory':str(directory)}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--sequence',required=True);p.add_argument('--worker',action='store_true');a=p.parse_args();path=Path(a.sequence).resolve()
 if ROOT not in path.parents:raise ValueError('Manifest outside project')
 worker(path) if a.worker else start(path)
