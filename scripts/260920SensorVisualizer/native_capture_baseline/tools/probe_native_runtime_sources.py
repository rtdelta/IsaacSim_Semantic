import json
from pathlib import Path
base=Path('/root/isaacsim')
files=[]
for folder,pattern in [('exts/isaacsim.core.nodes','*writer*node*.py'),('exts/isaacsim.core.nodes','*WriterNode*.py'),('exts/isaacsim.ros2.nodes','ros2_common.py'),('standalone_examples/api/isaacsim.ros2.bridge','camera*.py')]:
 for p in (base/folder).rglob(pattern):
  files.append({'path':str(p),'text':p.read_text()[:29000]})
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
x=json.loads((root/'reports/latest_execution.json').read_text());out=Path(x['directory'])
lines=(out/'engine.log').read_text(errors='replace').splitlines()
warnings=[line for line in lines if '[Warning]' in line and 'PoseTree' not in line]
print(json.dumps({'files':files,'warnings':warnings[-50:]}))
