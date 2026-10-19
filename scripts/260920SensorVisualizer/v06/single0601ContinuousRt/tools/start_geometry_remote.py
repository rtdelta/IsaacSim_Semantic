"""Launch explicitly separate ideal-surface diagnostics after other GUI tests finish."""
import hashlib,json,os,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:
            if b'/kit/kit' in (p/'cmdline').read_bytes():raise RuntimeError('An Isaac process is running')
        except FileNotFoundError:pass
log=root/'reports'/('geometry_launch_'+time.strftime('%Y%m%d_%H%M%S')+'.log')
env=os.environ.copy()
env.update(DISPLAY=':20',S0601_FORCE_BARRIER='1',S0601_MATRIX=str(root/'config/acceptance_geometry.json'))
with log.open('xb') as f:
    process=subprocess.Popen(['/usr/bin/python3','-B',str(root/'run_capture.py'),'--job',str(root/'config/mixed_pair.json')],cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':process.pid,'log':str(log),'project':str(root),'launched_monotonic_ns':str(time.monotonic_ns()),'entrypoint_sha256':hashlib.sha256((root/'run_in_isaac.py').read_bytes()).hexdigest(),'matrix':env['S0601_MATRIX']}
(root/'reports/record_process.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
