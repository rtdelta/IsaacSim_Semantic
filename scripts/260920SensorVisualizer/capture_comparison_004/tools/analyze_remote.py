"""Post-processing only. Requires all scheduled independent engine tests to end."""
import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004')
info=json.loads((root/'reports/latest_suite.json').read_text());out=Path(info['directory']);progress=json.loads((out/'progress.json').read_text())
if progress['state'] not in ('completed','failed','stopped') or progress.get('current'):raise RuntimeError('Capture still active; post-analysis deferred')
codes=[]
for script in ('verify_common_inputs.py','compare_lidar_ranges.py','analyze_suite.py'):
 p=subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc004',str(root/'tools'/script),str(out)],capture_output=True,text=True,timeout=900)
 (out/(script+'.log')).write_text(p.stdout+p.stderr);print(p.stdout);print(p.stderr);codes.append(p.returncode)
raise SystemExit(max(codes))
