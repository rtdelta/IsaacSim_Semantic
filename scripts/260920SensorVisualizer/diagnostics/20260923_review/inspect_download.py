"""Select and hash the latest completed unified MCAP without modifying it."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

root = Path('/root/gpufree-data/semantic/output/sensor_visualizer')
folders = sorted((p for p in root.iterdir() if p.is_dir() and p.name.startswith('20') and (p/'session.json').is_file()), reverse=True)
recent = []
for folder in folders[:3]:
    session = json.loads((folder/'session.json').read_text())
    status_path = folder/'unified_export_status.json'
    status = json.loads(status_path.read_text()) if status_path.is_file() else {}
    recent.append({'name': folder.name, 'recording_state': session.get('state'), 'unified_state': status.get('state')})
folder = folders[0]
session = json.loads((folder/'session.json').read_text())
status = json.loads((folder/'unified_export_status.json').read_text())
if session.get('state') != 'finished' or status.get('state') != 'complete':
    raise RuntimeError('Latest session is not finalized: '+json.dumps(recent))
bag = folder/'bag_unified'
files = sorted(bag.glob('*.mcap')) + [bag/'metadata.yaml']
if not files or not list(bag.glob('*.mcap')):
    raise RuntimeError('No finalized unified MCAP')
files += [folder/name for name in ('session.json', 'capture_summary.json', 'unified_export_status.json', 'unified_export_report.json') if (folder/name).is_file()]
manifest = []
for path in files:
    if not path.resolve().is_relative_to(folder.resolve()):
        raise RuntimeError('Unexpected source path')
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Source is still changing')
    manifest.append({'relative': path.relative_to(folder).as_posix(), 'bytes': after.st_size,
                     'mtime_ns': after.st_mtime_ns, 'sha256': h.hexdigest()})
print(json.dumps({'session': str(folder), 'recent': recent, 'files': manifest,
                  'observed_utc': datetime.now(timezone.utc).isoformat(),
                  'metadata_yaml': (bag/'metadata.yaml').read_text()}))
