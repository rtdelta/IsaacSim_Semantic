from pathlib import Path
import json
p=Path('/root/isaacsim/exts/isaacsim.sensors.experimental.rtx/isaacsim/sensors/experimental/rtx/generic_model_output/_rtx_sensors_gmo.pyi')
s=p.read_text();a=s.index('class GenericModelOutput(');b=s.index('\nclass ',a+10);print(json.dumps({'text':s[a:b]}))
