import hashlib,json
from pathlib import Path
root=next(Path('/root/isaacsim/extscache').glob('omni.sensors.nv.common-3.0.0*/bin/gmo_lib/include'))
result=[]
for p in root.glob('*.h'):
    data=p.read_text(errors='replace')
    if any(n in data for n in ('getModelOutputFromBuffer','LidarAuxiliaryData','getModelOutputSize')):
        result.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'text':data[:40000]})
print(json.dumps(result))
