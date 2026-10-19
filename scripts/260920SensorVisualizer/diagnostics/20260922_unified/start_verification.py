import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
out=root/'reports/unified_bag';out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX','AMENT_PREFIX_PATH','CMAKE_PREFIX_PATH'):env.pop(key,None)
command=['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash; exec /usr/bin/python3 -B "$@"','verify']
result=subprocess.run(command+[str(root/'tools/test_unified_bag.py')],env=env,text=True,capture_output=True,timeout=20)
(out/'unit_tests.log').write_text(result.stdout+result.stderr)
if result.returncode:raise RuntimeError(result.stderr[-3000:])
session=Path('/root/gpufree-data/semantic/output/sensor_visualizer/20260922_155355_992974_87bcf8')
if (session/'bag_unified').exists():raise RuntimeError('Inspect existing unified output before rerunning')
with (out/'historical_pack.log').open('wb') as log:
    child=subprocess.Popen(command+[str(root/'tools/pack_session_mcap.py'),str(session)],env=env,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
identity=dict(pid=child.pid,start_ticks=(Path('/proc')/str(child.pid)/'stat').read_text().split()[21],session=str(session),purpose='pack historical completed session')
(out/'historical_process.json').write_text(json.dumps(identity,indent=2))
print(json.dumps(dict(tests=result.stderr,process=identity)))
