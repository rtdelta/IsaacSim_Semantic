#!/usr/bin/env python3
"""Inspect Gaussian Splat PLY files without requiring Isaac Sim.

The scanner reads each vertex element with NumPy, validates the standard 3DGS
properties, and writes a deterministic JSON manifest. Input files are never
modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


PLY_NUMPY_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}

REQUIRED_3DGS_PROPERTIES = {
    "position": ("x", "y", "z"),
    "scale": ("scale_0", "scale_1", "scale_2"),
    "rotation": ("rot_0", "rot_1", "rot_2", "rot_3"),
    "opacity": ("opacity",),
    "sh_dc": ("f_dc_0", "f_dc_1", "f_dc_2"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_header(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        if stream.readline().decode("ascii").strip() != "ply":
            raise ValueError("missing PLY magic")

        file_format = None
        vertex_count = None
        current_element = None
        vertex_properties: list[dict[str, str]] = []
        elements: list[dict[str, Any]] = []

        while True:
            raw = stream.readline()
            if not raw:
                raise ValueError("unexpected EOF before end_header")
            line = raw.decode("ascii").strip()
            if line == "end_header":
                break
            if not line or line.startswith("comment") or line.startswith("obj_info"):
                continue
            fields = line.split()
            if fields[0] == "format":
                file_format = fields[1]
            elif fields[0] == "element":
                current_element = fields[1]
                count = int(fields[2])
                elements.append({"name": current_element, "count": count})
                if current_element == "vertex":
                    vertex_count = count
            elif fields[0] == "property" and current_element == "vertex":
                if fields[1] == "list":
                    raise ValueError("list property in vertex element is unsupported")
                if fields[1] not in PLY_NUMPY_TYPES:
                    raise ValueError(f"unsupported property type: {fields[1]}")
                vertex_properties.append({"type": fields[1], "name": fields[2]})

        if file_format is None or vertex_count is None:
            raise ValueError("format or vertex element is missing")
        if file_format not in {"ascii", "binary_little_endian", "binary_big_endian"}:
            raise ValueError(f"unsupported PLY format: {file_format}")

        return {
            "format": file_format,
            "vertex_count": vertex_count,
            "vertex_properties": vertex_properties,
            "elements": elements,
            "header_bytes": stream.tell(),
        }


def _structured_dtype(header: dict[str, Any]) -> np.dtype:
    byte_order = "<" if header["format"] == "binary_little_endian" else ">"
    return np.dtype(
        [
            (item["name"], byte_order + PLY_NUMPY_TYPES[item["type"]])
            for item in header["vertex_properties"]
        ]
    )


def _float(value: Any) -> float:
    result = float(value)
    return result if math.isfinite(result) else result


def _vector(values: np.ndarray) -> list[float]:
    return [_float(item) for item in values.tolist()]


def _read_vertices(path: Path, header: dict[str, Any]) -> np.ndarray:
    names = [item["name"] for item in header["vertex_properties"]]
    if header["format"] == "ascii":
        raw = np.loadtxt(path, skiprows=0, comments=None)
        raise ValueError(
            "ASCII vertex loading is intentionally not implemented in v01; "
            f"properties={names}, loaded_shape={raw.shape}"
        )
    dtype = _structured_dtype(header)
    return np.memmap(
        path,
        mode="r",
        dtype=dtype,
        offset=header["header_bytes"],
        shape=(header["vertex_count"],),
    )


def _range(data: np.ndarray, names: tuple[str, ...]) -> dict[str, Any] | None:
    if not all(name in data.dtype.names for name in names):
        return None
    array = np.column_stack([np.asarray(data[name], dtype=np.float64) for name in names])
    finite = np.isfinite(array)
    return {
        "minimum": _vector(np.nanmin(array, axis=0)),
        "maximum": _vector(np.nanmax(array, axis=0)),
        "mean": _vector(np.nanmean(array, axis=0)),
        "all_finite": bool(finite.all()),
        "non_finite_value_count": int(array.size - np.count_nonzero(finite)),
    }


def inspect_ply(path: Path, root: Path) -> dict[str, Any]:
    header = _parse_header(path)
    data = _read_vertices(path, header)
    names = list(data.dtype.names or ())

    required = {
        group: all(name in names for name in property_names)
        for group, property_names in REQUIRED_3DGS_PROPERTIES.items()
    }
    rest_names = sorted(
        (name for name in names if name.startswith("f_rest_")),
        key=lambda name: int(name.rsplit("_", 1)[1]),
    )
    rest_count = len(rest_names)
    sh_degree = {0: 0, 9: 1, 24: 2, 45: 3}.get(rest_count)

    positions = _range(data, ("x", "y", "z"))
    scales = _range(data, ("scale_0", "scale_1", "scale_2"))
    opacity = _range(data, ("opacity",))

    quaternion_norm = None
    if required["rotation"]:
        rotations = np.column_stack(
            [np.asarray(data[f"rot_{index}"], dtype=np.float64) for index in range(4)]
        )
        norms = np.linalg.norm(rotations, axis=1)
        quaternion_norm = {
            "minimum": _float(np.nanmin(norms)),
            "maximum": _float(np.nanmax(norms)),
            "mean": _float(np.nanmean(norms)),
            "all_finite": bool(np.isfinite(norms).all()),
        }

    dtype = _structured_dtype(header)
    expected_vertex_data_bytes = int(header["vertex_count"] * dtype.itemsize)
    minimum_expected_file_bytes = int(header["header_bytes"] + expected_vertex_data_bytes)

    return {
        "id": path.stem,
        "relative_path": path.relative_to(root).as_posix(),
        "absolute_path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "format": header["format"],
        "header_bytes": header["header_bytes"],
        "vertex_count": header["vertex_count"],
        "vertex_record_bytes": dtype.itemsize,
        "expected_vertex_data_bytes": expected_vertex_data_bytes,
        "minimum_expected_file_bytes": minimum_expected_file_bytes,
        "file_has_expected_vertex_bytes": path.stat().st_size >= minimum_expected_file_bytes,
        "elements": header["elements"],
        "property_count": len(names),
        "properties": names,
        "required_3dgs_groups": required,
        "is_standard_3dgs": bool(all(required.values())),
        "sh_rest_coefficient_count": rest_count,
        "sh_degree": sh_degree,
        "position": positions,
        "log_scale": scales,
        "opacity_logit": opacity,
        "quaternion_norm": quaternion_norm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ply-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    ply_dir = args.ply_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not ply_dir.is_dir():
        parser.error(f"PLY directory does not exist: {ply_dir}")

    files = sorted(ply_dir.glob("*.ply"), key=lambda item: item.name.lower())
    if not files:
        parser.error(f"No .ply files found: {ply_dir}")

    parts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            parts.append(inspect_ply(path, ply_dir))
        except Exception as exc:  # Keep scanning and report every malformed input.
            errors.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})

    manifest = {
        "schema_version": "1.0",
        "kind": "gaussian_ply_asset_manifest",
        "source_directory": str(ply_dir),
        "file_count": len(files),
        "inspected_count": len(parts),
        "error_count": len(errors),
        "total_size_bytes": sum(item["size_bytes"] for item in parts),
        "total_vertex_count": sum(item["vertex_count"] for item in parts),
        "parts": parts,
        "errors": errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "file_count": len(files),
        "inspected_count": len(parts),
        "error_count": len(errors),
        "total_vertex_count": manifest["total_vertex_count"],
    }, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
