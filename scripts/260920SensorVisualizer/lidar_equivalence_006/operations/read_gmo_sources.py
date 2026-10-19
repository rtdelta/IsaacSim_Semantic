import json
from pathlib import Path
base=Path('/root/isaacsim/exts');rows=[]
for folder in ('isaacsim.sensors.experimental.rtx','isaacsim.sensors.rtx.nodes'):
 for p in (base/folder).rglob('*.py'):
  if p.name in ('generic_model_output.py','test_point_cloud_annotator.py','utils.py'):
   rows.append({'path':str(p),'text':p.read_text(errors='replace')})
print(json.dumps(rows))
