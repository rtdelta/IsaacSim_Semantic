"""Read selected scene/configuration files and recent capture metadata only."""
import hashlib
import json
from pathlib import Path

assets = Path('/root/gpufree-data/IsaacSim_Asset')
project = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
out = {'scenes': [], 'files': {}, 'captures': [], 'snapshots': [], 'processes': []}
for p in sorted((assets / 'combine_stage').glob('*.usd*')):
    st = p.stat()
    out['scenes'].append({'name': p.name, 'size': st.st_size, 'mtime': st.st_mtime})
paths = [assets / 'combine_stage/combine_scene_15_surround_fisheye.usda',
         assets / 'sensor_set/camera_set/fish_eye_camera/fish_eye_camera.usda',
         project / 'config/sensors.json', project / 'reports/surround_fisheye/assembly.json',
         project / 'reports/surround_fisheye/result.json']
for p in paths:
    if p.is_file() and p.stat().st_size < 150000:
        raw = p.read_bytes()
        out['files'][str(p)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'text': raw.decode('utf-8')}
output = Path('/root/gpufree-data/semantic/output/sensor_visualizer')
if output.is_dir():
    sessions = sorted([p for p in output.iterdir() if p.is_dir() and (p / 'cameras').is_dir()],
                      key=lambda p: p.stat().st_mtime, reverse=True)[:4]
    for folder in sessions:
        row = {'path': str(folder), 'mtime': folder.stat().st_mtime, 'files': {}, 'images': {}}
        for rel in ['session.json', 'capture_summary.json', 'capture_index.jsonl']:
            p = folder / rel
            if p.is_file():
                if rel.endswith('.jsonl'):
                    with p.open() as f: row['files'][rel] = f.readline()[:16000]
                elif p.stat().st_size < 100000:
                    row['files'][rel] = p.read_text()
        for cam in sorted((folder / 'cameras').iterdir()):
            if not cam.is_dir(): continue
            for name in ['calibration.json', 'summary.json', 'frames.jsonl']:
                p = cam / name
                if p.is_file():
                    if name.endswith('.jsonl'):
                        with p.open() as f: row['files'][str(p.relative_to(folder))] = f.readline()[:20000]
                    elif p.stat().st_size < 30000:
                        row['files'][str(p.relative_to(folder))] = p.read_text()
            images = sorted((cam / 'images').glob('*.png'))
            row['images'][cam.name] = {'count': len(images), 'first': str(images[0]) if images else None,
                                       'last': str(images[-1]) if images else None}
        out['captures'].append(row)
    snapshots = output / 'camera_snapshots'
    if snapshots.is_dir():
        out['snapshots'] = [str(p) for p in sorted(snapshots.iterdir(), key=lambda p:p.stat().st_mtime, reverse=True)[:3]]
# No process environments or full commands: only relevant executable names and
# scene filenames already present in their arguments.
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        name=(p/'comm').read_text().strip()
        if any(x in name.lower() for x in ['kit','isaac']):
            args=(p/'cmdline').read_bytes().decode(errors='replace').split(chr(0))
            out['processes'].append({'pid':int(p.name),'name':name,
                'scene_arguments':[x for x in args if x.endswith(('.usd','.usda','.usdc'))]})
    except OSError: pass
print(json.dumps(out, ensure_ascii=False))
