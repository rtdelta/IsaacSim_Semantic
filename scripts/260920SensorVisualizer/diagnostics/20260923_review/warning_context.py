from pathlib import Path
from collections import Counter
import json

root = Path('/root/isaacsim')
log = Path('/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0/kit_20260923_095639.log').read_text(errors='replace').splitlines()
phases = {}
release_minutes = Counter()
for line in log:
    if '[Warning]' not in line:
        continue
    t = line[:19]
    phase = ('before_script' if t < '2026-09-23T02:22:47' else
             'setup_and_preview' if t < '2026-09-23T02:24:50' else
             'recording' if t < '2026-09-23T02:30:27' else 'after_recording')
    phases.setdefault(phase, Counter())[line.split('[Warning]', 1)[1].strip()] += 1
    if 'was already released' in line:
        release_minutes[line[:16]] += 1
sources = []
for base in (root/'extscache', root/'exts', root/'kit/exts'):
    if not base.exists():
        continue
    for ext in base.glob('omni.replicator.core*'):
        for path in ext.rglob('writers.py'):
            lines = path.read_text(errors='replace').splitlines()
            for i, line in enumerate(lines):
                if 'Writer version not specified' in line:
                    sources.append({'path': str(path), 'line': i+1, 'excerpt': '\n'.join(lines[max(0,i-12):i+9])})
pil = []
for base in (root/'extscache', root/'exts', root/'kit/python/lib'):
    if not base.exists():
        continue
    candidates = list(base.glob('omni.kit.pip_archive*')) + list(base.glob('python*/site-packages'))
    for candidate in candidates:
        for path in candidate.rglob('PIL/PngImagePlugin.py'):
            lines = path.read_text(errors='replace').splitlines()
            markers = [i for i,s in enumerate(lines) if 'class _idat' in s or 'ImageFile._save(im' in s or 'ImageFile._save(' in s]
            version = path.parent/'_version.py'
            pil.append({'path': str(path), 'version': version.read_text().strip()[:1000] if version.exists() else None,
                        'excerpts': [{'line': i+1, 'text': '\n'.join(lines[max(0,i-2):i+12])} for i in markers]})
            imagefile = path.parent/'ImageFile.py'
            ilines = imagefile.read_text(errors='replace').splitlines()
            markers = [i for i,s in enumerate(ilines) if 'fp.fileno()' in s or 'encoder.encode(bufsize)' in s]
            pil[-1]['imagefile'] = [{'line': i+1, 'text': '\n'.join(ilines[max(0,i-8):i+10])} for i in markers]
print(json.dumps({'warnings_by_phase': {k: dict(v) for k,v in phases.items()}, 'released_by_minute_utc': dict(release_minutes),
                  'writer_sources': sources, 'pillow_sources': pil}, ensure_ascii=False))
