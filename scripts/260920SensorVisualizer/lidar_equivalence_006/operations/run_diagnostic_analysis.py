import json,subprocess
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
assert json.loads((out/'causal_retry_progress.json').read_text()).get('finished')
with (out/'diagnostic_analysis.log').open('xb') as log:
 p=subprocess.Popen(['bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc006',str(R/'analyze_diagnostics.py'),str(out)],stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({'pid':p.pid}))
