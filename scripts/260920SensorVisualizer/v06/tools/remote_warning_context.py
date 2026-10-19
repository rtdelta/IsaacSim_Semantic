import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
out={}
for name in ('offline_task.json','soak_task.json'):
    info=json.loads((root/'reports/native_owner'/name).read_text());lines=(Path(info['directory'])/'kit.log').read_text(errors='replace').splitlines()
    indexes=[i for i,l in enumerate(lines) if 'omni.hydratexture.plugin was already released' in l]
    out[name]={'first_context':lines[max(0,indexes[0]-5):indexes[0]+6] if indexes else [],'last':lines[indexes[-1]] if indexes else None,
        'samples':[lines[i] for i in indexes[:5]],'count':len(indexes)}
print(json.dumps(out))
