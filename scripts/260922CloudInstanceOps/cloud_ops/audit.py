import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .security import PolicyError


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


class Audit:
    """One append-only-by-convention file per operation, flushed before actions.

    Hash chaining detects accidental changes; it is not a signature and cannot
    resist an attacker able to rewrite the entire file or delete it.
    """
    def __init__(self, state, redactor, task, purpose, action, policy_hash):
        self.redactor = redactor
        self.id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
        folder = Path(state) / "audit" / self.id[:8]
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (self.id + ".jsonl")
        self.file = self.path.open("x", encoding="utf-8", newline="\n")
        self.seq, self.previous = 0, "0" * 64
        self.closed = False
        self.event("operation.started", task=task, purpose=purpose, action=action,
                   initiator="ai_or_operator_via_wrapper", policy_sha256=policy_hash,
                   coverage="wrapper operations only")

    def event(self, kind, **data):
        if self.closed:
            raise PolicyError("Attempted write to closed audit operation")
        record = {"schema": 1, "operation_id": self.id, "sequence": self.seq,
                  "time_utc": utc_now(), "event": kind, "previous_sha256": self.previous,
                  "data": self.redactor.clean(data)}
        digest = hashlib.sha256(canonical(record)).hexdigest()
        record["sha256"] = digest
        self.file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())
        self.previous, self.seq = digest, self.seq + 1

    def finish(self, status, **data):
        try:
            self.event("operation.finished", status=status, **data)
        finally:
            self.closed = True
            self.file.close()

    def snapshot(self, label, content):
        safe = self.redactor.text(content)
        path = self.path.with_suffix("." + label + ".txt")
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(safe)
        self.event("artifact.saved", artifact=path.name,
                   sha256=hashlib.sha256(safe.encode("utf-8")).hexdigest())
        return path


def verify_file(path):
    previous, expected, op_id, last = "0" * 64, 0, None, None
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            digest = record.pop("sha256")
            if (record["previous_sha256"] != previous or
                    record["sequence"] != expected or
                    hashlib.sha256(canonical(record)).hexdigest() != digest):
                raise ValueError("Hash/sequence mismatch")
            if op_id is not None and record["operation_id"] != op_id:
                raise ValueError("Operation mismatch")
            if expected == 0 and record["event"] != "operation.started":
                raise ValueError("Missing start record")
            if last == "operation.finished":
                raise ValueError("Records after completion")
            if record["event"] == "artifact.saved":
                name = record["data"]["artifact"]
                if Path(name).name != name:
                    raise ValueError("Invalid artifact path")
                artifact = Path(path).parent / name
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != record["data"]["sha256"]:
                    raise ValueError("Artifact hash mismatch")
            op_id, previous, last = record["operation_id"], digest, record["event"]
            expected += 1
        return {"file": str(path), "integrity": "valid" if expected else "invalid",
                "completion": "recorded" if last == "operation.finished" else "unknown",
                "events": expected, "last_sha256": previous}
    except (OSError, ValueError, KeyError, TypeError):
        return {"file": str(path), "integrity": "invalid", "completion": "unknown"}

