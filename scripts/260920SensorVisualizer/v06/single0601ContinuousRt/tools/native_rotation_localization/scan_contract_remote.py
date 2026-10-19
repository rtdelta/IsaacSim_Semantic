import json
from pathlib import Path
base=next(Path('/root/isaacsim/extscache').glob('omni.sensors.nv.common-*'))
p=base/'bin/gmo_lib/include/GMOAuxiliaryDataTypes.h';lines=p.read_text().splitlines();hits=[]
for i,l in enumerate(lines):
 if any(k in l.lower() for k in ('tickstate','scancomplete','newscan','new_scan','startscan','start_scan')):hits.append({'line':i+1,'lines':lines[max(0,i-4):i+6]})
print(json.dumps({'path':str(p),'hits':hits}))
