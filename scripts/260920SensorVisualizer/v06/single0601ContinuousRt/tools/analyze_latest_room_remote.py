import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
latest=json.loads((root/'reports/latest_native_probe.json').read_text())
directory=Path(latest['directory'])
result=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/analyze_room_geometry.py'),str(directory),'--report',str(directory/'room_geometry_analysis.json')],cwd=root,capture_output=True,text=True,timeout=25)
if result.returncode:raise RuntimeError(result.stderr[-1800:])
print(result.stdout)
