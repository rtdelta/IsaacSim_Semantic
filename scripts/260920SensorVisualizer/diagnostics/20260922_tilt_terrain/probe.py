import hashlib
import json
import os
from pathlib import Path
import shutil

project = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
out = {'blender': [], 'processes': [], 'files': {}, 'displays': [], 'scenes': []}
candidates = [shutil.which('blender'), '/root/blender/blender', '/opt/blender/blender']
for folder in [Path('/root'), Path('/opt'), Path('/root/gpufree-data'), Path('/root/gpufree-data/tools')]:
    if folder.is_dir():
        candidates += [str(p) for p in folder.glob('*blender*/blender')]
        candidates += [str(p) for p in folder.glob('*/blender*/blender')]
out['blender'] = sorted({str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()})
out['displays'] = [p.name for p in Path('/tmp/.X11-unix').glob('X*')]
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        name = (p/'comm').read_text().strip()
        if name.lower() in ['kit','isaac-sim','isaacsim','blender','xorg','xvfb','xvnc','xtigervnc']:
            out['processes'].append({'pid':int(p.name),'name':name})
    except OSError: pass
assets = Path('/root/gpufree-data/IsaacSim_Asset')
out['scenes'] = [p.name for p in sorted((assets/'combine_stage').glob('*.usd*'))]
for p in [project/'sensor_visualizer/base_control.py',project/'sensor_visualizer/base_panel.py',
          project/'sensor_visualizer/articulation_motion.py',project/'sensor_visualizer/camera_capture.py',
          project/'config/sensors.json',assets/'combine_stage/combine_scene_15_surround_fisheye.usda']:
    out['files'][str(p)] = hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
out['disk_free_bytes'] = shutil.disk_usage('/root/gpufree-data').free
out['usd_native'] = [str(p) for p in Path('/root/isaacsim/extscache').glob('omni.usd.libs-*')]
print(json.dumps(out))
