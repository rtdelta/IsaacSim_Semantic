import hashlib
import json
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
report=root/'reports/tilt_terrain'
asset=Path('/root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_20260922')
partial=asset/'terrain.incomplete-export.blend'
if partial.exists():
    dest=report/'before_metadata_fix/terrain.incomplete-export.blend'
    if not dest.exists():partial.rename(dest)
checks={}
for name in ['validation_process.json','cloud_diagnostic_process.json']:
    identity=json.loads((report/name).read_text())
    p=Path('/proc')/str(identity['pid'])
    checks[name]={'pid':identity['pid'],'running':p.exists() and (p/'stat').read_text().split()[21]==identity['start_ticks']}
out={'processes':checks,'files':{},'terrain_files':{p.name:p.stat().st_size for p in asset.iterdir() if p.is_file()}}
for name in ['base_control.py','base_panel.py','tilt_panel.py','articulation_motion.py','camera_capture.py','runtime.py']:
    p=root/'sensor_visualizer'/name
    out['files']['sensor_visualizer/'+name]=hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
for name in ['validation.json','recording_check.json','assembly.json']:
    out[name]=json.loads((report/name).read_text())
print(json.dumps(out))
