import argparse
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path

from .audit import Audit, verify_file
from .download import download
from .security import PolicyError, Redactor, WindowsCredentials, load_policy, private_directory
from .ssh import OutcomeUnknown, run


def parser():
    p = argparse.ArgumentParser(description="Audited cloud operations; not a security sandbox")
    p.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.json")
    p.add_argument("--state", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/state"))) / "CloudInstanceOps")
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("probe", "exec", "download", "access-note", "credential-set"):
        s = commands.add_parser(name)
        s.add_argument("--task", required=True, help="Task/case identifier, no secrets")
        s.add_argument("--purpose", required=True, help="Reason for this operation")
        if name in ("probe", "exec", "credential-set"):
            s.add_argument("--target", required=True)
        if name == "exec":
            s.add_argument("--script", type=Path, required=True, help="Reviewed Python script, sent over SSH stdin")
            s.add_argument("--intent", choices=["read", "write", "diagnostic"], required=True,
                           help="Recorded declaration, NOT a sandbox")
            s.add_argument("--timeout", type=int, default=30)
        if name == "download":
            s.add_argument("--url", required=True)
            s.add_argument("--filename", required=True)
            g = s.add_mutually_exclusive_group(required=True)
            g.add_argument("--sha256")
            g.add_argument("--observe-hash", action="store_true")
        if name == "access-note":
            s.add_argument("--surface", required=True, choices=["browser_tool", "local_windows", "remote_linux"])
            s.add_argument("--url", required=True)
            s.add_argument("--activity", required=True, choices=["documentation", "search", "download", "upload", "other"])
            s.add_argument("--reference", required=True, help="Tool-call ID or other evidence pointer, no sensitive contents")
    commands.add_parser("verify")
    commands.add_parser("status")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    redactor = Redactor()
    audit = None
    result = None
    try:
        policy = load_policy(args.config)
        state = private_directory(args.state)
        if args.command == "verify":
            results = [verify_file(f) for f in sorted((state / "audit").glob("*/*.jsonl"))]
            print(json.dumps({"operations": results,
                              "limitation": "Local hash chains cannot detect whole-file deletion or deliberate complete rewriting"}, ensure_ascii=False, indent=2))
            return 1 if any(r["integrity"] != "valid" or r["completion"] != "recorded" for r in results) else 0
        if args.command == "status":
            print(json.dumps({"state": str(state), "targets": list(policy["targets"]),
                              "scope": "Only wrapper activity; no background monitoring or firewall controls"}, ensure_ascii=False, indent=2))
            return 0
        target = None
        if hasattr(args, "target"):
            target = policy["targets"].get(args.target)
            if target is None:
                raise PolicyError("Unknown target alias")
        # Register the runtime credential before any dynamic value is logged.
        if args.command in ("probe", "exec") and target.get("auth") == "windows-credential":
            secret = WindowsCredentials().read(target["credential_ref"])
            redactor.add_secret(secret)
            class LoadedCredential:
                def read(self, name):
                    if name != target["credential_ref"]:
                        raise PolicyError("Credential reference mismatch")
                    return secret
            provider = LoadedCredential()
        else:
            provider = None
        audit = Audit(state, redactor, args.task, args.purpose, args.command,
                      hashlib.sha256(args.config.read_bytes()).hexdigest())
        if args.command == "credential-set":
            if target.get("auth") != "windows-credential":
                raise PolicyError("Target is not configured for Windows credentials")
            if not sys.stdin.isatty():
                raise PolicyError("Credential enrollment requires an interactive terminal; no stdin/argument secrets")
            secret = getpass.getpass("SSH password (hidden): ")
            redactor.add_secret(secret)
            WindowsCredentials().write(target["credential_ref"], target["username"], secret)
            result = {"stored": True, "target": args.target}
        elif args.command in ("probe", "exec"):
            timeout = getattr(args, "timeout", 30)
            if not 1 <= timeout <= 3600:
                raise PolicyError("Timeout must be between 1 and 3600 seconds")
            script = args.script.read_text(encoding="utf-8-sig") if args.command == "exec" else None
            result = run(target, args.target, audit, redactor, script, timeout,
                         getattr(args, "intent", "read"), provider)
        elif args.command == "download":
            result = download(args.url, args.filename, args.sha256, args.observe_hash,
                              state, policy["downloads"], audit)
        elif args.command == "access-note":
            audit.event("external_access.reported", surface=args.surface, url=args.url,
                        activity=args.activity, evidence_reference=args.reference,
                        provenance="operator_or_ai_reported_not_independent_network_capture")
            result = {"recorded": True, "network_request_performed": False}
        else:
            raise PolicyError("Unsupported action")
        status = "succeeded" if result.get("exit_code", 0) == 0 else "failed"
        audit.finish(status, exit_code=result.get("exit_code", 0))
        safe = redactor.clean(result)
        print(json.dumps({"operation_id": audit.id, "audit_log": str(audit.path),
                          "status": status, "result": safe}, ensure_ascii=False, indent=2))
        return 0 if status == "succeeded" else 1
    except KeyboardInterrupt:
        if audit and not audit.closed:
            try:
                audit.finish("unknown", reason="operator interruption; inspect state before retry")
            except Exception:
                pass  # Report the interruption even when the audit disk failed.
        print(json.dumps({"status": "unknown", "error": "Interrupted; operation may be incomplete"}))
        return 130
    except Exception as exc:
        unknown = isinstance(exc, OutcomeUnknown) or result is not None
        message = redactor.text(str(exc))
        audit_write_failed = False
        try:
            if audit is None and 'state' in locals() and hasattr(args, "task"):
                # Omit user metadata before runtime secrets are registered.
                audit = Audit(state, redactor, "preflight", "operation rejected before execution",
                              args.command, hashlib.sha256(args.config.read_bytes()).hexdigest())
            if audit and not audit.closed:
                audit.finish("unknown" if unknown else "failed", error_type=type(exc).__name__, error=message)
        except Exception:
            audit_write_failed = True
        print(json.dumps({"status": "unknown" if unknown else "failed", "error_type": type(exc).__name__,
                          "error": message, "audit_write_failed": audit_write_failed,
                          "audit_log": str(audit.path) if audit else None}, ensure_ascii=False), file=sys.stderr)
        return 3 if unknown else 2
