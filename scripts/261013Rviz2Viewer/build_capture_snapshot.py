"""Copy the proven single06 runtime. Never edit the source project."""
import hashlib, json, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent/'260920SensorVisualizer/lidar_equivalence_006/legacy'

def main():
    destination = ROOT/'capture_runtime'
    destination.mkdir(exist_ok=False)
    manifest = {}
    for p in SOURCE.rglob('*'):
        rel = p.relative_to(SOURCE)
        if not p.is_file() or '__pycache__' in rel.parts or p.suffix not in ('.py','.json'):
            continue
        target = destination/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p,target)
        manifest[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT/'backups').mkdir(exist_ok=True)
    with zipfile.ZipFile(ROOT/'backups/single06_source_snapshot.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for rel in manifest: archive.write(SOURCE/rel, rel)
    (ROOT/'source_provenance.json').write_text(json.dumps({'source':str(SOURCE),'files':manifest,'scope':'unchanged baseline files; task-owned kit entry added separately'},indent=2),encoding='utf-8')
    print(json.dumps({'files':len(manifest),'destination':str(destination)}))

if __name__=='__main__':main()
