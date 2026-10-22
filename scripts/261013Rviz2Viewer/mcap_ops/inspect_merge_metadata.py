import json
from pathlib import Path
root = Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300/capture/captures/20261013_142524_685978_f13b03ee')
for name in ['bag_unified', 'bag_merged']:
    path = root / name
    print(json.dumps({'bag': name, 'files': [{'name': p.name, 'bytes': p.stat().st_size} for p in path.iterdir() if p.is_file()], 'metadata': (path / 'metadata.yaml').read_text()}))
