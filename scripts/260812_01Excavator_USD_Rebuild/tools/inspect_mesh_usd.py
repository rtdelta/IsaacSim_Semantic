#!/usr/bin/env python3
"""Inspect USD Mesh inputs and optionally inventory connected components."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vec3(value):
    return [float(value[0]), float(value[1]), float(value[2])]


def _connected_components(point_count, face_counts, face_indices):
    import numpy as np

    parent = np.arange(point_count, dtype=np.int32)
    sizes = np.ones(point_count, dtype=np.int64)

    def find(item):
        root = item
        while parent[root] != root:
            root = int(parent[root])
        while parent[item] != item:
            next_item = int(parent[item])
            parent[item] = root
            item = next_item
        return root

    def union(a, b):
        root_a = find(int(a))
        root_b = find(int(b))
        if root_a == root_b:
            return
        if sizes[root_a] < sizes[root_b]:
            root_a, root_b = root_b, root_a
        parent[root_b] = root_a
        sizes[root_a] += sizes[root_b]

    offset = 0
    for count_value in face_counts:
        count = int(count_value)
        if count > 1:
            anchor = int(face_indices[offset])
            for index in face_indices[offset + 1 : offset + count]:
                union(anchor, int(index))
        offset += count

    roots = np.fromiter((find(i) for i in range(point_count)), dtype=np.int32, count=point_count)
    _, component_sizes = np.unique(roots, return_counts=True)
    component_sizes.sort()
    component_sizes = component_sizes[::-1]
    return {
        "component_count": int(component_sizes.size),
        "largest_component_vertex_counts": [int(value) for value in component_sizes[:20]],
        "single_vertex_component_count": int(np.count_nonzero(component_sizes == 1)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--prim-path")
    parser.add_argument("--compute-connected-components", action="store_true")
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    if not input_path.is_file():
        parser.error(f"input file does not exist: {input_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    import numpy as np
    from pxr import Usd, UsdGeom, UsdShade

    stage = Usd.Stage.Open(str(input_path), load=Usd.Stage.LoadNone)
    if stage is None:
        raise RuntimeError(f"failed to open USD stage: {input_path}")

    if args.prim_path:
        prims = [stage.GetPrimAtPath(args.prim_path)]
        if not prims[0] or not prims[0].IsA(UsdGeom.Mesh):
            raise RuntimeError(f"Mesh prim not found at {args.prim_path}")
    else:
        prims = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]

    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    mesh_reports = []
    for prim in prims:
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
        face_counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
        face_indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
        if points.size:
            numeric_bounds = {
                "min": points.min(axis=0).tolist(),
                "max": points.max(axis=0).tolist(),
                "center_aabb": ((points.min(axis=0) + points.max(axis=0)) * 0.5).tolist(),
            }
        else:
            numeric_bounds = None

        aligned_range = bbox_cache.ComputeWorldBound(prim).ComputeAlignedRange()
        material = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        entry = {
            "prim_path": str(prim.GetPath()),
            "point_count": int(points.shape[0]),
            "face_count": int(face_counts.shape[0]),
            "face_vertex_index_count": int(face_indices.shape[0]),
            "face_vertex_count_histogram": {
                str(int(value)): int(count)
                for value, count in zip(*np.unique(face_counts, return_counts=True))
            },
            "subdivision_scheme": str(mesh.GetSubdivisionSchemeAttr().Get()),
            "orientation": str(mesh.GetOrientationAttr().Get()),
            "numeric_point_bounds": numeric_bounds,
            "world_aligned_bounds": {
                "min": _vec3(aligned_range.GetMin()),
                "max": _vec3(aligned_range.GetMax()),
            },
            "bound_material_path": str(material.GetPath()) if material else None,
        }
        if args.compute_connected_components:
            entry["connected_components"] = _connected_components(
                points.shape[0], face_counts, face_indices
            )
        mesh_reports.append(entry)

    report = {
        "schema_version": "1.0",
        "kind": "usd_mesh_input_manifest",
        "source_file": str(input_path),
        "source_file_size_bytes": input_path.stat().st_size,
        "source_file_sha256": _sha256(input_path),
        "stage_up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "stage_meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "default_prim_path": str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
        "mesh_count": len(mesh_reports),
        "meshes": mesh_reports,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
