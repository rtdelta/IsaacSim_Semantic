import hashlib,json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003')
saved=json.loads((root/'reports/preserved_remote_hashes.json').read_text());changed=[]
for rel,h in saved.items():
 p=root.parent/rel
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:changed.append(rel)
out=Path('/root/gpufree-data/semantic/output/native_capture_continuous_pt_003/continuous_pt1024_20261012_060128')
manifest=json.loads((out/'sensor_manifest.json').read_text());asset_changes=[]
for row in manifest['used_layers']:
 p=Path(row['path'])
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:asset_changes.append(row['path'])
alive=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  cmd=p.read_bytes()
  if cmd.split(b'\0')[0].endswith(b'/kit/kit') or b'native_capture_continuous_pt_003/run.py' in cmd:alive.append(int(p.parent.name))
 except OSError:pass
p=subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc003',str(root/'tools/analyze_continuous.py'),str(out)],capture_output=True,text=True)
if p.returncode:raise RuntimeError('Analysis failed: '+p.stderr[-2000:])
q=subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
report={'prior_source_files_checked':len(saved),'prior_source_changes':changed,'asset_layers_checked':len(manifest['used_layers']),'asset_layer_changes':asset_changes,'remaining_kit_or_nc003_runner_pids':alive,'gpu':q.stdout.strip(),'render_analysis':json.loads(p.stdout)}
(root/'reports/final_verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if changed or asset_changes or alive:raise SystemExit(1)
