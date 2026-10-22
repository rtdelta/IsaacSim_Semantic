import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
result=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/start_native_probe_remote.py'),'--scene','room','--profile','rotation','--sync','default'],cwd=root,capture_output=True,text=True,timeout=10)
if result.returncode:raise RuntimeError(result.stderr[-1800:])
print(result.stdout)
