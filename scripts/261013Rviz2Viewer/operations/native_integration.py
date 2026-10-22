import subprocess,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
output=Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer')
args=['/usr/bin/python3',str(root/'tests/ros_integration.py'),'/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300',str(output/'20261013_142507_300/capture/viewer_assets'),str(root/'reports/native_integration.json'),'--cache',str(output/'native_reference_cache/index.sqlite'),'--logs',str(output/'native_reference_cache/logs')]
p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','test',*args],cwd=root,capture_output=True,text=True,timeout=30)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout[-6000:],'stderr':p.stderr[-4000:]}))
assert p.returncode==0
