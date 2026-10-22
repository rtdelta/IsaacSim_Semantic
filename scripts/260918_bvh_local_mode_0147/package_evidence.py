"""Create local-review evidence without duplicating all raw NPZ or runtime caches."""
from pathlib import Path
import tarfile,json,hashlib,time
r=Path(__file__).resolve().parent
files=[p for p in r.iterdir() if p.is_file() and p.suffix in [".py",".json",".jsonl",".txt",".md",".png",".log"]]
raw=[]
for case in sorted((r/"cases").iterdir()):
    if not case.is_dir():continue
    files.extend(p for p in case.iterdir() if p.is_file() and p.suffix!=".npz")
    npzs=sorted(case.glob("*.npz"))
    if npzs:files.append(npzs[-1])
    raw.extend(npzs)
manifest=[]
for p in files:
    manifest.append({"path":str(p.relative_to(r)),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
with (r/"evidence_manifest.json").open("x") as f:json.dump({"included":manifest,"full_raw_npz_files":len(raw),"full_raw_npz_bytes":sum(p.stat().st_size for p in raw),"note":"All raw NPZ remain at the experiment remote root; package includes each case's last NPZ."},f,indent=2)
files.append(r/"evidence_manifest.json")
with tarfile.open(r/"evidence_metadata.tar.gz","x:gz",compresslevel=5) as tar:
    for p in sorted(files):tar.add(p,arcname=str(p.relative_to(r)),recursive=False)
print(json.dumps({"archive":str(r/"evidence_metadata.tar.gz"),"bytes":(r/"evidence_metadata.tar.gz").stat().st_size,"included_files":len(files),"raw_npz_count":len(raw)}))

