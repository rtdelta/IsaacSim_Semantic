#!/usr/bin/env python3
"""Print old Link transforms and reconstruct old joint axes in world space."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LINK_PATHS = [
    "/excavator_prim/track_prim",
    "/excavator_prim/cab_prim",
    "/excavator_prim/boom_prim",
    "/excavator_prim/arm_prim",
    "/excavator_prim/bucket_with_teeth_prim",
]


def _vec(value):
    return [float(value[index]) for index in range(len(value))]


def _matrix(value):
    if isinstance(value, tuple):
        value = value[0]
    return [[float(value[row][column]) for column in range(4)] for row in range(4)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--combined-mesh", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    from pxr import Gf, Usd, UsdGeom

    stage = Usd.Stage.Open(str(args.input.expanduser().resolve()), load=Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"failed to open {args.input}")
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    links = []
    for path in LINK_PATHS:
        prim = stage.GetPrimAtPath(path)
        links.append(
            {
                "path": path,
                "type_name": prim.GetTypeName(),
                "active": prim.IsActive(),
                "applied_schemas": list(prim.GetAppliedSchemas()),
                "local_transform": _matrix(cache.GetLocalTransformation(prim)),
                "world_transform": _matrix(cache.GetLocalToWorldTransform(prim)),
            }
        )

    visual_prims = []
    for prim in stage.TraverseAll():
        if prim.GetTypeName() not in ("Mesh", "ParticleField3DGaussianSplat") and not prim.GetAttribute("positions"):
            continue
        xformable = UsdGeom.Xformable(prim)
        visual_prims.append(
            {
                "path": str(prim.GetPath()),
                "type_name": prim.GetTypeName(),
                "active": prim.IsActive(),
                "ordered_xform_ops": [op.GetOpName() for op in xformable.GetOrderedXformOps()],
                "local_transform": _matrix(cache.GetLocalTransformation(prim)),
                "world_transform": _matrix(cache.GetLocalToWorldTransform(prim)),
            }
        )

    joints = []
    for prim in stage.TraverseAll():
        if prim.GetTypeName() != "PhysicsRevoluteJoint":
            continue
        body0_targets = prim.GetRelationship("physics:body0").GetTargets()
        body1_targets = prim.GetRelationship("physics:body1").GetTargets()
        body0 = stage.GetPrimAtPath(body0_targets[0])
        body1 = stage.GetPrimAtPath(body1_targets[0])
        pos0 = prim.GetAttribute("physics:localPos0").Get()
        pos1 = prim.GetAttribute("physics:localPos1").Get()
        rot0 = prim.GetAttribute("physics:localRot0").Get()
        rot1 = prim.GetAttribute("physics:localRot1").Get()
        axis_token = str(prim.GetAttribute("physics:axis").Get())
        unit_axis = {
            "X": Gf.Vec3d(1, 0, 0),
            "Y": Gf.Vec3d(0, 1, 0),
            "Z": Gf.Vec3d(0, 0, 1),
        }[axis_token]
        body0_world = cache.GetLocalToWorldTransform(body0)
        body1_world = cache.GetLocalToWorldTransform(body1)
        center0_world = body0_world.Transform(Gf.Vec3d(*pos0))
        center1_world = body1_world.Transform(Gf.Vec3d(*pos1))
        axis0_local = Gf.Rotation(rot0).TransformDir(unit_axis)
        axis1_local = Gf.Rotation(rot1).TransformDir(unit_axis)
        axis0_world = body0_world.TransformDir(axis0_local).GetNormalized()
        axis1_world = body1_world.TransformDir(axis1_local).GetNormalized()
        joints.append(
            {
                "path": str(prim.GetPath()),
                "body0": str(body0.GetPath()),
                "body1": str(body1.GetPath()),
                "local_pos0": _vec(pos0),
                "local_pos1": _vec(pos1),
                "local_rot0": str(rot0),
                "local_rot1": str(rot1),
                "axis_token": axis_token,
                "center0_world": _vec(center0_world),
                "center1_world": _vec(center1_world),
                "center_world_error": float((center0_world - center1_world).GetLength()),
                "axis0_world": _vec(axis0_world),
                "axis1_world": _vec(axis1_world),
                "axis_world_alignment": float(Gf.Dot(axis0_world, axis1_world)),
            }
        )

    mesh_comparison = None
    if args.combined_mesh:
        import numpy as np

        combined_stage = Usd.Stage.Open(
            str(args.combined_mesh.expanduser().resolve()), load=Usd.Stage.LoadNone
        )
        combined_prim = combined_stage.GetPrimAtPath("/World/mesh_")
        combined_points = np.asarray(
            UsdGeom.Mesh(combined_prim).GetPointsAttr().Get(), dtype=np.float32
        )
        reference_parts = []
        reference_arrays = []
        for link_path in LINK_PATHS:
            link_prim = stage.GetPrimAtPath(link_path)
            mesh_prims = [
                child for child in link_prim.GetAllChildren() if child.GetTypeName() == "Mesh"
            ]
            for mesh_prim in mesh_prims:
                points = np.asarray(
                    UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get(), dtype=np.float32
                )
                reference_arrays.append(points)
                reference_parts.append(
                    {
                        "link_path": link_path,
                        "mesh_path": str(mesh_prim.GetPath()),
                        "point_count": int(points.shape[0]),
                        "bounds_min": points.min(axis=0).tolist(),
                        "bounds_max": points.max(axis=0).tolist(),
                    }
                )
        reference_points = np.concatenate(reference_arrays, axis=0)

        def sorted_rows(values):
            order = np.lexsort((values[:, 2], values[:, 1], values[:, 0]))
            return values[order]

        point_multiset_equal = False
        maximum_sorted_point_difference = None
        if reference_points.shape == combined_points.shape:
            difference = np.abs(sorted_rows(reference_points) - sorted_rows(combined_points))
            maximum_sorted_point_difference = float(difference.max())
            point_multiset_equal = bool(np.array_equal(sorted_rows(reference_points), sorted_rows(combined_points)))
        mesh_comparison = {
            "combined_mesh_path": str(args.combined_mesh),
            "combined_point_count": int(combined_points.shape[0]),
            "reference_point_count": int(reference_points.shape[0]),
            "reference_parts": reference_parts,
            "point_multiset_exactly_equal": point_multiset_equal,
            "maximum_sorted_point_difference": maximum_sorted_point_difference,
        }

    report = {
        "links": links,
        "visual_prims": visual_prims,
        "joints": joints,
        "mesh_comparison": mesh_comparison,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
