"""Install this project's maintained skill and helper sources, with backups.

No packages, services, SSH configuration or remote files are changed.
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = Path.home() / ".codex/skills/cloud-instance-ops"


def main():
    if not (ROOT / "config.json").is_file():
        raise FileNotFoundError("Create and fill local config.json from config.example.json before installing; no files were changed.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = ROOT / "backups" / ("install_" + stamp)
    mapping = [(p, DEST / p.relative_to(ROOT / "skill/cloud-instance-ops"))
               for p in (ROOT / "skill/cloud-instance-ops").rglob("*") if p.is_file()]
    mapping += [(ROOT / name, DEST / "scripts" / name) for name in ("ops.py", "config.json", "config.example.json")]
    mapping += [(p, DEST / "scripts/cloud_ops" / p.name) for p in (ROOT / "cloud_ops").glob("*.py")]
    records = []
    for src, dst in mapping:
        content = src.read_bytes()
        changed = not dst.exists() or dst.read_bytes() != content
        original = None
        if changed:
            if dst.exists():
                original = backup / dst.relative_to(DEST)
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, original)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(content)
        records.append({"source": str(src), "destination": str(dst), "changed": changed,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "backup": str(original) if original else None})
    report = ROOT / "reports" / ("skill_install_" + stamp + ".json")
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(records), "changed": sum(r["changed"] for r in records),
                      "manifest": str(report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
