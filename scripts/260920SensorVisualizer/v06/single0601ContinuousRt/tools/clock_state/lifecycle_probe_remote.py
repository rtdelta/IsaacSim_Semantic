"""One bounded owned Kit; execute only after registered capture batches exit."""
import json,os,signal,subprocess,sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');sys.path.insert(0,str(root))
from run_capture import launch_spec
from tools.experiments.start_paired_remote import kits
spec={'name':'legacy_120_commit_probe','hz':120,'sensor_products':True,'commit_recheck':True}
if kits():raise RuntimeError('Existing Kit; defer lifecycle probe')
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        cmd=(p/'cmdline').read_bytes()
        if str(root).encode() in cmd and b'--worker' in cmd:raise RuntimeError('Owned batch may start another Kit')
    except (FileNotFoundError,PermissionError,ProcessLookupError):pass
parent=root/'reports/clock_state_consistency/lifecycle_probes';parent.mkdir(parents=True,exist_ok=True)
os.environ['S0601_LIFECYCLE_PROBE']=json.dumps(spec);os.environ['DISPLAY']=':20';os.environ.pop('S0601_FORCE_BARRIER',None)
command,env,install=launch_spec(root/'config/mixed_pair.json',root/'tools/clock_state/run_lifecycle_probe.py')
with (parent/(spec['name']+'_launch.log')).open('xb') as log:
    child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:code=child.wait(timeout=180)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=15)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        raise RuntimeError('Owned lifecycle probe watchdog')
if code:raise RuntimeError('Lifecycle probe failed '+str(code))
print((parent/spec['name']/'result.json').read_text())
