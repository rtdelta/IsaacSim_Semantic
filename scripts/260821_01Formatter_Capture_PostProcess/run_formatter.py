from __future__ import annotations

import argparse
import json

from capture_postprocess_formatter import convert_dataset, load_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Semantic World Module v03 frame directories into the flat "
            "input contract required by Post Process Chain v02."
        )
    )
    parser.add_argument("--config", required=True, help="Path to formatter JSON config")
    args = parser.parse_args()
    summary = convert_dataset(load_config(args.config))
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

