from pathlib import Path
here=Path(__file__).resolve().parent
code=(here/'inspect_mcap.py').read_text(encoding='utf-8')
wrapper='''import os,subprocess
env=dict(os.environ)
for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX','AMENT_PREFIX_PATH','CMAKE_PREFIX_PATH'):env.pop(key,None)
env['PYTHONDONTWRITEBYTECODE']='1'
r=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash; exec /usr/bin/python3 -B -'],
 input=__INSPECTION_SOURCE__,env=env,text=True,capture_output=True,timeout=50)
print(r.stdout)
if r.returncode:print(r.stderr[-4000:])
raise SystemExit(r.returncode)
'''.replace('__INSPECTION_SOURCE__',repr(code))
(here/'run_bag_probe.py').write_text(wrapper,encoding='utf-8')
