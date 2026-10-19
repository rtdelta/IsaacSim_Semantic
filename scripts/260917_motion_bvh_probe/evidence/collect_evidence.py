"""Archive diagnostic outputs only; never copy referenced source assets."""
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent
files = [p for p in root.iterdir() if p.is_file() and p.suffix in {'.py', '.json', '.md', '.log', '.usda'}]
files += [p for p in (root / 'cases').rglob('*') if p.is_file() and
          p.suffix in {'.py', '.json', '.log', '.usda', '.npz', '.png'}]
with tarfile.open(root / 'evidence.tar.gz', 'w:gz') as archive:
    for path in sorted(files):
        archive.add(path, arcname=str(path.relative_to(root)))
print(root / 'evidence.tar.gz', (root / 'evidence.tar.gz').stat().st_size, 'bytes', len(files), 'files')
