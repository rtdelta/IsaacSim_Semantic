import hashlib,json,shutil,subprocess
from pathlib import Path
root=Path('/root/isaacsim');keys=('maxHistoryTransformCount','perSensorTickTlas','raytracingMotion','outputBufferOnGPU')
matches=[];headers=[]
for parent in (root/'apps',root/'exts',root/'extscache'):
 for p in parent.rglob('*'):
  if not p.is_file():continue
  if p.name in ('GenericModelOutput.h','GMOAuxiliaryData.h'):
   headers.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  if p.suffix not in ('.toml','.kit') or p.stat().st_size>2*1024**2:continue
  lines=p.read_text(errors='replace').splitlines()
  for i,line in enumerate(lines):
   if any(k in line for k in keys):matches.append({'path':str(p),'line':i+1,'text':'\n'.join(lines[max(0,i-2):i+3])})
print(json.dumps({'headers':headers,'setting_declarations':matches[:100],'matches':len(matches)}))
