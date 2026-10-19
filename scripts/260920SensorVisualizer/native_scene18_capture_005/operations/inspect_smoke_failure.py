import json,re
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005')
info=json.loads((root/'reports/latest.json').read_text());out=Path(info['directory'])/'smoke/capture'
lines=(out/'engine.log').read_text(errors='replace').splitlines();warn={}
for line in lines:
 if '[Warning]' not in line and '[Error]' not in line:continue
 msg=re.sub(r'^.*?\[(Warning|Error)\]','',line)
 if len(warn)<35 or msg in warn:warn[msg]=warn.get(msg,0)+1
files=[]
for p in Path('/root/isaacsim/exts/isaacsim.core.experimental.prims').rglob('*.py'):
 s=p.read_text(errors='replace')
 if 'def set_world_poses' in s and 'def set_dof_positions' in s:
  chunks=[]
  for name in ('set_world_poses','set_dof_positions','set_velocities','set_root_velocities','get_velocities'):
   match=re.search(r'^    def '+name+r'\(',s,re.M)
   if match:
    start=match.start();end=s.find('\n    def ',start+1);chunks.append(s[start:end if end>0 else start+6000][:9500])
  files.append({'path':str(p),'methods':chunks})
print(json.dumps({'warnings':warn,'sdk':files}))
