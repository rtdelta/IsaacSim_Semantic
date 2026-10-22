import json
from pathlib import Path
root=Path('/root/isaacsim');out=[]
patterns=[('exts/isaacsim.ros2.core','*camera_info*.py'),('exts/isaacsim.ros2.nodes','*extension*.py'),
 ('exts/isaacsim.core.nodes','*TransformTree*.ogn'),('exts/isaacsim.core.nodes','*ReadSimulationTime*.ogn'),
 ('exts/isaacsim.ros2.nodes','*PublishRawTransformTree*.ogn')]
for base,pattern in patterns:
 for p in (root/base).rglob(pattern):
  if p.is_file():out.append({'path':str(p),'text':p.read_text(errors='replace')[:20000]})
print(json.dumps(out,ensure_ascii=False))
