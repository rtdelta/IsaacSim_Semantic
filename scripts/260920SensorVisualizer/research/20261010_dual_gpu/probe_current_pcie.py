"""Read only the currently assigned GPU PCI endpoints; do not reuse old addresses."""
import json
from pathlib import Path
import subprocess

def run(args):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=10)
        return {'exit_code':r.returncode,'stdout':r.stdout[:10000],'stderr':r.stderr[:2000]}
    except (OSError,subprocess.TimeoutExpired) as exc:return {'error':str(exc)}

inventory=run(['nvidia-smi','--query-gpu=index,pci.bus_id','--format=csv,noheader,nounits'])
out={'inventory':inventory,'endpoints':[],'ncu':run(['/usr/local/cuda/bin/ncu','--version'])}
for line in inventory.get('stdout','').splitlines():
    index,raw=[v.strip() for v in line.split(',')]
    domain,bus,device=raw.split(':');address=f'{int(domain,16):04x}:{bus.lower()}:{device.lower()}'
    chain=[];path=Path('/sys/bus/pci/devices')/address
    if path.exists():
        resolved=path.resolve()
        for p in (resolved,*resolved.parents):
            if not (p/'vendor').exists():continue
            row={'address':p.name}
            for field in ('current_link_speed','current_link_width','max_link_speed','max_link_width','numa_node'):
                try:row[field]=(p/field).read_text().strip()
                except OSError:pass
            chain.append(row)
    lspci=run(['lspci','-D','-vv','-s',address])
    if 'stdout' in lspci:lspci['stdout']='\n'.join(l for l in lspci['stdout'].splitlines() if 'LnkCap:' in l or 'LnkSta:' in l or 'LnkCap2:' in l)
    out['endpoints'].append({'gpu_index':int(index),'address':address,'chain':chain,'lspci':lspci})
params=Path('/proc/driver/nvidia/params')
if params.exists():out['counter_permission_setting']=[line for line in params.read_text().splitlines() if 'ProfilingAdminOnly' in line]
out['processes']=run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'])
print(json.dumps(out,indent=2))
