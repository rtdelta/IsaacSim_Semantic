import base64,subprocess,json
from pathlib import Path
script=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline/tools/check_recorded_joints.py')
r=subprocess.run(['bash','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','native-ros','/usr/bin/python3',str(script)],capture_output=True,text=True,timeout=60)
print(json.dumps({'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}));raise SystemExit(r.returncode)
