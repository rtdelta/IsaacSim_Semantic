from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from postprocess_chain_v02.config import load_config
from postprocess_chain_v02.main_pipeline import run_pipeline


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the unified excavator tooth post-processing pipeline."
    )
    parser.add_argument("--config", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_pipeline(load_config(args.config))
    print(
        f"completed mode={summary['mode']} frames={summary['frames']} "
        f"elapsed={summary['elapsed_seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
