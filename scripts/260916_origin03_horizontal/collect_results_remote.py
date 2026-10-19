"""Read-only release evidence and source-file preservation check."""
import hashlib, json
from pathlib import Path
base=Path('/root/gpufree-data/IsaacSim_Asset')
asset=base/'excavator_module_set/Sim_Fangshan_02'
project=Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer')
qa=project/'validation/results/origin03_horizontal'
report=json.loads((asset/'Excavator_Fangshan_05_origin03_data/validation.json').read_text())
for name,expected in report['original_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
for key,hash_key in [('asset','asset_sha256'),('scene','scene_sha256')]:
    assert hashlib.sha256(Path(report[key]).read_bytes()).hexdigest()==report[hash_key],key
receipt=json.loads((project/'DEPLOYMENT_ORIGIN03.json').read_text())
for name,expected in receipt['files'].items():
    assert hashlib.sha256((project/name).read_bytes()).hexdigest()==expected,name
sources={
    'sources/Excavator_Fangshan_05_origin03.usda':asset/'Excavator_Fangshan_05_origin03.usda',
    'sources/combine_scene_11_origin03.usda':base/'combine_stage/combine_scene_11_origin03.usda',
    'asset_validation.json':asset/'Excavator_Fangshan_05_origin03_data/validation.json',
    'payload_validation.json':asset/'Excavator_Fangshan_05_origin03_data/payload_validation.json',
    'kinematics_origin03.json':asset/'Excavator_Fangshan_05_origin03_data/kinematics_origin03.json',
    'kit_validation.json':qa/'kit_validation.json',
    'bag_validation.json':qa/'bag_validation.json',
    'deployment.json':project/'DEPLOYMENT_ORIGIN03.json'}
data={name:p.read_text() for name,p in sources.items() if p.exists()}
data['preservation.json']=json.dumps({'passed':True,'original_files_checked':len(report['original_sha256']),
    'new_asset_and_scene_hashes_verified':True,'deployed_files_checked':len(receipt['files']),
    'backups':sorted(str(p) for p in (project/'backups').glob('origin03_horizontal_*'))},indent=2)
print(json.dumps(data))
