import json
from pathlib import Path
root=Path('/root/isaacsim')
rep=next((root/'extscache').glob('omni.replicator.core-*'))/'omni/replicator/core/scripts'
requests={
 rep/'utils/annotator_utils.py':[(449,528),(555,627),(790,875)],
 rep/'annotators.py':[(1683,1733)],
 root/'exts/isaacsim.core.throttling/isaacsim/core/throttling/extension.py':[(20,135)],
 root/'exts/isaacsim.core.rendering_manager/isaacsim/core/rendering_manager/impl/rendering_manager.py':[(87,130)]}
out=[]
for p,windows in requests.items():
    if not p.is_file():continue
    lines=p.read_text().splitlines()
    out.append({'path':str(p),'snippets':['\n'.join(str(i+1)+': '+lines[i] for i in range(start-1,min(end,len(lines)))) for start,end in windows]})
print(json.dumps(out))
