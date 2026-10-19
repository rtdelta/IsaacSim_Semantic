from pathlib import Path
import hashlib,json,tarfile
root=Path(__file__).resolve().parent
manifest=json.loads((root/"evidence_manifest.json").read_text())
archive=root/manifest["archive"]
assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest["sha256"]
dest=root/"evidence"
assert not dest.exists()
with tarfile.open(archive) as t:
    members=t.getmembers()
    for m in members:
        resolved=(dest/m.name).resolve()
        assert resolved.is_relative_to(dest.resolve()),m.name
        assert not m.issym() and not m.islnk(),m.name
    dest.mkdir()
    t.extractall(dest)
rows=json.loads((dest/"summary_final.json").read_text())
for g in ["mesh","gaussian"]:
 for output in ["camera","lidar"]:
  for mode in ["off","on"]:
   r=next(r for r in rows if r["case"]==f"v3_{output}_{g}_{mode}")
   assert r["status"]=="collected" and r["isolation"]["verified"]
   assert r["engines"][0]["flags"]==int(mode=="on")
   assert bool(r["gaussian_errors"])==(g=="gaussian" and mode=="on")
checks=[]
for p in dest.glob("verification_*.json"):
    v=json.loads(p.read_text())
    assert v["checked"]==1088 and not v["changed"] and not v["missing"]
    checks.append(p.name)
env=json.loads((dest/"final_environment.json").read_text())
assert not env["active_isaac_processes"]
print(json.dumps({"archive_hash_verified":True,"members":len(members),"case_count":len(rows),
                  "formal_eight_pair_checks":"passed","integrity_records":checks,"processes_remaining":0},indent=2))

