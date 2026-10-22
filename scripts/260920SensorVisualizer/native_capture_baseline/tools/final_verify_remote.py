"""Read-only original-code/USD and owned-process check."""
import hashlib,json,os,zipfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
changed=[];checked=0
with zipfile.ZipFile(root/'backups/single06_before_lab_20261011_101200.zip') as z:
 for name in z.namelist():
  if name.endswith('/'):continue
  p=root/'v06'/name
  if not p.resolve().is_relative_to(root/'v06'):raise RuntimeError('Unsafe backup member')
  checked+=1
  if not p.is_file() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(z.read(name)).digest():changed.append(name)
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
manifest=Path('/root/gpufree-data/semantic/output/native_capture_baseline/wave_ordinary_20261011_124852/C_record/sensor_manifest.json')
layers=json.loads(manifest.read_text())['used_layers'];layer_changes=[]
for row in layers:
 if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()!=row['sha256']:layer_changes.append(row['path'])
live=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  cmd=(p/'cmdline').read_bytes();executable=cmd.split(b'\0')[0].decode(errors='replace')
  if b'/kit/kit' in cmd.split(b'\0')[0] or b'native_capture_baseline/kit_entry.py' in cmd or b'native_capture_baseline/run.py' in cmd or b'native_capture_baseline/wave.py' in cmd:
   live.append({'pid':int(p.name),'executable':executable})
 except (OSError,ValueError):pass
result={'formal_files_checked':checked,'formal_changes':changed,'used_usd_layers_checked':len(layers),
 'used_usd_layer_changes':layer_changes,'scene_sha256':hashlib.sha256(scene.read_bytes()).hexdigest(),
 'live_owned_or_isaac_processes':live,'passed':not changed and not layer_changes and not live}
print(json.dumps(result))
