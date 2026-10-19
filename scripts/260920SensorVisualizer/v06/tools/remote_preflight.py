"""Read only, scoped to the current task and installed dependency metadata."""
import json
from pathlib import Path
import subprocess

def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return {'exit_code':p.returncode,'stdout':p.stdout[:10000],'stderr':p.stderr[:1000]}

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
print(json.dumps({'project':root.is_dir(),'v05_exists':(root/'v05').exists(),
    'scene':Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda').is_file(),
    'gpus':run(['nvidia-smi','--query-gpu=uuid,name,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits']),
    'dependencies':run(['/usr/bin/python3','-I','-c',"import importlib.metadata as m,json; r={};\nfor n in ['fastapi','uvicorn','starlette','websockets','paramiko']:\n try:r[n]=m.version(n)\n except m.PackageNotFoundError:r[n]=None\nprint(json.dumps(r))"]),
    'cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
    'memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip(),
    'app_processes':[{'pid':int(p.name),'program':('isaac/kit' if b'/kit/kit' in raw else 'sensor_visualizer')}
      for p in Path('/proc').iterdir() if p.name.isdigit() and (p/'cmdline').is_file()
      for raw in [((p/'cmdline').read_bytes() if (p/'cmdline').exists() else b'')]
      if b'/kit/kit' in raw or b'/260920SensorVisualizer/v0' in raw]},ensure_ascii=False))
