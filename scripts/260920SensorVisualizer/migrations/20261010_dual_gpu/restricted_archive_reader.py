"""Forced SSH command: only probe or read this immutable migration archive."""
import hashlib,json,os,sys
from pathlib import Path
work=Path('/root/gpufree-data/.migration_sensor_20261010_dual')
meta=json.loads((work/'archive_metadata.json').read_text())
command=os.environ.get('SSH_ORIGINAL_COMMAND','')
if command=='probe':
    print(json.dumps({'task':'sensor-visualizer-dual-migration-20261010',**meta}));sys.exit(0)
if command!='read':sys.exit(64)
p=work/'assets_and_code.tar.gz'
if p.stat().st_size!=meta['archive_bytes']:sys.exit(65)
with p.open('rb') as f:
    for c in iter(lambda:f.read(1048576),b''):sys.stdout.buffer.write(c)
sys.stdout.buffer.flush()
