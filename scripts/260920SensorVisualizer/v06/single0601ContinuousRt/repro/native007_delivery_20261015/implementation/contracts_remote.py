import hashlib,json
from pathlib import Path
sdk=Path('/root/isaacsim');ext=sdk/'exts/isaacsim.sensors.experimental.rtx'
selected=['impl/lidar.py','impl/lidar_sensor.py','impl/_sensor_base.py','impl/utils.py','impl/rtx_lidar_configs.py','tests/test_lidar_sensor.py']
files=[ext/'isaacsim/sensors/experimental/rtx'/s for s in selected]
files += list((sdk/'extscache').glob('omni.sensors.nv.common-*/bin/gmo_lib/include/GenericModelOutput.h'))
files += list((sdk/'extscache').glob('omni.sensors.nv.common-*/data/lidar/Example_Rotary.json'))
hits=[]
for base in (sdk/'exts',sdk/'extscache'):
 for p in base.rglob('*'):
  if not p.is_file() or p.stat().st_size>400000 or p.suffix not in ('.py','.h','.md','.rst','.usda'):continue
  if not any(s in str(p).lower() for s in ('sensor','lidar','rtx','rendering_manager')):continue
  t=p.read_text(errors='replace')
  if any(s in t for s in ('Example_Rotary.usd','SPHERICAL','parse_generic_model_output_data','get_transform_history','interpolationWeight','queryTimestamp')):
   rows=[{'line':i+1,'text':'\n'.join(t.splitlines()[max(0,i-2):i+4])} for i,l in enumerate(t.splitlines()) if any(k in l for k in ('Example_Rotary.usd','SPHERICAL','parse_generic_model_output_data','get_transform_history','interpolationWeight','queryTimestamp'))]
   hits.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'hits':rows[:30]})
print(json.dumps({'files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'text':p.read_text()} for p in files],'search_hits':hits}))
