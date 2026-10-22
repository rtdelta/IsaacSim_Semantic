"""Read-only task-scoped preflight; no imports from unreviewed remote project code."""
import hashlib,json,shutil,subprocess
from pathlib import Path
base=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
kit=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        argv=p.read_bytes().split(b'\0')
        if argv[0].endswith(b'/kit/kit'):kit.append({'pid':int(p.parent.name),'executable':argv[0].decode(errors='replace')})
    except OSError:pass
sources=['native_scene18_capture_005/config/baseline.json','single06_lab/frozen_runtime/config/offline.json','single06_lab/frozen_runtime/config/robot.json']
print(json.dumps({'scene_exists':scene.is_file(),'scene_sha256':hashlib.sha256(scene.read_bytes()).hexdigest() if scene.is_file() else None,'free_gib':shutil.disk_usage('/root/gpufree-data').free/1024**3,'kit_processes':kit,'sources':{s:(base/s).is_file() for s in sources},'task_directory_exists':(base/'lidar_equivalence_006').exists(),'gpu':subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=15).stdout},indent=2))
