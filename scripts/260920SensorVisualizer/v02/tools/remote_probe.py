"""Read only: targeted prerequisites for the v02 project."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
result = {'project': str(root), 'v02_exists': (root/'v02').exists(), 'files': {}, 'kit_processes': []}
for relative in ('config/sensors.json', 'sensor_visualizer/articulation_motion.py', 'sensor_visualizer/robot_discovery.py', 'launch_isaac.py'):
    path = root/relative
    result['files'][relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        if (proc/'comm').read_text().strip() == 'kit':
            args = (proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
            result['kit_processes'].append({'pid': int(proc.name), 'args': [a for a in args if 'isaacsim.exp.' in a or a.startswith('--/') or a == '--no-window']})
    except OSError:
        pass
for program, args in [('gpu', ['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader']),
                      ('disk', ['df', '-h', str(root)])]:
    run = subprocess.run(args, capture_output=True, text=True, timeout=10)
    result[program] = {'returncode': run.returncode, 'output': run.stdout[:2000], 'error': run.stderr[:500]}
result['scene_exists'] = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda').is_file()
result['isaac'] = {p: Path(p).exists() for p in ('/root/isaacsim/python.sh', '/root/isaacsim/kit/python/bin/python3', '/root/isaacsim/kit/kit', '/opt/ros/jazzy/setup.bash')}
result['installed_source_paths'] = [str(p) for p in Path('/root/isaacsim/exts').glob('isaacsim.sensors.rtx*')]
print(json.dumps(result))
