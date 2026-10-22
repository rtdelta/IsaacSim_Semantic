import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab')
r=json.loads((root/'reports/latest_execution.json').read_text());out=Path(r['directory'])
result={'files':[{'name':p.name,'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()]}
for name in ('engine.log','result.json'):
 p=out/name
 if p.is_file():
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-14000));result[name]=f.read().decode(errors='replace')
result['capture_help']=subprocess.run(['/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys',
  'profile','--help'],capture_output=True,text=True,timeout=10).stdout
print(json.dumps(result,indent=2))
