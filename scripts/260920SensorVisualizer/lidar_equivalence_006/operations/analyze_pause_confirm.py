import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
d=json.loads((out/'native_pause_no_probe/capture/result.json').read_text());assert d.get('engine_exit')==0,d.get('state')
with (out/'pause_confirmation.log').open('xb') as log:
 p=subprocess.Popen(['bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc006',str(R/'analyze_pause_confirm.py'),str(out)],stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({'pid':p.pid}))
