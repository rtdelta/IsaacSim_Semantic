from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping


def make_source(root: Path, frame_tokens: Iterable[str]) -> Path:
    source = root / "PostProcess"
    rgb = source / "dataset" / "rgb"
    tooth = source / "dataset" / "tooth_boxes"
    collision = source / "dataset" / "tooth_collision_model"
    reports = source / "reports"
    for directory in (rgb, tooth, collision, reports):
        directory.mkdir(parents=True, exist_ok=True)

    (tooth / "classes.txt").write_text(
        "tooth_01\ntooth_02\ntooth_03\ntooth_04\ntooth_05\n",
        encoding="utf-8",
    )
    (collision / "classes.txt").write_text(
        "tooth_collision_model\n", encoding="utf-8"
    )
    for index, token in enumerate(frame_tokens):
        (rgb / f"rgb_{token}.png").write_bytes(f"image-{token}".encode("ascii"))
        tooth_content = (
            "4 0.10000000 0.20000000 0.30000000 0.40000000\n"
            if index % 2 == 0
            else ""
        )
        collision_content = (
            "7 0.50000000 0.60000000 0.20000000 0.10000000\n"
            if index % 3 == 0
            else ""
        )
        (tooth / f"rgb_{token}.txt").write_text(tooth_content, encoding="utf-8")
        (collision / f"rgb_{token}.txt").write_text(
            collision_content, encoding="utf-8"
        )
    (reports / "frame_summary.csv").write_text(
        "frame_id,class_id\n0000,4\n", encoding="utf-8"
    )
    (source / "manifest.json").write_text(
        '{"source": "postprocess"}\n', encoding="utf-8"
    )
    (source / "resolved_config.json").write_text(
        '{"schema_version": 2}\n', encoding="utf-8"
    )
    return source


def write_config(
    path: Path,
    *,
    input_root: Path,
    output_root: Path,
    prefix: str = "Sim_Fangshan_tooth_260813",
    overrides: Mapping[str, object] | None = None,
) -> Path:
    value = {
        "schema_version": 1,
        "input_root": str(input_root),
        "output_root": str(output_root),
        "filename_prefix": prefix,
        "classes": {
            "tooth_class_name": "tooth",
            "collision_class_name": "tooth_collision_model",
        },
        "output": {
            "preserve_reports": True,
            "unchanged_file_mode": "copy",
        },
        "performance": {"workers": 4, "max_in_flight": 8},
    }
    if overrides:
        value.update(overrides)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path
