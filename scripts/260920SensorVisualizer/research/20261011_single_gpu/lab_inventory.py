"""Read only: source identity, selected processes and existing trajectory metadata."""
import hashlib, json, os, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
out={'sources':{},'kit_processes':[],'trajectories':[]}
for p in sorted((root/'v06').rglob('*.py')):
    if any(x in p.parts for x in ('__pycache__','reports','deploy_history')):continue
    out['sources'][str(p.relative_to(root/'v06'))]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in Path('/proc').glob('[0-9]*'):
    try:
        args=(p/'cmdline').read_bytes().split(b'\0')
        if args and b'/kit/kit' in args[0]:
            out['kit_processes'].append({'pid':int(p.name),'executable':os.readlink(p/'exe'),
                'entry':[a.decode(errors='replace') for a in args if a.endswith(b'.py') or a==b'--no-window']})
    except (OSError,ValueError):pass
report=root/'v06/reports/baseline_performance_suite.json'
if report.is_file():
    r=json.loads(report.read_text());out['baseline_report']=r
    directory=Path(r.get('directory',''))
    t=directory/'input_trajectory'
    out['trajectory_files']=[str(p) for p in t.glob('*')] if t.is_dir() else []
out['gpu']=subprocess.run(['nvidia-smi','--query-gpu=index,name,uuid,utilization.gpu,memory.used,pcie.link.gen.current',
                          '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10).stdout
out['tools']={p:Path(p).is_file() for p in ('/root/isaacsim/kit/kit',
 '/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys','/usr/local/cuda/bin/ncu')}
print(json.dumps(out,indent=2))
