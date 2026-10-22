"""Read-only GPU counters/tool inventory and negotiated PCIe capability probe."""
import ctypes
import ctypes.util
import json
from pathlib import Path
import shutil
import subprocess
import time

def command(args):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=10)
        return {'exit_code':r.returncode,'stdout':r.stdout[:18000],'stderr':r.stderr[:2000]}
    except (OSError,subprocess.TimeoutExpired) as exc:return {'error':type(exc).__name__+': '+str(exc)}

out={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'intent':'read; no installation, profiler enablement or benchmark',
     'tools':{name:shutil.which(name) for name in ('nvidia-smi','dcgmi','nv-hostengine','dcgm-exporter','nsys','ncu','lspci')},
     'commands':{},'cuda':[],'pcie_paths':[]}
out['commands']['gpu_inventory']=command(['nvidia-smi','--query-gpu=index,name,uuid,pci.bus_id,driver_version,pcie.link.gen.max,pcie.link.gen.current,pcie.link.width.max,pcie.link.width.current,clocks.max.sm,clocks.current.sm,power.limit','--format=csv,noheader,nounits'])
out['commands']['pci_topology']=command(['nvidia-smi','topo','-m'])
out['commands']['pcie_sample']=command(['nvidia-smi','dmon','-s','t','-c','1'])
for base in ('/opt/nvidia/nsight-systems','/opt/nvidia/nsight-compute','/usr/local/cuda/extras/CUPTI','/usr/lib/x86_64-linux-gnu/libdcgm.so'):
    p=Path(base);out.setdefault('known_tool_paths',{})[base]=p.exists()
if out['tools']['dcgmi']:
    out['commands']['dcgm_version']=command([out['tools']['dcgmi'],'--version'])
    out['commands']['dcgm_profile_catalogue']=command([out['tools']['dcgmi'],'profile','--list','--entity-id','gpu:0'])
try:
    cuda=ctypes.CDLL(ctypes.util.find_library('cuda') or 'libcuda.so.1')
    def check(code):
        if code:raise RuntimeError('CUDA status '+str(code))
    check(cuda.cuInit(0));count=ctypes.c_int();check(cuda.cuDeviceGetCount(ctypes.byref(count)))
    for index in range(count.value):
        dev=ctypes.c_int();check(cuda.cuDeviceGet(ctypes.byref(dev),index))
        name=ctypes.create_string_buffer(128);pci=ctypes.create_string_buffer(40)
        check(cuda.cuDeviceGetName(name,128,dev));check(cuda.cuDeviceGetPCIBusId(pci,40,dev))
        row={'cuda_ordinal':index,'name':name.value.decode(),'pci_bus_id':pci.value.decode()}
        for key,attribute in [('multiprocessor_count',16),('compute_capability_major',75),('compute_capability_minor',76),('async_engine_count',40)]:
            value=ctypes.c_int();code=cuda.cuDeviceGetAttribute(ctypes.byref(value),attribute,dev)
            row[key]=value.value if code==0 else {'status':code}
        out['cuda'].append(row)
except Exception as exc:out['cuda_error']=type(exc).__name__+': '+str(exc)
for address in ('0000:34:00.0','0000:35:00.0'):
    endpoint=Path('/sys/bus/pci/devices')/address
    chain=[]
    if endpoint.exists():
        resolved=endpoint.resolve()
        for device in (resolved,*resolved.parents):
            if not (device/'vendor').exists():continue
            record={'address':device.name}
            for key in ('current_link_speed','current_link_width','max_link_speed','max_link_width','numa_node'):
                try:record[key]=(device/key).read_text().strip()
                except OSError:pass
            chain.append(record)
    out['pcie_paths'].append({'endpoint':address,'chain':chain})
    if out['tools']['lspci']:
        r=command([out['tools']['lspci'],'-D','-vv','-s',address])
        if 'stdout' in r:r['stdout']='\n'.join(line for line in r['stdout'].splitlines() if 'LnkCap:' in line or 'LnkSta:' in line or 'LnkCap2:' in line or 'LnkSta2:' in line or 'Access denied' in line)
        out['commands']['lspci_'+address]=r
print(json.dumps(out,indent=2))
