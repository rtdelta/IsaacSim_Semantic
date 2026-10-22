"""Project delivery boundary: source plus curated docs, excluding runtime data."""
from pathlib import Path


SOURCE_SUFFIXES = {'.py', '.json', '.md', '.js', '.html', '.css'}
REPORT_SUFFIXES = SOURCE_SUFFIXES | {'.txt', '.png', '.jpg', '.jpeg', '.svg'}
CACHES = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.git'}
LOCAL_ROOTS = {'reports', '_local', 'tmp', 'output', 'remote_output'}


def delivery_files(root, include_manifest=False):
    root = Path(root).resolve()
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in LOCAL_ROOTS or any(part in CACHES for part in relative.parts):
            continue
        if len(relative.parts) > 1 and relative.parts[0].startswith(('output', 'remote_output')):
            continue
        if relative == Path('project_manifest.json') and not include_manifest:
            continue
        curated = relative.parts[:2] == ('docs', 'reports')
        if path.suffix.lower() in (REPORT_SUFFIXES if curated else SOURCE_SUFFIXES):
            yield path
