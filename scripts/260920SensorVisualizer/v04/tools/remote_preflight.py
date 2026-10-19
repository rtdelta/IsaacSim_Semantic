"""Read project prerequisites only; no package installs or process changes."""
from pathlib import Path
import hashlib,json,shutil,subprocess

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
processes=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        fields=p.read_bytes().split(b'\0');args=[x.decode(errors='replace') for x in fields if x]
        if args and ('/kit/kit' in args[0] or any('record_worker.py' in a or 'supervise_v04.py' in a for a in args)):
            processes.append({'pid':int(p.parent.name),'program':args[0],
                              'project_args':[a for a in args[1:] if '260920SensorVisualizer' in a or 'sensor_visualizer' in a]})
    except OSError:pass
result={'project_parent':str(root.resolve()),'v04_exists':(root/'v04').exists(),
        'v04_symlink':(root/'v04').is_symlink(),'scene_exists':scene.is_file(),
        'scene_sha256':hashlib.sha256(scene.read_bytes()).hexdigest() if scene.is_file() else None,
        'kit_exists':Path('/root/isaacsim/kit/kit').is_file(),'ros_setup':Path('/opt/ros/jazzy/setup.bash').is_file(),
        'displays':[p.name for p in Path('/tmp/.X11-unix').glob('X*')],
        'active_project_processes':processes,'disk_free_bytes':shutil.disk_usage(root).free}
gpu=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
result['gpu']=gpu.stdout.strip()
print(json.dumps(result))
