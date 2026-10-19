import json, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
smoke=Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142231_003/capture')
session=json.loads((smoke/'result.json').read_text())['capture']['session']
latest=json.loads((root/'reports/latest_capture.json').read_text())
assets=Path(latest['directory'])/'capture/viewer_assets'
log=root/'reports/ros_integration.log'
with log.open('wb') as stream:
    child=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','test','/usr/bin/python3',str(root/'tests/ros_integration.py'),session,str(assets),str(root/'reports/ros_integration.json')],cwd=root,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True)
print(json.dumps({'pid':child.pid,'log':str(log)}))
