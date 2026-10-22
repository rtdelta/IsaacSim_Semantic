"""Probe installed runtime without starting Kit or downloading dependencies."""
import json, os, subprocess
from pathlib import Path

work = Path('/root/gpufree-data/.migration_sensor_20261010_dual')
assert json.loads((work / 'owner.json').read_text())['task'] == 'sensor-visualizer-dual-migration-20261010'
env = os.environ.copy()
for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):
    env.pop(name, None)
code = '''import importlib,json
mods={}
for name in ('numpy','PIL','rosbag2_py','rclpy','sensor_msgs.msg','tf2_msgs.msg','rosgraph_msgs.msg'):
    try:
        m=importlib.import_module(name)
        mods[name]={'ok':True,'file':getattr(m,'__file__',None),'version':getattr(m,'__version__',None)}
    except Exception as exc:mods[name]={'ok':False,'error':type(exc).__name__+': '+str(exc)}
try:
    import rosbag2_py
    writers=list(rosbag2_py.get_registered_writers())
except Exception as exc: writers={'error':str(exc)}
print(json.dumps({'imports':mods,'bag_storage_plugins':writers}))
'''
p = subprocess.run(['/bin/bash','--noprofile','--norc','-c',
                    'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B -c "$1"',
                    'runtime-check',code], env=env,capture_output=True,text=True,timeout=40)
result = {'exit_code':p.returncode, 'stderr':p.stderr[-2000:],
          'probe':json.loads(p.stdout) if p.returncode == 0 else p.stdout[-2000:],
          'isaac_version':Path('/root/isaacsim/VERSION').read_text().strip(),
          'kit_exists':Path('/root/isaacsim/kit/kit').is_file(),
          'ros_setup_exists':Path('/opt/ros/jazzy/setup.bash').is_file()}
(work/'runtime_validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
