"""Same-host job lifecycle CLI."""

import argparse
from pathlib import Path

from semantic_world_v04.core.models import JobSpec
from semantic_world_v04.core.serde import pretty_json
from semantic_world_v04.output.io import read_json
from semantic_world_v04.output.segment_store import SegmentStatusStore
from semantic_world_v04.supervisor import SameHostSupervisor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Semantic World v04 supervisor")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("job_spec")
    run = sub.add_parser("run")
    run.add_argument("job_spec")
    for name in (
        "start",
        "status",
        "stop",
        "resume",
        "logs",
        "segments",
        "failure-report",
    ):
        command = sub.add_parser(name)
        command.add_argument("job_id")
        command.add_argument("--output-root", required=True)
        if name == "logs":
            command.add_argument("--lines", type=int, default=100)
    return parser


def _load(path: str) -> JobSpec:
    return JobSpec.from_dict(read_json(Path(path)))


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    supervisor = SameHostSupervisor()
    if args.command in {"submit", "run"}:
        job = _load(args.job_spec)
        status = supervisor.submit(job)
        if args.command == "run":
            status = supervisor.start(
                job.job_id, SameHostSupervisor.job_dir(job).parent
            )
        print(pretty_json(status.to_dict()), end="")
        return 0
    output_root = Path(args.output_root)
    if args.command == "start":
        status = supervisor.start(args.job_id, output_root)
    elif args.command == "status":
        status = supervisor.status(args.job_id, output_root)
    elif args.command == "stop":
        status = supervisor.stop(args.job_id, output_root)
    elif args.command == "resume":
        status = supervisor.resume(args.job_id, output_root)
    elif args.command == "logs":
        print("".join(supervisor.tail_logs(args.job_id, output_root, args.lines)), end="")
        return 0
    elif args.command == "segments":
        segments = []
        for path in sorted((output_root / args.job_id / "segments").glob("*/status.json")):
            try:
                segments.append(SegmentStatusStore(path).read().to_dict())
            except Exception as exc:
                segments.append(
                    {
                        "segment_id": path.parent.name,
                        "state": "invalid",
                        "message": str(exc),
                    }
                )
        print(pretty_json(segments), end="")
        return 0
    else:
        path = output_root / args.job_id / "failure_report.json"
        if not path.is_file():
            print(pretty_json({"available": False, "path": str(path)}), end="")
            return 1
        report = read_json(path)
        report["path"] = str(path)
        print(pretty_json(report), end="")
        return 0
    print(pretty_json(status.to_dict()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
