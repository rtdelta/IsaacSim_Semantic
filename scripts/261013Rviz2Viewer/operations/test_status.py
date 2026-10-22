import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
result={}
for name in ('ros_integration.json','ros_integration.log'):
    p=root/'reports'/name
    if p.exists():result[name]=json.loads(p.read_text()) if name.endswith('.json') else p.read_text()[-4500:]
print(json.dumps(result))
