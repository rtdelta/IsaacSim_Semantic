import json
from pathlib import Path
r=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/tilt_terrain')
a=Path('/root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_20260922')
print(json.dumps({'files':[p.name for p in a.glob('*')],
    'logs':{p.name:p.read_text()[-7000:] for p in r.glob('*build.log')}}))
