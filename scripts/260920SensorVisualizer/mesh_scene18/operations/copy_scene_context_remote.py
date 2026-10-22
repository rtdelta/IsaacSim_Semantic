import hashlib,shutil,json
from pathlib import Path
source=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
target=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/handoff/scene_context/combine_scene_18_terrain_fisheye_mesh.usda')
expected='e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79'
assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
if target.exists():assert hashlib.sha256(target.read_bytes()).hexdigest()==expected
else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
print(json.dumps({'scene_context_copied':True,'sha256':expected}))
