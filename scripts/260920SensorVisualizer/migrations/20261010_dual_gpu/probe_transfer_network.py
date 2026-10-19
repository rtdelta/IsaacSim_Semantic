import json,socket,importlib.util
from pathlib import Path
result={}
try:
    with socket.create_connection(('120.209.70.195',30729),timeout=5) as s:
        result['source_ssh_reachable']=s.recv(128).startswith(b'SSH-')
except OSError as exc:result.update(source_ssh_reachable=False,error=type(exc).__name__)
result['pxr_system_available']=importlib.util.find_spec('pxr') is not None
result['usd_library_paths']=[str(p) for p in Path('/root/isaacsim/extscache').glob('omni.usd.libs-*/pxr')]
result['usd_plugin_paths']=[str(p) for p in Path('/root/isaacsim/kit/exts').glob('omni.usd.libs*/pxr')]
print(json.dumps(result))
