"""Read installed APIs without importing Kit or starting processes."""
import json
from pathlib import Path
import re
import subprocess

root = Path('/root/isaacsim')
patterns = {
    'simulation_manager': ('exts/isaacsim.core.simulation_manager/**/*.py',
        ['def get_simulation_time', 'def get_num_physics_steps', 'def register_callback',
         'def setup_simulation', 'def _on_physics_step', 'class IsaacEvents']),
    'replicator': ('extscache/omni.replicator.core-*/omni/replicator/core/**/*.py',
        ['def attach(', 'trigger=', 'ReferenceTime', 'def set_capture_on_play']),
    'source_time': ('exts/isaacsim.core.nodes/**/*.py', ['IsaacReadSimulationTime', 'ReferenceTime']),
}
out = {}
for label, (pattern, needles) in patterns.items():
    matches = []
    for path in sorted(root.glob(pattern)):
        lines = path.read_text(errors='replace').splitlines()
        found = [i for i, line in enumerate(lines) if any(n in line for n in needles)]
        if found:
            selected = sorted(set(j for i in found[:12] for j in range(max(0, i-2), min(len(lines), i+24))))
            matches.append({'path': str(path), 'lines': [{'line': j+1, 'text': lines[j]} for j in selected]})
        if len(matches) >= 8:
            break
    out[label] = matches
out['ros'] = subprocess.run(['/bin/bash', '-c', "source /opt/ros/jazzy/setup.bash && /usr/bin/python3 -B -c 'import rosbag2_py,rclpy; print(rosbag2_py.get_registered_writers())'"], capture_output=True, text=True, timeout=20).stdout
print(json.dumps(out))
