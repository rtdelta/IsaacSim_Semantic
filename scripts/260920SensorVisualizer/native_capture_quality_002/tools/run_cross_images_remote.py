import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
# Executed after deployment, using only already installed ROS/NumPy/Pillow.
code=subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','nc002',str(root/'tools/compare_images_remote.py')],timeout=120).returncode
raise SystemExit(code)
