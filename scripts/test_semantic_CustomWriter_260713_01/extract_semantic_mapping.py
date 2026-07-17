"""Generate a stable semantic mapping JSON from labels authored in a USD stage."""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path


parser = argparse.ArgumentParser(description="Extract semantic mapping from an Isaac Sim USD stage")
parser.add_argument("--usd", required=True, help="Input USD/USDA/USDC stage")
parser.add_argument("--output", required=True, help="Output mapping JSON")
parser.add_argument("--semantic-type", default="class", help="Semantic taxonomy to extract")
args, _ = parser.parse_known_args()

from isaacsim import SimulationApp


simulation_app = SimulationApp(launch_config={"headless": True, "sync_loads": True})
exit_code = 0

try:
    from pxr import Usd

    from semantic_mapping import build_schema_from_stage

    if not os.path.isfile(args.usd):
        raise FileNotFoundError(f"USD file not found: {args.usd}")
    stage = Usd.Stage.Open(args.usd)
    if stage is None:
        raise RuntimeError(f"Failed to open USD stage: {args.usd}")

    schema = build_schema_from_stage(stage, args.usd, args.semantic_type)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(schema, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    temporary_path.replace(output_path)

    print(
        f"[semantic-mapping] Wrote {schema['class_count']} classes from "
        f"{schema['semantic_prim_count']} semantic prims to {output_path}"
    )
    for entry in schema["classes"]:
        print(
            f"[semantic-mapping] id={entry['id']:>3} color={entry['color']} "
            f"prims={entry['prim_count']:>3} label={entry['label']}"
        )
except Exception as exc:
    exit_code = 1
    print(f"[semantic-mapping] ERROR: {exc}", file=sys.stderr)
    traceback.print_exc()
finally:
    simulation_app.close()

sys.exit(exit_code)
