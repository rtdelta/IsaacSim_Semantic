"""Read installed NVRTC exported symbol ranges; no library loading or modification."""
import hashlib,json,subprocess,struct
from pathlib import Path
tool=Path('/usr/bin/nm');out={'nm_available':tool.is_file(),'modules':[]}
if tool.is_file():
 for p in Path('/root/isaacsim/extscache').glob('omni.sensors.nv.common-*/bin/libnvrtc.so*'):
  if not p.is_file():continue
  result=subprocess.run([str(tool),'-D','-S','--defined-only',str(p)],capture_output=True,text=True,timeout=15)
  symbols=[]
  for line in result.stdout.splitlines():
   fields=line.split()
   if len(fields)==4 and fields[3].startswith('nvrtc'):
    symbols.append({'address':int(fields[0],16),'size':int(fields[1],16),'name':fields[3]})
  with p.open('rb') as f:
   header=f.read(64)
   if header[:6]!=b'\x7fELF\x02\x01':raise RuntimeError('Expected ELF64 little-endian library')
   offset=struct.unpack_from('<Q',header,32)[0];entry_size,count=struct.unpack_from('<HH',header,54)
   segments=[]
   for i in range(count):
    f.seek(offset+i*entry_size);record=struct.unpack('<IIQQQQQQ',f.read(56))
    if record[0]==1:segments.append({'file_offset':record[2],'virtual_address':record[3],'file_size':record[5],'memory_size':record[6]})
  out['modules'].append({'path':str(p),'resolved_path':str(p.resolve()),'symbols':symbols,'load_segments':segments,'exit_code':result.returncode})
print(json.dumps(out,indent=2))
