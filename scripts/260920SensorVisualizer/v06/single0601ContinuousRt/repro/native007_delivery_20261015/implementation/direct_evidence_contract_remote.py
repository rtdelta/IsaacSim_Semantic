"""Bounded static inventory of public sensor/history diagnostic declarations."""
import hashlib,json,re
from pathlib import Path
sdk=Path('/root/isaacsim');project=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
roots=[sdk/'exts/isaacsim.sensors.experimental.rtx',sdk/'exts/isaacsim.core.simulation_manager',sdk/'exts/isaacsim.core.rendering_manager']
roots += [p for p in (sdk/'extscache').iterdir() if p.name.startswith(('omni.sensors.nv.common-','omni.sensors.nv.lidar-'))]
files=[];matches=[]
pattern=re.compile(r'history|interpol|query.?time|ray.?origin|ray.?direction|frameStart|frameEnd|debug|trace|dump',re.I)
for base in roots:
 for p in base.rglob('*'):
  if not p.is_file() or p.suffix not in ('.h','.hpp','.pyi','.toml','.rst','.md') or p.stat().st_size>300000:continue
  digest=hashlib.sha256(p.read_bytes()).hexdigest();files.append({'path':str(p),'sha256':digest})
  lines=p.read_text(errors='replace').splitlines();hits=[]
  for i,line in enumerate(lines):
   if pattern.search(line):hits.append({'line':i+1,'lines':lines[max(0,i-2):i+3]})
  if hits:matches.append({'path':str(p),'sha256':digest,'hits':hits})
out={'scope':'installed public .h/.hpp/.pyi/config/docs only; no binary disassembly or runtime probe','files':files,'matches':matches,
 'requested_evidence':['actual history samples consumed','actual query time','actual interpolation endpoints and weight','per-ray consumed origin direction time','output-reference transform actually consumed'],
 'interpretation':'Declarations require manual semantic review; GMO frame endpoints and current Fabric matrix alone do not prove internal consumption.'}
p=project/'reports/native007_direct_evidence_contracts.json';p.write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'report':str(p.relative_to(project)),'files_examined':len(files),'files_with_matches':len(matches),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
