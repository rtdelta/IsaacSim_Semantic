"""Inspect installed SDK APIs and driver capabilities without starting Isaac."""
import ctypes,json,re,subprocess
from pathlib import Path
base=Path('/root/isaacsim')
def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=20)
    return {'exit_code':p.returncode,'stdout':p.stdout[-6000:],'stderr':p.stderr[-2000:]}
pcie=command(['nvidia-smi','--query-gpu=index,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max','--format=csv,noheader'])
profiler=[]
for parent in (Path('/opt/nvidia'),Path('/usr/local'),Path('/root/gpufree-data/semantic/tools')):
    if parent.exists():
        for pattern in ('nsight-systems*/bin/nsys','nsight-systems/*/bin/nsys','cuda*/nsight-systems*/bin/nsys','nsys/bin/nsys'):
            profiler.extend(str(p) for p in parent.glob(pattern))
found=[]
needles=('optimize_render_products','def render(', 'rendering_enabled','asyncHandshake',
         'set_gpu','gpuDevice','device_index','do_array_copy','def get_data(',
         'copy_to_host','wait_for_render','enable_async','threadCount','maxThreadCount')
extensions=[]
for parent in (base/'exts',base/'extscache'):
    for prefix in ('isaacsim.core.rendering_manager','omni.replicator.core','isaacsim.core.throttling','isaacsim.simulation_app'):
        extensions.extend(parent.glob(prefix+'*'))
for ext in extensions:
    snippets=[]
    for p in list(ext.rglob('*.py'))+list(ext.rglob('extension.toml')):
        if '/tests/' in str(p) or p.stat().st_size>800000:continue
        lines=p.read_text(errors='replace').splitlines()
        hits=[(n+1,s.strip()) for n,s in enumerate(lines) if any(w in s for w in needles)]
        if hits:snippets.append({'path':str(p),'hits':hits[:18]})
    found.append({'extension':str(ext),'api_hits':snippets[:22]})
capabilities={}
try:
    lib=ctypes.CDLL('libcuda.so.1');code=lib.cuInit(0)
    capabilities['cuInit']=code
    if code==0:
        count=ctypes.c_int();assert lib.cuDeviceGetCount(ctypes.byref(count))==0
        devices=[];header=Path('/usr/local/cuda/include/cuda.h').read_text()
        attrs={n:int(m.group(1)) for n in ('ASYNC_ENGINE_COUNT','CONCURRENT_KERNELS','CAN_MAP_HOST_MEMORY','UNIFIED_ADDRESSING','HOST_NATIVE_ATOMIC_SUPPORTED')
               if (m:=re.search(r'CU_DEVICE_ATTRIBUTE_'+n+r'\s*=\s*(\d+)',header))}
        for i in range(count.value):
            name=ctypes.create_string_buffer(256);bus=ctypes.create_string_buffer(32)
            lib.cuDeviceGetName(name,256,i);lib.cuDeviceGetPCIBusId(bus,32,i)
            values={}
            for n,attr in attrs.items():
                v=ctypes.c_int();ret=lib.cuDeviceGetAttribute(ctypes.byref(v),attr,i);values[n]={'value':v.value,'code':ret}
            peers={}
            for j in range(count.value):
                if i==j:continue
                v=ctypes.c_int();ret=lib.cuDeviceCanAccessPeer(ctypes.byref(v),i,j);peers[str(j)]={'value':v.value,'code':ret}
            devices.append({'cuda_ordinal':i,'name':name.value.decode(),'pci_bus':bus.value.decode(),'attributes':values,'peer_access':peers})
        capabilities['devices']=devices
except Exception as exc:capabilities['error']=type(exc).__name__+': '+str(exc)
print(json.dumps({'pcie':pcie,'profiler_candidates':profiler,'sdk':found,'cuda_driver_read_only':capabilities,
                  'notes':'No CUDA contexts, buffers, kernels, Isaac application or project processes created.'}))
