"""Read only the deployment identity, owned processes and project baseline."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
assert root.resolve() == root and root.is_dir()
files = {p.relative_to(root/'v06').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (root/'v06').rglob('*') if p.is_file() and
         not set(p.relative_to(root/'v06').parts) & {'reports', '__pycache__'} and p.suffix not in ('.pyc', '.pyo')}
processes = []
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        raw = p.read_bytes().decode('utf-8', 'replace').split('\0')
        if any(str(root/'v06') in arg or str(root/'v07') in arg for arg in raw):
            processes.append({'pid': int(p.parent.name), 'entry': [arg for arg in raw if str(root) in arg]})
    except OSError:
        pass
gpu = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,pci.bus_id,name,memory.used,utilization.gpu',
                      '--format=csv,noheader'], capture_output=True, text=True, timeout=10)
print(json.dumps({'root': str(root), 'v07_exists': (root/'v07').exists(), 'v06_sha256': files,
                  'processes': processes, 'gpu': gpu.stdout, 'gpu_exit': gpu.returncode,
                  'scene_exists': Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda').is_file()}))
