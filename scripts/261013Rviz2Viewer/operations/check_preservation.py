import hashlib,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
source=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006/legacy')
manifest=json.loads((root/'source_provenance.json').read_text())['files']
differences=[]
for rel,sha in manifest.items():
    p=source/rel
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:differences.append(rel)
dependency=Path('/root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531/baseline_pose/dependencies.json')
dependencies=json.loads(dependency.read_text()) if dependency.exists() else {}
asset_differences=[path for path,sha in dependencies.items() if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha]
value={'source_checked_files':len(manifest),'source_differences':differences,'source_preserved':not differences,'dependency_checked_files':len(dependencies),'asset_differences':asset_differences,'assets_preserved':bool(dependencies) and not asset_differences}
(root/'reports/preservation.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
