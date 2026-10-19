import json
from pathlib import Path
p=Path('/root/isaacsim/exts/isaacsim.sensors.experimental.rtx/isaacsim/sensors/experimental/rtx/generic_model_output/_rtx_sensors_gmo.pyi')
lines=p.read_text().splitlines();out=[]
for i,l in enumerate(lines):
 if l.startswith('class FrameAtTime') or l.startswith('class Pose') or l.startswith('class Quaternion'):
  end=next((j for j in range(i+1,len(lines)) if lines[j].startswith('class ')),min(i+180,len(lines)));out.extend(lines[i:end])
out.extend(l for l in lines if any(x in l for x in ('timeOffset','elementsCoordsType','motionCompensation','outputMotion','tickStates','scanComplete')))
print(json.dumps({'path':str(p),'lines':out}))
