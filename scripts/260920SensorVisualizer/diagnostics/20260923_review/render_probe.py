"""Read render configuration evidence and sample-file manifests; no scene execution."""
from pathlib import Path
from collections import Counter
import hashlib, json, re

session = Path('/root/gpufree-data/semantic/output/sensor_visualizer/20260923_102450_024594_6ccb02')
manifest = json.loads((session/'session.json').read_text())
scene = manifest['scene']
result = {'session': str(session), 'root_layer': scene['root_layer'], 'used_layers': scene['used_layers'], 'cameras': {}, 'files': []}
for camera in ('front', 'back', 'left', 'right'):
    folder = session/'cameras'/camera
    calibration = json.loads((folder/'calibration.json').read_text())
    rows = [json.loads(line) for line in (folder/'frames.jsonl').read_text().splitlines()]
    selected = [rows[0], rows[-1]]
    result['cameras'][camera] = {'calibration': calibration, 'frame_count': len(rows),
        'samples': [{k: row.get(k) for k in ('simulation_time', 'image', 'camera_usd_to_world', 'render_pose_max_abs_error')} for row in selected]}
    for row in selected:
        path = folder/row['image']
        stat = path.stat()
        result['files'].append({'relative': path.relative_to(session).as_posix(), 'bytes': stat.st_size,
            'mtime_ns': stat.st_mtime_ns, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
log = Path('/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0/kit_20260923_095639.log')
lines = log.read_text(errors='replace').splitlines()
pattern = re.compile(r'rendermode|PathTracing|RayTracedLighting|Real.?Time|dlss|ngx|antialias|motionblur|depth.of.field|gsplat|gaussian|particle.field|asset.*(load|fail)|load.*(asset|stage)|shader.*compil', re.I)
matches = [line[:1200] for line in lines if pattern.search(line)]
result['log_render_matches'] = matches[:100] + matches[-60:] if len(matches)>160 else matches
result['log_match_count'] = len(matches)
root = Path('/root/isaacsim')
paths = [root/'apps/isaacsim.exp.full.kit', root/'apps/isaacsim.exp.base.kit', root/'apps/isaacsim.exp.base.python.kit']
for base in (root/'extscache', root/'exts', root/'kit/exts'):
    for pattern_name in ('omni.hydra.rtx-*', 'omni.rtx.settings.core-*', 'isaacsim.app.setup*'):
        paths.extend(p/'config/extension.toml' for p in base.glob(pattern_name))
result['config_matches'] = []
for path in paths:
    if not path.is_file():
        continue
    excerpts = [{'line': i+1, 'text': line} for i,line in enumerate(path.read_text(errors='replace').splitlines())
                if re.search(r'rendermode|PathTracing|RayTracedLighting|dlss|ngx|antialias|motionBlur|depthOfField|rt2|domeLight|lazy|load', line, re.I)]
    if excerpts:
        result['config_matches'].append({'path': str(path), 'matches': excerpts[:90]})
result['stage_render_lines'] = []
for name in scene['used_layers']:
    path = Path(name)
    if path.suffix != '.usda' or not path.is_file() or path.stat().st_size > 10*1024*1024:
        continue
    text = path.read_text(errors='replace')
    if any(s in text for s in ('renderSettings', 'fStop', 'focusDistance', 'Gaussian', 'ParticleField')):
        excerpts = [{'line': i+1, 'text': line[:500]} for i,line in enumerate(text.splitlines()) if
          re.search(r'renderSettings|rendermode|PathTracing|RayTracedLighting|dlss|fStop|focusDistance|shutter|Gaussian|ParticleField|primvars:.*(scale|density|opacity)|payload|references|visibility',line)]
        result['stage_render_lines'].append({'path': name, 'excerpts': excerpts[:70]})
result['kit_render_flags'] = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        if (p/'comm').read_text().strip() == 'kit':
            args = (p/'cmdline').read_bytes().decode(errors='replace').split('\0')
            result['kit_render_flags'].append({'pid': p.name, 'flags': [a for a in args if a.startswith('--/') and re.search(r'render|rtx|async|multiGpu|fabric', a, re.I)]})
    except OSError:
        pass
print(json.dumps(result, ensure_ascii=False))
