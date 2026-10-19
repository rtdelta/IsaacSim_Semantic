"""Create an isolated project and a restorable source baseline without editing v06."""
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

project = Path(__file__).resolve().parents[2]
source = project / 'v06'
destination = project / 'v07'
assert not destination.exists() or not any(p.is_file() for p in destination.rglob('*')), 'v07 already contains files; inspect before proceeding'
stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup = project / 'backups' / (stamp + '_v07_baseline')
backup.mkdir(parents=True, exist_ok=False)
paths = [p for p in source.rglob('*') if p.is_file() and
         not set(p.relative_to(source).parts) & {'reports', '__pycache__'} and
         p.suffix not in ('.pyc', '.pyo')]
hashes = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
with zipfile.ZipFile(backup / 'v06_source.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
    for p in paths:
        archive.write(p, p.relative_to(source).as_posix())
with zipfile.ZipFile(backup / 'v06_source.zip') as archive:
    assert archive.testzip() is None
    assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name, digest in hashes.items())
for p in paths:
    relative = p.relative_to(source)
    if relative.parts[0] in ('docs', 'tools') or p.name.endswith('manifest.json'):
        continue
    relative = Path(*[part.replace('sensor_visualizer_v06', 'sensor_visualizer_v07') for part in relative.parts])
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix in ('.py', '.json', '.md', '.html', '.js', '.css', '.txt'):
        text = p.read_text(encoding='utf-8-sig').replace('v06', 'v07').replace('V06', 'V07').replace('SV06', 'SV07').replace('sv06', 'sv07')
        target.write_bytes(text.encode('utf-8'))
    else:
        target.write_bytes(p.read_bytes())
record = {'created_utc': datetime.now(timezone.utc).isoformat(), 'baseline': str(source),
          'backup': str(backup / 'v06_source.zip'), 'sha256': hashes,
          'old_source_modified': False, 'independent_package': 'sensor_visualizer_v07'}
(backup / 'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
(destination / 'baseline_manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'backup': str(backup), 'source_files': len(paths), 'project': str(destination)}))
