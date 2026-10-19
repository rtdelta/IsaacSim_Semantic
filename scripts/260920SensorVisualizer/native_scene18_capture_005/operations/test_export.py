import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005')
base=Path(json.loads((root/'reports/latest.json').read_text())['directory'])
source=base/'smoke/capture';dest=base/'smoke/delivery_test'
def run(args):
 r=subprocess.run(['bash','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','native-export',*args],text=True,capture_output=True,timeout=90)
 print(r.stdout);print(r.stderr)
 if r.returncode:raise SystemExit(r.returncode)
run(['/usr/bin/python3',str(root/'tools/export_groups.py'),str(source),str(dest)])
for tool in ('validate_bag.py','validate_groups.py'):run(['/usr/bin/python3',str(root/'tools'/tool),str(dest)])
print(json.dumps({'export_test':str(dest),'ok':True}))
