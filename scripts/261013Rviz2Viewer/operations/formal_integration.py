import subprocess,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text());capture=Path(latest['directory'])/'capture';result=json.loads((capture/'result.json').read_text())
args=['/usr/bin/python3',str(root/'tests/ros_integration.py'),result['capture']['session'],str(capture/'viewer_assets'),str(root/'reports/formal_integration.json')]
p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','test',*args],cwd=root,capture_output=True,text=True,timeout=30)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}));assert p.returncode==0
