"""Create isolated native test engines and preserve pre-existing source files."""
import hashlib,json,shutil,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];base=root.parent
oldnames=('v06','single06_lab','native_capture_baseline','native_capture_quality_002','native_capture_continuous_pt_003')
excluded={'reports','__pycache__','backups','deploy_history','vendor','.venv-web','.git'}
hashes={}
for name in oldnames:
 for p in sorted((base/name).rglob('*')):
  if p.is_file() and not any(x in excluded for x in p.relative_to(base/name).parts):hashes[p.relative_to(base).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
record=root/'reports/preserved_local.json'
if record.exists():
 if json.loads(record.read_text())!=hashes:raise RuntimeError('Previous source files changed')
else:
 record.write_text(json.dumps(hashes,indent=2));(root/'backups').mkdir(exist_ok=True)
 with zipfile.ZipFile(root/'backups/pre_NC004_sources.zip','x',zipfile.ZIP_DEFLATED) as z:
  for rel in hashes:z.write(base/rel,rel)
source=base/'native_capture_continuous_pt_003'
for engine in ('frozen','continuous_rt','continuous_pt'):
 dest=root/'engines'/engine;(dest/'tools').mkdir(exist_ok=True);(dest/'config').mkdir(exist_ok=True)
 for rel in ('run.py','kit_entry.py','experiment.py','continuous.py','tools/validate_bag.py','tools/validate_groups.py','config/baseline.json'):
  shutil.copyfile(source/rel,dest/rel)
 def edit(rel,old,new):
  p=dest/rel;s=p.read_text(encoding='utf-8')
  if old not in s:raise RuntimeError('Expected source anchor absent: '+rel)
  p.write_text(s.replace(old,new,1),encoding='utf-8')
 edit('experiment.py',"    if kind=='reference':", "    if kind=='comparison_static':return [dict(name='comparison_'+spec['render_mode'],renderer=spec['render_mode'],warm=16 if spec['render_mode']=='RealTimePathTracing' else 1,formal=2 if spec['render_mode']=='RealTimePathTracing' else 1,repeat=spec.get('repeat',0),pose='static',**({'total_spp':spec['pt_total_spp']} if spec['render_mode']=='PathTracing' else {})) for _ in range(spec['measure_frames'])]\n    if kind=='reference':")
 if engine=='continuous_pt':
  edit('continuous.py','joint_targets=[0.,15.,-15.,0.]','joint_targets=[0.,0.,0.,0.]  # NC004: identical static pose for all configurations.')
  edit('continuous.py',"rgb=True,camera_params=True", "rgb=spec.get('extra_capture_png',True),camera_params=True")
  edit('continuous.py',"'quality_png_exported':'NVIDIA BasicWriter'", "'quality_png_exported':spec.get('extra_capture_png',True), 'diagnostic_basic_writer':'CameraParams only' if not spec.get('extra_capture_png',True) else 'RGB+CameraParams'")
  edit('tools/validate_groups.py',"    if sensor['kind']!='camera':continue", "    if sensor['kind']!='camera' or not spec.get('extra_capture_png',True):continue")
 (dest/'source_provenance.json').write_text(json.dumps({'source':str(source),'independent_copy':True,'changes':['static comparison case matrix','continuous PT static targets and no extra RGB PNG export'],'source_manifest':{rel:hashlib.sha256((source/rel).read_bytes()).hexdigest() for rel in ('run.py','kit_entry.py','experiment.py','continuous.py')}},indent=2))
print(json.dumps({'preserved_files':len(hashes),'engines':3}))
