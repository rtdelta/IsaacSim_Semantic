"""Read only: locate the existing scene and native runtime before deployment."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

scene = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
info = {'scene': str(scene), 'scene_exists': scene.is_file(),
        'kit_exists': Path('/root/isaacsim/kit/kit').is_file(),
        'destination_exists': Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless').exists()}
if scene.is_file():
    info['scene_sha256'] = hashlib.sha256(scene.read_bytes()).hexdigest()
    text = scene.read_text()
    refs = re.findall(r'@([^@]+)@', text)
    info['scene_references'] = refs
    info['robot_lines'] = [line.strip() for line in text.splitlines()
                           if any(k in line.lower() for k in ('excavator', 'origin03', 'swing', 'reference'))][:35]
info['gpu'] = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.used,utilization.gpu', '--format=csv,noheader'],
                             capture_output=True, text=True, timeout=15).stdout.strip()
print(json.dumps(info, ensure_ascii=False))
