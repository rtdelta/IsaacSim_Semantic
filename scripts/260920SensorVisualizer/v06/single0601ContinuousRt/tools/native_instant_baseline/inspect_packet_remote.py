import gzip,json,struct,hashlib
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_instant_baseline/native005_20261015_v1/M_E/S0/r01/q01/continuous')
p=next((root/'gmo').glob('*.gz'));raw=gzip.decompress(p.read_bytes());magic,ma,mi,pa,size,count=struct.unpack_from('<IIIIQI',raw)
header=Path('/root/isaacsim/extscache/omni.sensors.nv.common-3.0.0+f9bf0dda.lx64.r.cp312/bin/gmo_lib/include/GenericModelOutput.h');lines=header.read_text().splitlines()
snippets=[{'line':i+1,'text':'\n'.join(lines[max(0,i-2):i+4])} for i,line in enumerate(lines) if any(s in line for s in ('sizeInBytes','bufferSize','getBaseGMOPtrFromBuffer','GMO_MAGIC','magicNumber'))]
print(json.dumps({'file':str(p),'buffer_bytes':len(raw),'declared_bytes':size,'count':count,'magic':hex(magic),'version':[ma,mi,pa],
 'tail_bytes':len(raw)-size,'tail_nonzero_bytes':sum(b!=0 for b in raw[size:]),'tail_sha256':hashlib.sha256(raw[size:]).hexdigest(),'installed_declarations':snippets}))
