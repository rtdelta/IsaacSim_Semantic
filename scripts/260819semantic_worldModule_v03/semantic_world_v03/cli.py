"""Command-line entry point for validation, planning, and supervised capture."""

from __future__ import annotations

import argparse
import json

from .config import load_run_config
from .supervisor import Supervisor, plan_segments


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="semantic-world-v03")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "plan", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)
        if name == "run":
            command.add_argument(
                "--headless", action=argparse.BooleanOptionalAction, default=True
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = load_run_config(args.config)
    if args.command == "validate":
        print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "plan":
        print(
            json.dumps(
                [segment.__dict__ for segment in plan_segments(config)],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        Supervisor(config, headless=args.headless).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

