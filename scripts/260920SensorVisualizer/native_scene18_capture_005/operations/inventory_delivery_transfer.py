import hashlib,json,zipfile
from pathlib import Path
base=Path('/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643')
project=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18')
files=[]
def add(path,relative):
 if not path.is_file():raise FileNotFoundError(str(path))
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
 files.append({'remote':str(path),'relative':relative,'bytes':path.stat().st_size,'sha256':h.hexdigest()})
for path in sorted((base/'delivery_300').rglob('*')):
 if path.is_file():
  assert path.resolve().is_relative_to(base/'delivery_300')
  add(path,path.relative_to(base).as_posix())
for name in ('CaptureReport.md','run_summary.json','motion_plan.json','delivery_status.json'):add(base/name,name)
handoff=project/'handoff'
for path in sorted(handoff.rglob('*')):
 if path.is_file() and '__pycache__' not in path.parts:
  assert path.resolve().is_relative_to(handoff)
  add(path,'excavator_handoff/'+path.relative_to(handoff).as_posix())
report=handoff/'MeshRawToExcavator_Reconstruction_Handoff.md';assert report.is_file()
print(json.dumps({'files':files,'total_bytes':sum(r['bytes'] for r in files),'handoff_files':sum(r['relative'].startswith('excavator_handoff/') for r in files)}))
