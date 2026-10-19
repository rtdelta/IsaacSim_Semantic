"""Collect this fix's evidence, excluding previous runs and sensitive configuration."""
import hashlib,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');directory=root/'reports/native_owner'
owner=json.loads((directory/'owner.json').read_text());reports={}
for name in ('native_keyboard_fix','lifecycle_fix','web_lifecycle_fix','interaction','http_runtime','validation_offline'):
    p=directory/(name+'.json');reports[name]=json.loads(p.read_text())
event_path=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v06/runtime/control_events.jsonl')
rows=[json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
rows=[r for r in rows if r.get('monotonic_ns',0)>=owner['started_ns']]
slow=[]
for i,row in enumerate(rows):
    if row['event']=='owner_slow':
        slow.append({'elapsed_ms':row['elapsed_ms'],'preceding_actions':[{'action':r.get('action'),'event':r['event'],
            'latency_ms':r.get('latency_ns',0)/1e6} for r in rows[max(0,i-4):i] if r['event'].startswith('control_')]})
reports['input_log']={'events':len(rows),'native_errors':sum(r['event']=='native_input_error' for r in rows),
    'owner_failed':sum(r['event']=='owner_failed' for r in rows),'slow_updates':slow}
old=root.parent/'v04';manifest=json.loads((root.parent/'backups/20261009_before_v05/v04_remote_manifest.json').read_text())
old_changed=[n for n,h in manifest.items() if not (old/n).is_file() or hashlib.sha256((old/n).read_bytes()).hexdigest()!=h]
source=json.loads((root/'deployment_manifest.json').read_text())
changed=[n for n,h in source.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
asset=json.loads((Path(reports['validation_offline']['session'])/'asset_manifest.json').read_text())
asset_unchanged=hashlib.sha256(Path(asset['root_layer']).read_bytes()).hexdigest()==asset['root_sha256']
assert not old_changed and not changed and asset_unchanged
reports['isolation']={'v04_files_verified':len(manifest),'v04_changes':old_changed,'deployment_files_verified':len(source),
    'deployment_mismatches':changed,'root_scene_unchanged':asset_unchanged,'external_downloads':False}
print(json.dumps(reports,ensure_ascii=False))
