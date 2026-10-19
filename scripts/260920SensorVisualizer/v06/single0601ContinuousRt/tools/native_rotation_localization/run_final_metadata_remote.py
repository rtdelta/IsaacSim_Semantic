import json,os,signal,subprocess,sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');sys.path.insert(0,str(root))
from run_capture import launch_spec
from tools.native_rotation_localization.coordinator import competitors,check_lock
suite=root/'reports/native_rotation_localization/native007_20261015_v1'
if competitors():raise RuntimeError('Capture still active')
for p in (suite/'sequences').glob('*/status.json'):
 if json.loads(p.read_text())['state']=='running':raise RuntimeError('Sequence active')
check_lock(root/'config/native_rotation_localization/v1/main_code_lock.json');os.environ['DISPLAY']=':20';os.environ.pop('S0601_EXPERIMENT_SPEC',None)
command,env,install=launch_spec(root/'config/mixed_pair.json',root/'tools/native_rotation_localization/final_metadata_crosscheck.py')
with (suite/'final_metadata_crosscheck.log').open('xb') as log:
 child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:code=child.wait(timeout=600)
 except subprocess.TimeoutExpired:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
  raise RuntimeError('Owned offline parser process exceeded bound')
result=json.loads((suite/'final_metadata_crosscheck.json').read_text());print(json.dumps({k:v for k,v in result.items() if k!='files'}));sys.exit(code)
