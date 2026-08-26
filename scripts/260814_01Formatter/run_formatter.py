from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from formatter.config import load_config
from formatter.pipeline import run_formatter


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Format a post-processed YOLO dataset using a strict JSON configuration."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_formatter(load_config(args.config))
    except (OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    for key, value in summary.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
