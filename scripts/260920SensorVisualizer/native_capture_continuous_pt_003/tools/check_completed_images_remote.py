import json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
out=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
groups=[json.loads(l) for l in (out/'groups.jsonl').read_text().splitlines()]
result=[]
for g in groups:
 for topic,im in g['images'].items():
  sid=topic.split('/')[2].removeprefix('fisheye_');files=[p for p in (out/'native_basic_images').rglob(f"rgb_{g['group']:04d}.png") if any('NativeBaseline_'+sid in part for part in p.parts)]
  sha=hashlib.sha256(np.asarray(Image.open(files[0]).convert('RGB')).tobytes()).hexdigest() if len(files)==1 else None
  result.append({'group':g['group'],'camera':sid,'files':len(files),'equal':sha==im['sha256']})
print(json.dumps(result))
