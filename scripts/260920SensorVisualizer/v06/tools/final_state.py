"""Read task cleanup and source identity; never terminate discovered processes."""
import hashlib,json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
manifest=json.loads((root/'deployment_manifest.json').read_text())
changed=[n for n,h in manifest.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
old=json.loads((root/'baseline_manifest.json').read_text())['sha256'];base=root.parent/'v05'
old_changes=[n for n,h in old.items() if hashlib.sha256((base/n).read_bytes()).hexdigest()!=h]
processes=[]
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:raw=(p/'cmdline').read_bytes()
        except OSError:continue
        if b'/kit/kit' in raw or str(root).encode() in raw:
            if b'final_state.py' in raw:continue
            processes.append({'pid':int(p.name),'kit':b'/kit/kit' in raw,'v06':str(root).encode() in raw})
gpu=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.used,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
row={'deployed_files':len(manifest),'deployed_source_changes':changed,'v05_files':len(old),'v05_changes':old_changes,
     'remaining_related_processes':processes,'gpu':gpu}
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v06')
row['remaining_output_slot_files']=[str(p) for p in output.rglob('slot_*.bin')]
row['remaining_ram_slot_directories']=[p.name for p in Path('/dev/shm').glob('sv06_buffers_*')]
(root/'reports/final_state.json').write_text(json.dumps(row,indent=2));print(json.dumps(row))
