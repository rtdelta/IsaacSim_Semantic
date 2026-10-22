"""007 read-only installed contracts and instance inventory; no Kit import."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
sdk=Path('/root/isaacsim')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=json.loads((ROOT/'config/native_instant_baseline/main_code_lock.json').read_text())
diff=[f['path'] for f in lock['files'] if not (ROOT/f['path']).is_file() or sha(ROOT/f['path'])!=f['sha256']]
processes=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  c=(p/'cmdline').read_bytes()
  if b'/kit/kit' in c or (str(ROOT).encode() in c and b'--worker' in c):processes.append({'pid':p.name,'cmd':c.decode(errors='replace').replace('\0',' ')[:600]})
 except OSError:pass
files=[];assets=[]
for base in (sdk/'exts',sdk/'extscache'):
 for p in base.rglob('*'):
  if not p.is_file():continue
  s=str(p)
  if ('isaacsim.sensors.experimental.rtx' in s and p.suffix in ('.py','.md','.rst')) or p.name in ('GenericModelOutput.h','GMOAuxiliaryData.h'):
   files.append({'path':s,'bytes':p.stat().st_size,'sha256':sha(p)})
  if p.suffix.lower() in ('.usd','.usda','.usdc','.json') and ('rotary' in p.name.lower() or 'lidar' in s.lower() and 'example' in p.name.lower()):
   assets.append({'path':s,'bytes':p.stat().st_size,'sha256':sha(p)})
assetroot=Path('/root/gpufree-data/IsaacSim_Asset')
for p in assetroot.rglob('*'):
 if p.is_file() and p.suffix.lower() in ('.usd','.usda','.usdc','.json') and ('rotary' in p.name.lower() or 'example' in p.name.lower() and 'lidar' in str(p).lower()):
  assets.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
print(json.dumps({'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,driver_version,memory.used','--format=csv,noheader,nounits'],text=True).strip(),'isaac':(sdk/'VERSION').read_text().strip(),'free_bytes':shutil.disk_usage(ROOT).free,'processes':processes,'old_lock_files':len(lock['files']),'old_lock_differences':diff,'installed_files':files,'example_assets':assets}))
