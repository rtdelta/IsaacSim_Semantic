from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from threshold_filter.config import load_config
from threshold_filter.pipeline import run_pipeline


def parse_args(argv: Sequence[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter tooth and tooth-group YOLO boxes by visibility ratio."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the JSON run configuration.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    summary = run_pipeline(config)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"completed output={config.output.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
