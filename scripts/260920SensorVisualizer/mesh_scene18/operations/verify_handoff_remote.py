import hashlib,json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/handoff')
p=subprocess.run(['python3','-I','-S','-B',str(root/'verify_package.py')],capture_output=True,text=True,timeout=45)
asset=Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_Mesh_Contract')
verification=json.loads((root/'evidence/rebuild_verification.json').read_text())
unchanged={rel:hashlib.sha256((asset/rel).read_bytes()).hexdigest()==row['reference_sha256'] for rel,row in verification['files'].items()}
facts=json.loads((root/'evidence/source_facts.json').read_text())
scene_unchanged=hashlib.sha256(Path(facts['scene']['path']).read_bytes()).hexdigest()==facts['scene']['sha256']
source_unchanged=hashlib.sha256(Path(facts['source']['path']).read_bytes()).hexdigest()==facts['source']['sha256']
print(json.dumps({'package_verification':json.loads(p.stdout) if p.returncode==0 else p.stdout,'stderr':p.stderr,'formal_asset_unchanged':unchanged,'scene18_unchanged':scene_unchanged,'source_mesh_unchanged':source_unchanged}))
assert p.returncode==0 and all(unchanged.values()) and scene_unchanged and source_unchanged
