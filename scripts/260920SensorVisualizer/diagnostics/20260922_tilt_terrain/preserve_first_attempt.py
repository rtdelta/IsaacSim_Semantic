import hashlib
import json
from pathlib import Path
import shutil
r=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/tilt_terrain')
folder=r/'before_metadata_fix';folder.mkdir(exist_ok=True)
for name in ['validation.json','recording_check.json','kit.log','log_summary.json','assembly.json']:
    p=r/name
    if p.exists() and not (folder/name).exists():shutil.copy2(p,folder/name)
assembly=json.loads((r/'assembly.json').read_text())
scene=Path(assembly['scene'])
assembly['scene_sha256']=hashlib.sha256(scene.read_bytes()).hexdigest()
assembly['root_metadata_preserved_from_scene15']=True
(r/'assembly.json').write_text(json.dumps(assembly,indent=2)+'\n')
print(json.dumps({'preserved':str(folder),'scene_sha256':assembly['scene_sha256']}))
