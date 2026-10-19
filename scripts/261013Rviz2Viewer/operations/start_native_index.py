import subprocess, json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
args=['/usr/bin/python3',str(root/'run_viewer.py'),'--capture','/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300','--cache','/root/gpufree-data/semantic/output/261013Rviz2Viewer/native_reference_cache/index.sqlite','--index-only']
log=(root/'reports/native_index.log').open('wb')
child=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','index',*args],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'pid':child.pid,'log':str(root/'reports/native_index.log')}))
