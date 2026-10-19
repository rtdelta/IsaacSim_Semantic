import hashlib,json,subprocess,shutil
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
trace=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
manifest=json.loads((root/'reports/preserved_remote_hashes.json').read_text())
changed=[f for f,h in manifest.items() if not (root.parent/f).is_file() or hashlib.sha256((root.parent/f).read_bytes()).hexdigest()!=h]
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
scene_hash=hashlib.sha256(scene.read_bytes()).hexdigest()
procs=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().split(b'\0')
  if args[0].endswith(b'/kit/kit') or any(a.endswith(b'native_capture_quality_002/run.py') or a.endswith(b'native_capture_quality_002/wave.py') or a.endswith(b'native_capture_quality_002/reference_native.py') or a.endswith(b'native_capture_quality_002/reference_external.py') for a in args):
   procs.append({'pid':int(p.parent.name),'executable':args[0].decode(errors='replace')})
 except (OSError,IndexError):pass
result=json.loads((trace/'result.json').read_text())
files={}
for name in ('native.sqlite','native.nsys-rep'):
 p=trace/name;h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 files[name]={'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}
v={'preserved_source_files':len(manifest),'changed_old_sources':changed,'scene_sha256':scene_hash,
 'scene_unchanged':scene_hash=='ab2a2ef736030adba3420450f916420e705952a04fec163c05b545655fc7f0ae',
 'remaining_capture_processes':procs,'profile_capture_verified':result['profile_capture_verified'],
 'profile_files':files,'disk_free_gib':shutil.disk_usage(trace).free/1024**3,
 'gpu':subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,power.draw','--format=csv,noheader'],text=True,capture_output=True).stdout.strip()}
(trace.parent/'final_analysis/final_verification.json').write_text(json.dumps(v,indent=2))
print(json.dumps(v))
assert not changed and v['scene_unchanged'] and not procs and v['profile_capture_verified']
