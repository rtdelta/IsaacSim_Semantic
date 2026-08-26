from __future__ import annotations

import argparse
import sys
from pathlib import Path

from semantic_pixel_ratio.config import load_config
from semantic_pixel_ratio.pipeline import run


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare paired whole-scene and excavator-only semantic pixel counts."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "configs" / "combine_scene_02.json",
        help="Path to the JSON run configuration.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        config = load_config(args.config)
        summary = run(config)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"semantic pixel-ratio analysis failed: {exc}", file=sys.stderr)
        return 1

    print("semantic pixel-ratio analysis completed")
    print(f"frames: {summary['frames']}")
    print(f"backend: {summary['backend']}")
    print(f"elapsed_seconds: {summary['elapsed_seconds']}")
    print(f"frames_per_second: {summary['frames_per_second']}")
    print(f"output: {config.output.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

