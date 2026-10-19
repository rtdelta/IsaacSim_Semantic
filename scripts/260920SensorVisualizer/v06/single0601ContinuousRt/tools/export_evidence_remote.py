"""Copy verified, task-created evidence into the project for audited SFTP delivery."""
import hashlib
import json
from pathlib import Path
import shutil
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
output=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt')
recording='recording_12b92d339a94453a8a7b1bb108335fd0'
source=output/'datasets'/recording
manifest=json.loads((source/'dataset_manifest.json').read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
if (source/'READY').read_text()!=sha(source/'dataset_manifest.json')+'\n':
    raise RuntimeError('Dataset READY hash mismatch')
for item in manifest['files']:
    p=source/item['path']
    if not p.resolve().is_relative_to(source.resolve()) or p.is_symlink() or p.stat().st_size!=item['size_bytes'] or sha(p)!=item['sha256']:
        raise RuntimeError('Actual dataset file integrity mismatch: '+item['path'])
if sum(p.stat().st_size for p in source.rglob('*') if p.is_file())>256*1024*1024:
    raise RuntimeError('Delivery copy exceeds the declared 256 MiB bound')
destination=root/'reports/deliverables'/recording
if destination.exists():
    raise RuntimeError('Existing delivery evidence is immutable')
shutil.copytree(source,destination)
print(json.dumps({'recording_id':recording,'directory':str(destination),'verified_files':len(manifest['files']),
                  'bytes':sum(p.stat().st_size for p in destination.rglob('*') if p.is_file())}))
