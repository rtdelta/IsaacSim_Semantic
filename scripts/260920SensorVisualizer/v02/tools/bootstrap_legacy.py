"""Create a self-contained, provenance-tracked copy; never change v01."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[1]
old = root.parent
names = ['articulation_motion', 'base_control', 'joint_control', 'motion_profile',
         'reference_frames', 'robot_discovery', 'discovery', 'render_lease',
         'performance', 'sensor_pose', 'joint_panel', 'base_panel', 'tilt_panel']
target = root/'sv02_legacy'
target.mkdir(exist_ok=True)
(target/'__init__.py').write_text('"""Frozen project-local v01 components; see provenance.json."""\n', encoding='utf-8')
manifest = {}
for name in names:
    source = old/'sensor_visualizer'/f'{name}.py'
    dest = target/source.name
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copyfile(source, dest)
    manifest[str(source.relative_to(old)).replace('\\', '/')] = hashlib.sha256(source.read_bytes()).hexdigest()
(root/'provenance.json').write_text(json.dumps({'source_project': old.name, 'source_files': manifest}, indent=2)+'\n', encoding='utf-8')
(root/'config').mkdir(exist_ok=True)
shutil.copyfile(old/'config/sensors.json', root/'config/legacy_sensors.json')
(root/'docs').mkdir(exist_ok=True)
shutil.copyfile(old/'docs/capture_v2_implementation_plan.md', root/'docs/implementation_plan.md')
print(json.dumps({'copied': len(manifest), 'v02': str(root)}))
