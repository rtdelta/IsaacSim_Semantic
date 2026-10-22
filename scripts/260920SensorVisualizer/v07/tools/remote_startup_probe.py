import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
status=json.loads((root/'reports/native_validation_status.json').read_text());directory=Path(status['directory'])
log=(directory/'v06/kit.log').read_text(errors='replace').splitlines()
selected=[line for line in log if any(word in line.lower() for word in ('error','vulkan','device','nvidia','gpu','license','eula','render','display','thread','sv06'))]
gpu=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu,display_active','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
print(json.dumps({'selected_startup_lines':selected[:60]+selected[-25:],'gpu':gpu.stdout,
                  'project_logs':[str(p) for p in directory.rglob('manifest*.json')],
                  'displays':[p.name for p in Path('/tmp/.X11-unix').glob('X*')]}))
