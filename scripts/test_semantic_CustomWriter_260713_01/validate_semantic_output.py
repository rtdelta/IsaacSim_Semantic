"""Validate semantic NPY files against the custom-color PNG files and schema."""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from semantic_mapping import SemanticMapping


parser = argparse.ArgumentParser(description="Validate custom semantic capture output")
parser.add_argument("--output", required=True, help="Capture output directory")
parser.add_argument("--mapping", required=True, help="Semantic mapping JSON")
args = parser.parse_args()

output_dir = Path(args.output).resolve()
mapping = SemanticMapping(args.mapping)
npy_files = sorted(output_dir.rglob("semantic_id_*.npy"))
if not npy_files:
    print(f"[semantic-validate] ERROR: no semantic_id NPY files under {output_dir}", file=sys.stderr)
    sys.exit(1)

valid_ids = set(mapping.id_to_label)
for npy_path in npy_files:
    relative = npy_path.relative_to(output_dir)
    parent_parts = list(relative.parent.parts)
    if not parent_parts or parent_parts[-1] != "semantic_id":
        raise RuntimeError(f"Unexpected semantic NPY path: {relative}")
    parent_parts[-1] = "semantic_color"
    png_name = npy_path.name.replace("semantic_id_", "semantic_color_", 1).replace(".npy", ".png")
    png_path = output_dir.joinpath(*parent_parts, png_name)
    if not png_path.is_file():
        raise FileNotFoundError(f"Missing color PNG for {npy_path}: {png_path}")

    dataset_ids = np.load(npy_path, allow_pickle=False)
    if dataset_ids.ndim != 2 or dataset_ids.dtype != np.uint16:
        raise ValueError(f"Expected a 2D uint16 NPY, got {dataset_ids.shape} {dataset_ids.dtype}: {npy_path}")
    present_ids = {int(value) for value in np.unique(dataset_ids)}
    if not present_ids.issubset(valid_ids):
        raise ValueError(f"NPY contains IDs not defined by mapping: {sorted(present_ids - valid_ids)}")

    expected_rgb = mapping.colorize(dataset_ids)
    actual_rgb = np.asarray(Image.open(png_path).convert("RGB"))
    if not np.array_equal(expected_rgb, actual_rgb):
        mismatch_count = int(np.any(expected_rgb != actual_rgb, axis=2).sum())
        raise ValueError(f"Custom PNG differs from mapping(NPY) at {mismatch_count} pixels: {png_path}")
    print(
        f"[semantic-validate] PASS {npy_path.name}: shape={dataset_ids.shape}, "
        f"ids={sorted(present_ids)}"
    )

print(f"[semantic-validate] PASS: validated {len(npy_files)} frame(s) under {output_dir}")
