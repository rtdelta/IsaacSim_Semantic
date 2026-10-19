import json
from pathlib import Path
base=next(Path('/root/isaacsim/extscache').glob('omni.sensors.nv.lidar-*'))
p=base/'omni/sensors/nv/lidar/_lidar.pyi';lines=p.read_text().splitlines()
print(json.dumps({'api_path':str(base/'config/python_api.md'),'api_lines':(base/'config/python_api.md').read_text().splitlines(),
 'frame_binding_path':str(p),'frame_binding_lines':lines[1000:1135]}))
