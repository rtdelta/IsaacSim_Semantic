#!/usr/bin/env python3
"""Extract non-geometric reference data from an existing excavator USD."""

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


def _json_value(value):
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    try:
        return [_json_value(item) for item in value]
    except TypeError:
        return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    if not input_path.is_file():
        parser.error(f"input file does not exist: {input_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(input_path), load=Usd.Stage.LoadNone)
    if stage is None:
        raise RuntimeError(f"failed to open stage: {input_path}")

    joints = []
    semantic_prims = []
    named_parts = []
    for prim in stage.TraverseAll():
        prim_type = prim.GetTypeName()
        prim_path = str(prim.GetPath())
        if "Joint" in prim_type:
            attributes = {}
            for name in (
                "physics:axis",
                "physics:localPos0",
                "physics:localPos1",
                "physics:localRot0",
                "physics:localRot1",
                "physics:lowerLimit",
                "physics:upperLimit",
                "physics:collisionEnabled",
            ):
                attribute = prim.GetAttribute(name)
                if attribute:
                    attributes[name] = _json_value(attribute.Get())
            relationships = {}
            for name in ("physics:body0", "physics:body1"):
                relationship = prim.GetRelationship(name)
                if relationship:
                    relationships[name] = [str(target) for target in relationship.GetTargets()]
            joints.append(
                {
                    "path": prim_path,
                    "name": prim.GetName(),
                    "type_name": prim_type,
                    "active": prim.IsActive(),
                    "attributes": attributes,
                    "relationships": relationships,
                }
            )

        semantic_attributes = {}
        for attribute in prim.GetAttributes():
            name = attribute.GetName()
            if "semantic" in name.lower():
                semantic_attributes[name] = _json_value(attribute.Get())
        if semantic_attributes:
            semantic_prims.append(
                {
                    "path": prim_path,
                    "type_name": prim_type,
                    "active": prim.IsActive(),
                    "attributes": semantic_attributes,
                }
            )

        if any(token in prim.GetName().lower() for token in ("track", "cab", "boom", "arm", "bucket", "tooth")):
            references = prim.GetMetadata("references")
            named_parts.append(
                {
                    "path": prim_path,
                    "type_name": prim_type,
                    "active": prim.IsActive(),
                    "references": str(references) if references else None,
                }
            )

    report = {
        "schema_version": "1.0",
        "kind": "reference_excavator_usd_manifest",
        "usage_policy": "reference_only_not_a_build_dependency",
        "source_file": str(input_path),
        "source_file_size_bytes": input_path.stat().st_size,
        "source_file_sha256": _sha256(input_path),
        "stage_up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "stage_meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "default_prim_path": str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
        "joints": joints,
        "semantic_prims": semantic_prims,
        "named_parts": named_parts,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "kind": report["kind"],
                "source_file_size_bytes": report["source_file_size_bytes"],
                "joint_count": len(joints),
                "semantic_prim_count": len(semantic_prims),
                "named_part_count": len(named_parts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
