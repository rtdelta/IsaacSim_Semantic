from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path

from postprocess_chain.pipeline.orchestrator import Orchestrator
from postprocess_chain.pipeline.orchestrator_config import (
    load_orchestrator_config,
)


def parse_args() -> argparse.Namespace:
    default_config = Path(__file__).resolve().parent / "configs" / "orchestrator.json"
    parser = argparse.ArgumentParser(
        description="Run the config-driven post-process module chain."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help="orchestrator config path; defaults to configs/orchestrator.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_orchestrator_config(args.config)
    return Orchestrator(config).run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
