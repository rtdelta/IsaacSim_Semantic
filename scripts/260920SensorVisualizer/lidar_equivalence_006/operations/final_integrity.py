import json,hashlib
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
d=json.loads((out/'baseline_pose/dependencies.json').read_text());result={'dependencies_checked':len(d),'changed_assets':[p for p,h in d.items() if sha(Path(p))!=h],'remaining_kit':[]}
p=R/'original_remote_manifest.json'
if p.exists():
 original=json.loads(p.read_text());result['original_source_files_checked']=len(original);result['original_source_mismatches']=[p for p,h in original.items() if not Path(p).is_file() or sha(Path(p))!=h]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  v=p.read_bytes().split(b'\0')
  if v[0].endswith(b'/kit/kit'):result['remaining_kit'].append(int(p.parent.name))
 except OSError:pass
p=out/'native_pause_no_probe/capture/result.json'
if p.exists():
 d=json.loads(p.read_text());result['pause_confirm']={k:d.get(k) for k in ('state','engine_exit','validation_exit','group_validation_exit')}
print(json.dumps(result,indent=2))
