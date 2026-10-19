from pathlib import Path
import tarfile,json,hashlib
r=Path(__file__).resolve().parent
dest=r/"evidence"
dest.mkdir(exist_ok=False)
with tarfile.open(r/"evidence_metadata.tar.gz","r:gz") as tf:
    for member in tf.getmembers():
        target=(dest/member.name).resolve()
        if not target.is_relative_to(dest.resolve()):raise RuntimeError("Escaping archive member")
        if not member.isfile():raise RuntimeError("Unexpected non-file archive entry")
    tf.extractall(dest)
m=json.loads((dest/"evidence_manifest.json").read_text())
bad=[]
for entry in m["included"]:
    p=dest/entry["path"]
    if hashlib.sha256(p.read_bytes()).hexdigest()!=entry["sha256"]:bad.append(entry["path"])
assert not bad,bad
(r/"local_archive_verification.json").write_text(json.dumps({"checked":len(m["included"]),"changed":bad,"archive_bytes":(r/"evidence_metadata.tar.gz").stat().st_size},indent=2))
print(json.dumps({"verified_files":len(m["included"]),"bad":bad}))

