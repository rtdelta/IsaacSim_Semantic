import json
from pathlib import Path
rep=next(Path('/root/isaacsim/extscache').glob('omni.replicator.core-*'))/'omni/replicator/core/scripts/utils/annotator_utils.py'
lines=rep.read_text().splitlines();windows=[]
for i,s in enumerate(lines):
    if s.startswith('def _reshape_output_ptr') or s.startswith('def _get_data_output_ptr'):
        windows.append((i,min(i+100,len(lines))))
windows.append((519,555))
texts=['\n'.join(str(n+1)+': '+lines[n] for n in range(a,b)) for a,b in windows]
warp_paths=list(Path('/root/isaacsim/extscache').glob('omni.warp.core-*'))+list(Path('/root/isaacsim/exts').glob('omni.warp.core*'))
warp=[]
for base in warp_paths:
    for p in base.glob('*/warp/context.py'):
        ls=p.read_text().splitlines()
        for i,s in enumerate(ls):
            if s.startswith('def get_device('):warp.append({'path':str(p),'snippet':'\n'.join(ls[i:i+55])})
print(json.dumps({'path':str(rep),'device_transfer_implementation':texts,'warp_cuda_alias':warp}))
