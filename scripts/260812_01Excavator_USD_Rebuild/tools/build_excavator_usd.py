#!/usr/bin/env python3
"""Build the configured floating excavator USD in Isaac Sim's USD Python runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_path(value: str, base: Path, expand_environment_variables: bool) -> Path:
    if expand_environment_variables:
        value = os.path.expandvars(value)
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _vec3_array(values):
    import numpy as np

    return np.asarray([[value[0], value[1], value[2]] for value in values], dtype=np.float64)


def _quat_array(values):
    import numpy as np

    return np.asarray(
        [
            [
                value.GetReal(),
                value.GetImaginary()[0],
                value.GetImaginary()[1],
                value.GetImaginary()[2],
            ]
            for value in values
        ],
        dtype=np.float64,
    )


def _numpy_quatf_array(values):
    from pxr import Gf, Vt

    return Vt.QuatfArray(
        [
            Gf.Quatf(float(value[0]), Gf.Vec3f(*[float(item) for item in value[1:]]))
            for value in values
        ]
    )


def _quaternion_from_matrix(matrix):
    import numpy as np

    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (matrix[2, 1] - matrix[1, 2]) / scale
        y = (matrix[0, 2] - matrix[2, 0]) / scale
        z = (matrix[1, 0] - matrix[0, 1]) / scale
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            scale = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
            w = (matrix[2, 1] - matrix[1, 2]) / scale
            x = 0.25 * scale
            y = (matrix[0, 1] + matrix[1, 0]) / scale
            z = (matrix[0, 2] + matrix[2, 0]) / scale
        elif index == 1:
            scale = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
            w = (matrix[0, 2] - matrix[2, 0]) / scale
            x = (matrix[0, 1] + matrix[1, 0]) / scale
            y = 0.25 * scale
            z = (matrix[1, 2] + matrix[2, 1]) / scale
        else:
            scale = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
            w = (matrix[1, 0] - matrix[0, 1]) / scale
            x = (matrix[0, 2] + matrix[2, 0]) / scale
            y = (matrix[1, 2] + matrix[2, 1]) / scale
            z = 0.25 * scale
    quaternion = np.asarray([w, x, y, z], dtype=np.float64)
    return quaternion / np.linalg.norm(quaternion)


def _quaternion_multiply(left, right):
    import numpy as np

    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    result = np.empty_like(right)
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right.T
    result[:, 0] = lw * rw - lx * rx - ly * ry - lz * rz
    result[:, 1] = lw * rx + lx * rw + ly * rz - lz * ry
    result[:, 2] = lw * ry - lx * rz + ly * rw + lz * rx
    result[:, 3] = lw * rz + lx * ry - ly * rx + lz * rw
    result /= np.linalg.norm(result, axis=1, keepdims=True)
    return result


def _compute_frame(points_by_part, link_by_part, coordinate_config):
    import numpy as np

    gaussian_by_id = {part["id"]: part for part in coordinate_config["gaussian_parts"]}
    orientation = coordinate_config["coordinates"]["orientation"]
    explicit = orientation.get("explicit_rotation_matrix")
    if explicit is not None:
        rotation = np.asarray(explicit, dtype=np.float64)
    else:
        pca_id = orientation["pca_reference"]["reference_id"]
        track = points_by_part[pca_id]
        track_mean = track.mean(axis=0)
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov(track - track_mean, rowvar=False))
        up = eigenvectors[:, int(np.argmin(eigenvalues))]

        positive_means = []
        for reference in orientation.get("up_positive_references", []):
            if reference["reference_type"] != "link":
                raise RuntimeError("only Link up-positive references are supported")
            arrays = [
                points_by_part[part_id]
                for part_id, link_id in link_by_part.items()
                if link_id == reference["reference_id"]
            ]
            positive_means.extend(array.mean(axis=0) for array in arrays)
        if not positive_means:
            raise RuntimeError("orientation.up_positive_references resolved to no points")
        upper_mean = np.mean(np.asarray(positive_means), axis=0)
        if float((upper_mean - track_mean) @ up) < 0.0:
            up = -up

        forward_from_id = orientation["forward_from"]["reference_id"]
        forward_from = points_by_part[forward_from_id].mean(axis=0)
        forward_to = orientation["forward_to"]
        if forward_to["reference_type"] != "link":
            raise RuntimeError("only Link forward-to references are supported")
        forward_arrays = [
            points_by_part[part_id]
            for part_id, link_id in link_by_part.items()
            if link_id == forward_to["reference_id"]
        ]
        if not forward_arrays:
            raise RuntimeError("orientation.forward_to resolved to no points")
        forward_to_mean = np.concatenate(forward_arrays).mean(axis=0)
        forward = forward_to_mean - forward_from
        forward -= up * float(forward @ up)
        forward /= np.linalg.norm(forward)
        lateral = np.cross(up, forward)
        lateral /= np.linalg.norm(lateral)
        up = np.cross(forward, lateral)
        up /= np.linalg.norm(up)
        rotation = np.stack((forward, lateral, up), axis=0)

    determinant = float(np.linalg.det(rotation))
    orthogonality_error = float(np.max(np.abs(rotation @ rotation.T - np.eye(3))))
    if abs(determinant - 1.0) > 1.0e-8 or orthogonality_error > 1.0e-8:
        raise RuntimeError(
            f"invalid source-to-target rotation: det={determinant}, error={orthogonality_error}"
        )
    origin_cfg = coordinate_config["coordinates"]["origin"]
    reference_id = origin_cfg["reference"]["reference_id"]
    reference_points = points_by_part[reference_id]
    oriented = reference_points @ rotation.T
    center_oriented = 0.5 * (oriented.min(axis=0) + oriented.max(axis=0))
    origin_source = center_oriented @ rotation
    offset = np.asarray(origin_cfg.get("offset_m", [0.0, 0.0, 0.0]), dtype=np.float64)
    return {
        "source_to_target_rotation": rotation,
        "origin_source": origin_source,
        "offset_target": offset,
        "determinant": determinant,
        "orthogonality_error": orthogonality_error,
        "track_target_bounds": {
            "min": (oriented - center_oriented + offset).min(axis=0).tolist(),
            "max": (oriented - center_oriented + offset).max(axis=0).tolist(),
        },
    }


def _transform_points(points, frame):
    return (
        (points - frame["origin_source"]) @ frame["source_to_target_rotation"].T
        + frame["offset_target"]
    )


def _source_to_target_matrix(frame, units_to_meters=1.0):
    import numpy as np

    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = (
        float(units_to_meters) * frame["source_to_target_rotation"].T
    )
    matrix[3, :3] = (
        -frame["origin_source"] @ frame["source_to_target_rotation"].T
        + frame["offset_target"]
    )
    return matrix


def _axis_frame_quaternion(axis):
    import numpy as np

    x_axis = np.asarray(axis, dtype=np.float64)
    x_axis /= np.linalg.norm(x_axis)
    helper = np.asarray([0.0, 0.0, 1.0])
    if abs(float(x_axis @ helper)) > 0.9:
        helper = np.asarray([0.0, 1.0, 0.0])
    y_axis = np.cross(helper, x_axis)
    y_axis /= np.linalg.norm(y_axis)
    z_axis = np.cross(x_axis, y_axis)
    rotation = np.stack((x_axis, y_axis, z_axis), axis=1)
    return _quaternion_from_matrix(rotation)


def _apply_semantics(prim, semantic):
    if not semantic.get("enabled"):
        return
    from pxr import Sdf, Vt

    instance = "class"
    schema_name = f"SemanticsLabelsAPI:{instance}"
    prim.AddAppliedSchema(schema_name)
    prim.CreateAttribute(
        f"semantics:labels:{instance}", Sdf.ValueTypeNames.TokenArray, custom=False
    ).Set(Vt.TokenArray([str(semantic["label"])]))


def _prepend_api_schema(prim, schema_name):
    """Author an applied API token even when its Python schema is unavailable.

    The standalone USD environment used for deterministic asset construction
    exposes UsdPhysics but not PhysxSchema.  Isaac Sim resolves the token and
    property when the asset is later loaded by Kit.
    """
    prim.AddAppliedSchema(schema_name)


def _authored_api_schema_names(prim):
    """Return registered and unregistered applied-schema tokens."""
    names = set(prim.GetAppliedSchemas())
    authored = prim.GetMetadata("apiSchemas")
    if authored is not None:
        for field in (
            "explicitItems",
            "prependedItems",
            "appendedItems",
            "addedItems",
        ):
            names.update(getattr(authored, field, None) or [])
    return names


def _convert_gaussian(
    source,
    output,
    part,
    frame,
    up_axis,
    units_to_meters,
    visibility,
    purpose,
):
    import numpy as np
    import usd_convert_gsplat as gsplat
    from pxr import Usd, UsdGeom, Vt

    output.parent.mkdir(parents=True, exist_ok=True)
    data = gsplat.read_ply(str(source))
    actual = Path(
        gsplat.write_gaussian_splat_usd(
            data,
            str(output),
            source_file=str(source),
            prim_name=part["id"],
            up_axis=up_axis,
            rotation_degrees=(0.0, 0.0, 0.0),
        )
    )
    stage = Usd.Stage.Open(str(actual), load=Usd.Stage.LoadAll)
    prim = stage.GetDefaultPrim()
    positions = _vec3_array(prim.GetAttribute("positions").Get())
    positions_target = _transform_points(positions * float(units_to_meters), frame)
    bounds_min = positions_target.min(axis=0)
    bounds_max = positions_target.max(axis=0)
    UsdGeom.SetStageUpAxis(stage, up_axis)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    imageable = UsdGeom.Imageable(prim)
    imageable.CreateVisibilityAttr().Set(visibility)
    imageable.CreatePurposeAttr().Set(purpose)
    _apply_semantics(prim, part["semantic"])
    prim.SetCustomDataByKey(
        "excavatorBuilderCoordinateTransform",
        "all Gaussian geometry and radiance attributes preserved; common transform authored by entry stage",
    )
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(output), load=Usd.Stage.LoadAll)
    output_prim = reopened.GetDefaultPrim()
    output_positions = _vec3_array(output_prim.GetAttribute("positions").Get())
    if not np.array_equal(output_positions, positions):
        raise RuntimeError(f"Gaussian positions changed unexpectedly for {part['id']}")
    return {
        "file": str(output),
        "prim_path": str(prim.GetPath()),
        "splat_count": int(len(positions_target)),
        "units_to_meters": float(units_to_meters),
        "local_attributes_preserved": True,
        "local_bounds_min": positions.min(axis=0).tolist(),
        "local_bounds_max": positions.max(axis=0).tolist(),
        "bounds_min": bounds_min.tolist(),
        "bounds_max": bounds_max.tolist(),
        "sha256": _sha256(output),
    }


def _mesh_components(points, face_counts, face_indices):
    import numpy as np

    if not np.all(face_counts == 3):
        raise RuntimeError("v01 Mesh splitter currently requires triangular faces")
    triangles = face_indices.reshape(-1, 3)
    parent = np.arange(len(points), dtype=np.int64)

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root = find(int(left))
        right_root = find(int(right))
        if left_root != right_root:
            parent[right_root] = left_root

    for first, second, third in triangles:
        union(first, second)
        union(first, third)
    roots = np.fromiter((find(index) for index in range(len(points))), dtype=np.int64)
    face_roots = roots[triangles[:, 0]]
    result = []
    for root in np.unique(face_roots):
        result.append(np.flatnonzero(face_roots == root))
    return triangles, result


def _classify_mesh_components(
    points,
    triangles,
    components,
    gaussian_points_by_mesh,
    split_config,
    frozen_assignment,
):
    import numpy as np

    samples_by_mesh = {}
    for mesh_id, values in gaussian_points_by_mesh.items():
        stride = max(1, len(values) // 50000)
        samples_by_mesh[mesh_id] = values[::stride]
    assignments = {mesh_id: [] for mesh_id in samples_by_mesh}
    diagnostics = []
    frozen_by_index = None
    if frozen_assignment is not None:
        frozen_by_index = {
            int(item["component_index"]): item
            for item in frozen_assignment.get("assignments", [])
        }
        if len(frozen_by_index) != len(components):
            raise RuntimeError(
                "frozen Mesh component assignment count does not match current source"
            )
    for component_index, face_rows in enumerate(components):
        vertex_indices = np.unique(triangles[face_rows].reshape(-1))
        component_points = points[vertex_indices]
        if len(vertex_indices) <= 3:
            probe = component_points.mean(axis=0, keepdims=True)
        else:
            sample_count = min(32, len(component_points))
            selection = np.linspace(0, len(component_points) - 1, sample_count, dtype=np.int64)
            probe = component_points[selection]
        scores = []
        for mesh_id, reference in samples_by_mesh.items():
            minimum_squared = float("inf")
            for point in probe:
                for start in range(0, len(reference), 10000):
                    block = reference[start : start + 10000]
                    minimum_squared = min(
                        minimum_squared,
                        float(np.min(np.sum((block - point) ** 2, axis=1))),
                    )
            scores.append((math.sqrt(minimum_squared), mesh_id))
        scores.sort()
        margin = float(scores[1][0] - scores[0][0]) if len(scores) > 1 else None
        ambiguous = margin is not None and margin < float(
            split_config.get("ambiguity_margin_m", 0.0)
        )
        if frozen_by_index is not None:
            frozen = frozen_by_index.get(component_index)
            if frozen is None:
                raise RuntimeError(f"no frozen assignment for Mesh component {component_index}")
            if int(frozen["face_count"]) != len(face_rows) or int(
                frozen["vertex_count"]
            ) != len(vertex_indices):
                raise RuntimeError(
                    f"frozen assignment fingerprint mismatch for Mesh component {component_index}"
                )
            chosen = frozen["mesh_part_id"]
            if chosen not in assignments:
                raise RuntimeError(
                    f"frozen assignment references unknown Mesh part {chosen!r}"
                )
            method = "frozen_exact_historical_vertex_ownership"
        else:
            if ambiguous and split_config.get("fail_on_ambiguous_component", False):
                raise RuntimeError(
                    f"ambiguous Mesh component {component_index}: first={scores[0]}, "
                    f"second={scores[1]}, margin={margin} m"
                )
            chosen = scores[0][1]
            method = "nearest_reference_cloud"
        assignments[chosen].append(face_rows)
        diagnostics.append(
            {
                "component_index": component_index,
                "face_count": int(len(face_rows)),
                "vertex_count": int(len(vertex_indices)),
                "assigned_mesh_part_id": chosen,
                "assignment_method": method,
                "ambiguous_by_gaussian_margin": ambiguous,
                "candidate_margin_m": margin,
                "minimum_reference_distance_m": float(scores[0][0]),
                "second_minimum_reference_distance_m": (
                    float(scores[1][0]) if len(scores) > 1 else None
                ),
            }
        )
    return assignments, diagnostics


def _write_mesh_parts(
    source_file,
    source_prim_path,
    output,
    mesh_parts,
    gaussians,
    frame,
    split_config,
    frozen_assignment,
    units_to_meters,
    mesh_defaults,
):
    import numpy as np
    from pxr import Usd, UsdGeom, Vt

    source_stage = Usd.Stage.Open(str(source_file), load=Usd.Stage.LoadNone)
    source_prim = source_stage.GetPrimAtPath(source_prim_path)
    source_mesh = UsdGeom.Mesh(source_prim)
    source_points = _vec3_array(source_mesh.GetPointsAttr().Get())
    source_points_m = source_points * float(units_to_meters)
    face_counts = np.asarray(source_mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
    face_indices = np.asarray(source_mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
    source_normals = _vec3_array(source_mesh.GetNormalsAttr().Get())
    display_color = source_prim.GetAttribute("primvars:displayColor").Get()
    display_color_np = _vec3_array(display_color) if display_color else None
    normals_interpolation = source_mesh.GetNormalsInterpolation()
    if normals_interpolation != UsdGeom.Tokens.faceVarying:
        raise RuntimeError(
            f"v01 Mesh splitter requires faceVarying normals, got {normals_interpolation}"
        )
    triangles, components = _mesh_components(source_points, face_counts, face_indices)

    if frozen_assignment is not None:
        frozen_source = frozen_assignment.get("source", {})
        if frozen_source.get("prim_path") != source_prim_path:
            raise RuntimeError("frozen Mesh assignment source Prim mismatch")
        if int(frozen_source.get("point_count", -1)) != len(source_points):
            raise RuntimeError("frozen Mesh assignment point count mismatch")
        if int(frozen_source.get("face_count", -1)) != len(triangles):
            raise RuntimeError("frozen Mesh assignment face count mismatch")

    gaussian_points_by_mesh = {
        part["id"]: np.concatenate(
            [gaussians[gaussian_id] for gaussian_id in part["reference_gaussian_part_ids"]]
        )
        for part in mesh_parts
    }
    assignments, diagnostics = _classify_mesh_components(
        source_points_m,
        triangles,
        components,
        gaussian_points_by_mesh,
        split_config,
        frozen_assignment,
    )
    stage = Usd.Stage.CreateNew(str(output))
    root = UsdGeom.Xform.Define(stage, "/MeshParts").GetPrim()
    stage.SetDefaultPrim(root)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    output_records = {}
    emitted_faces = 0
    for part in mesh_parts:
        face_rows_arrays = assignments[part["id"]]
        if not face_rows_arrays:
            raise RuntimeError(f"Mesh classifier assigned no faces to {part['id']}")
        face_rows = np.concatenate(face_rows_arrays)
        old_triangles = triangles[face_rows]
        old_vertices, remapped = np.unique(old_triangles.reshape(-1), return_inverse=True)
        new_triangles = remapped.reshape(-1, 3)
        points_target = _transform_points(source_points_m[old_vertices], frame)
        mesh = UsdGeom.Mesh.Define(stage, f"/MeshParts/{part['id']}")
        mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(points_target.astype(np.float32)))
        mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3] * len(new_triangles)))
        mesh.GetFaceVertexIndicesAttr().Set(
            Vt.IntArray.FromNumpy(new_triangles.reshape(-1).astype(np.int32))
        )
        mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        source_corner_rows = face_rows[:, None] * 3 + np.arange(3, dtype=np.int64)[None, :]
        normals_target = source_normals[source_corner_rows.reshape(-1)]
        normals_target = normals_target @ frame["source_to_target_rotation"].T
        mesh.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(normals_target.astype(np.float32)))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
        if display_color_np is not None:
            colors = display_color_np[source_corner_rows.reshape(-1)]
            mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.faceVarying).Set(
                Vt.Vec3fArray.FromNumpy(colors.astype(np.float32))
            )
        mesh.GetVisibilityAttr().Set(
            part.get("visibility_override") or mesh_defaults["visibility"]
        )
        mesh.GetPurposeAttr().Set(
            part.get("purpose_override") or mesh_defaults["purpose"]
        )
        bounds_min = points_target.min(axis=0)
        bounds_max = points_target.max(axis=0)
        mesh.GetExtentAttr().Set(
            Vt.Vec3fArray(
                [tuple(float(value) for value in bounds_min), tuple(float(value) for value in bounds_max)]
            )
        )
        output_records[part["id"]] = {
            "prim_path": str(mesh.GetPath()),
            "point_count": int(len(points_target)),
            "face_count": int(len(new_triangles)),
            "bounds_min": bounds_min.tolist(),
            "bounds_max": bounds_max.tolist(),
        }
        emitted_faces += len(new_triangles)
    stage.GetRootLayer().Save()
    if emitted_faces != len(triangles):
        raise RuntimeError(f"Mesh face conservation failed: {emitted_faces} != {len(triangles)}")
    return {
        "source_point_count": int(len(source_points)),
        "source_face_count": int(len(triangles)),
        "component_count": int(len(components)),
        "emitted_face_count": int(emitted_faces),
        "parts": output_records,
        "component_assignments": diagnostics,
        "assignment_source": (
            "frozen_exact_historical_vertex_ownership"
            if frozen_assignment is not None
            else "nearest_reference_cloud"
        ),
        "sha256": _sha256(output),
    }


def _copy_reference_prim(
    stage, target_path, asset_path, source_path, payload=False, transform_matrix=None
):
    from pxr import Gf, Sdf, UsdGeom

    prim = stage.DefinePrim(target_path)
    if payload:
        prim.GetPayloads().AddPayload(asset_path, Sdf.Path(source_path))
    else:
        prim.GetReferences().AddReference(asset_path, Sdf.Path(source_path))
    if transform_matrix is not None:
        matrix = Gf.Matrix4d()
        for row in range(4):
            matrix.SetRow(
                row,
                Gf.Vec4d(*[float(transform_matrix[row, column]) for column in range(4)]),
            )
        UsdGeom.Xformable(prim).AddTransformOp(
            UsdGeom.XformOp.PrecisionDouble, "sourceToTarget"
        ).Set(matrix)
    return prim


def _build_stage(
    config,
    calibration,
    output_root,
    gaussian_records,
    mesh_report,
    frame,
    file_name,
    *,
    include_visual,
    include_physics,
):
    import numpy as np
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

    entry = output_root / file_name
    stage = Usd.Stage.CreateNew(str(entry))
    up_axis = UsdGeom.Tokens.z if config["stage"]["up_axis"] == "Z" else UsdGeom.Tokens.y
    UsdGeom.SetStageUpAxis(stage, up_axis)
    UsdGeom.SetStageMetersPerUnit(stage, float(config["stage"]["meters_per_unit"]))
    root_path = config["stage"]["root_prim_path"]
    root = UsdGeom.Xform.Define(stage, root_path).GetPrim()
    root.SetDisplayName(config["project"]["asset_name"])
    root.SetKind(config["stage"]["model_kind"])
    root.SetCustomDataByKey("assetId", config["project"]["asset_id"])
    root.SetCustomDataByKey("floatingBase", True)
    stage.SetDefaultPrim(root)
    UsdGeom.Scope.Define(stage, root_path + "/Links")
    if include_physics:
        UsdGeom.Scope.Define(stage, root_path + "/Joints")

    links = {item["id"]: item for item in config["links"] if item.get("enabled", True)}
    link_prims = {}
    for link_id, link in links.items():
        full_path = root_path + "/" + link["prim_path"].strip("/")
        prim = UsdGeom.Xform.Define(stage, full_path).GetPrim()
        prim.SetDisplayName(link["display_name"])
        if include_physics:
            profile = dict(config["physics_profiles"][link["physics_profile"]])
            profile.update(link.get("physics_overrides", {}))
            rigid = UsdPhysics.RigidBodyAPI.Apply(prim)
            rigid.GetRigidBodyEnabledAttr().Set(bool(profile["rigid_body_enabled"]))
            rigid.GetKinematicEnabledAttr().Set(bool(profile["kinematic_enabled"]))
            if bool(profile.get("disable_gravity", False)):
                _prepend_api_schema(prim, "PhysxRigidBodyAPI")
                prim.CreateAttribute(
                    "physxRigidBody:disableGravity", Sdf.ValueTypeNames.Bool, custom=False
                ).Set(True)
            mass = UsdPhysics.MassAPI.Apply(prim)
            mass.GetMassAttr().Set(float(profile["mass"]))
            mass.GetCenterOfMassAttr().Set(Gf.Vec3f(*profile["center_of_mass"]))
            mass.GetDiagonalInertiaAttr().Set(Gf.Vec3f(*profile["diagonal_inertia"]))
            mass.GetPrincipalAxesAttr().Set(Gf.Quatf(*profile["principal_axes_wxyz"]))
        link_prims[link_id] = prim
        if include_visual:
            UsdGeom.Scope.Define(stage, full_path + "/Visual")
            UsdGeom.Scope.Define(stage, full_path + "/Visual/Gaussian")
            UsdGeom.Scope.Define(stage, full_path + "/Visual/Mesh")

    if include_visual:
        gaussian_dir = config["outputs"]["gaussian_parts"]["directory"]
        for part in config["gaussian"]["parts"]:
            if not part.get("enabled", True):
                continue
            target = root_path + "/" + links[part["link_id"]]["prim_path"].strip("/") + "/" + part["relative_prim_path"]
            asset = f"./{gaussian_dir}/{part['id']}.usdc"
            gaussian_transform = _source_to_target_matrix(
                frame, gaussian_records[part["id"]]["units_to_meters"]
            )
            _copy_reference_prim(
                stage,
                target,
                asset,
                f"/{part['id']}",
                payload=True,
                transform_matrix=gaussian_transform,
            )

        mesh_asset = "./" + config["outputs"]["mesh_layer_file"]
        for part in config["mesh"]["parts"]:
            if not part.get("enabled", True):
                continue
            target = root_path + "/" + links[part["link_id"]]["prim_path"].strip("/") + "/" + part["relative_prim_path"]
            _copy_reference_prim(stage, target, mesh_asset, mesh_report["parts"][part["id"]]["prim_path"])

    if include_physics:
        articulation_root_id = config["articulation"]["articulation_root"]["reference_id"]
        UsdPhysics.ArticulationRootAPI.Apply(link_prims[articulation_root_id])

    calibration_by_id = {item["id"]: item for item in calibration["joints"]}
    joint_records = []
    for joint in config["joints"] if include_physics else []:
        if not joint.get("enabled", True):
            continue
        body0_id = joint["body0"]["reference_id"]
        body1_id = joint["body1"]["reference_id"]
        source_geometry = calibration_by_id[joint["geometry"]["calibration_id"]]
        center_source = np.asarray(
            joint["geometry"].get("center_override") or source_geometry["center"], dtype=np.float64
        )
        center_source *= float(
            calibration.get("coordinate_frame", {}).get("units_to_meters", 1.0)
        )
        axis_source = np.asarray(
            joint["geometry"].get("axis_override") or source_geometry["axis"], dtype=np.float64
        ) * float(joint["geometry"].get("axis_sign", 1))
        center_target = _transform_points(center_source.reshape(1, 3), frame)[0]
        axis_target = axis_source @ frame["source_to_target_rotation"].T
        axis_target /= np.linalg.norm(axis_target)
        quaternion = _axis_frame_quaternion(axis_target)
        full_path = root_path + "/" + joint["prim_path"].strip("/")
        usd_joint = UsdPhysics.RevoluteJoint.Define(stage, full_path)
        usd_joint.CreateBody0Rel().SetTargets([link_prims[body0_id].GetPath()])
        usd_joint.CreateBody1Rel().SetTargets([link_prims[body1_id].GetPath()])
        usd_joint.CreateAxisAttr().Set(UsdPhysics.Tokens.x)
        usd_joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*[float(value) for value in center_target]))
        usd_joint.CreateLocalPos1Attr().Set(Gf.Vec3f(*[float(value) for value in center_target]))
        rotation = Gf.Quatf(float(quaternion[0]), Gf.Vec3f(*[float(value) for value in quaternion[1:]]))
        usd_joint.CreateLocalRot0Attr().Set(rotation)
        usd_joint.CreateLocalRot1Attr().Set(rotation)
        usd_joint.CreateCollisionEnabledAttr().Set(bool(joint["collision_enabled"]))
        if joint["limits"]["enabled"]:
            usd_joint.CreateLowerLimitAttr().Set(float(joint["limits"]["lower_deg"]))
            usd_joint.CreateUpperLimitAttr().Set(float(joint["limits"]["upper_deg"]))
        joint_records.append(
            {
                "id": joint["id"],
                "prim_path": full_path,
                "body0": str(link_prims[body0_id].GetPath()),
                "body1": str(link_prims[body1_id].GetPath()),
                "center_target": center_target.tolist(),
                "axis_target": axis_target.tolist(),
                "local_frame_wxyz": quaternion.tolist(),
            }
        )
    stage.GetRootLayer().Save()
    return entry, joint_records


def _compose_entry(config, output_root):
    from pxr import Usd, UsdGeom

    path = output_root / config["outputs"]["entry_file"]
    stage = Usd.Stage.CreateNew(str(path))
    stage.GetRootLayer().subLayerPaths = [
        "./" + config["outputs"]["visual_layer_file"],
        "./" + config["outputs"]["physics_layer_file"],
    ]
    up_axis = UsdGeom.Tokens.z if config["stage"]["up_axis"] == "Z" else UsdGeom.Tokens.y
    UsdGeom.SetStageUpAxis(stage, up_axis)
    UsdGeom.SetStageMetersPerUnit(stage, float(config["stage"]["meters_per_unit"]))
    root = stage.GetPrimAtPath(config["stage"]["root_prim_path"])
    if not root:
        raise RuntimeError("layer composition did not produce the configured root Prim")
    stage.SetDefaultPrim(root)
    stage.GetRootLayer().Save()
    return path


def _write_debug_stage(config, output_root):
    from pxr import Usd, UsdGeom

    if not config["outputs"].get("write_debug_stage", False):
        return None
    path = output_root / config["outputs"]["debug_stage_file"]
    stage = Usd.Stage.CreateNew(str(path))
    stage.GetRootLayer().subLayerPaths = ["./" + config["outputs"]["entry_file"]]
    links = {item["id"]: item for item in config["links"] if item.get("enabled", True)}
    root_path = config["stage"]["root_prim_path"]
    for part in config["mesh"]["parts"]:
        if not part.get("enabled", True):
            continue
        target = root_path + "/" + links[part["link_id"]]["prim_path"].strip("/") + "/" + part["relative_prim_path"]
        imageable = UsdGeom.Imageable(stage.OverridePrim(target))
        imageable.CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
        imageable.CreatePurposeAttr().Set(UsdGeom.Tokens.default_)
    root = stage.GetPrimAtPath(root_path)
    stage.SetDefaultPrim(root)
    stage.GetRootLayer().Save()
    return path


def _validate_stage(path, config, gaussian_records, mesh_report):
    import numpy as np
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.Open(str(path), load=Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"failed to reopen final stage: {path}")
    errors = []
    root_path = config["stage"]["root_prim_path"]
    if str(stage.GetDefaultPrim().GetPath()) != config["stage"]["default_prim_path"]:
        errors.append("default Prim mismatch")
    if str(UsdGeom.GetStageUpAxis(stage)).upper() != config["stage"]["up_axis"]:
        errors.append("stage up axis mismatch")
    links = {item["id"]: item for item in config["links"] if item.get("enabled", True)}
    link_checks = []
    for link_id, link in links.items():
        prim = stage.GetPrimAtPath(root_path + "/" + link["prim_path"].strip("/"))
        if not prim or not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            errors.append(f"Link {link_id} is missing RigidBodyAPI")
            continue
        profile = dict(config["physics_profiles"][link["physics_profile"]])
        profile.update(link.get("physics_overrides", {}))
        actual_disable_gravity = bool(
            prim.GetAttribute("physxRigidBody:disableGravity").Get()
        )
        expected_disable_gravity = bool(profile.get("disable_gravity", False))
        applied_schemas = _authored_api_schema_names(prim)
        if actual_disable_gravity != expected_disable_gravity:
            errors.append(f"Link {link_id} disable-gravity setting mismatch")
        if expected_disable_gravity and "PhysxRigidBodyAPI" not in applied_schemas:
            errors.append(f"Link {link_id} is missing PhysxRigidBodyAPI token")
        link_checks.append(
            {
                "id": link_id,
                "rigid_body": True,
                "kinematic_enabled": bool(
                    UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Get()
                ),
                "disable_gravity": actual_disable_gravity,
                "physx_rigid_body_api_token": "PhysxRigidBodyAPI" in applied_schemas,
            }
        )
    calibration_count = 0
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    joint_checks = []
    for joint in config["joints"]:
        prim_path = root_path + "/" + joint["prim_path"].strip("/")
        usd_joint = UsdPhysics.RevoluteJoint.Get(stage, prim_path)
        prim = usd_joint.GetPrim()
        if not prim:
            errors.append(f"Joint is missing: {prim_path}")
            continue
        body0 = stage.GetPrimAtPath(usd_joint.GetBody0Rel().GetTargets()[0])
        body1 = stage.GetPrimAtPath(usd_joint.GetBody1Rel().GetTargets()[0])
        pos0 = usd_joint.GetLocalPos0Attr().Get()
        pos1 = usd_joint.GetLocalPos1Attr().Get()
        rot0 = usd_joint.GetLocalRot0Attr().Get()
        rot1 = usd_joint.GetLocalRot1Attr().Get()
        center0 = cache.GetLocalToWorldTransform(body0).Transform(Gf.Vec3d(*pos0))
        center1 = cache.GetLocalToWorldTransform(body1).Transform(Gf.Vec3d(*pos1))
        axis0 = cache.GetLocalToWorldTransform(body0).TransformDir(
            Gf.Rotation(rot0).TransformDir(Gf.Vec3d(1, 0, 0))
        ).GetNormalized()
        axis1 = cache.GetLocalToWorldTransform(body1).TransformDir(
            Gf.Rotation(rot1).TransformDir(Gf.Vec3d(1, 0, 0))
        ).GetNormalized()
        center_error = float((center0 - center1).GetLength())
        axis_alignment = float(Gf.Dot(axis0, axis1))
        if center_error > 1.0e-6 or axis_alignment < 1.0 - 1.0e-6:
            errors.append(f"Joint frame mismatch for {joint['id']}")
        joint_checks.append(
            {
                "id": joint["id"],
                "center_error_m": center_error,
                "axis_alignment_dot": axis_alignment,
            }
        )
        calibration_count += 1
    gaussian_count = 0
    gaussian_splats = 0
    for part in config["gaussian"]["parts"]:
        if not part.get("enabled", True):
            continue
        prim_path = root_path + "/" + links[part["link_id"]]["prim_path"].strip("/") + "/" + part["relative_prim_path"]
        prim = stage.GetPrimAtPath(prim_path)
        positions = prim.GetAttribute("positions").Get() if prim else None
        if not positions:
            errors.append(f"Gaussian Prim is missing or empty: {prim_path}")
        else:
            local_positions = _vec3_array(positions)
            world = cache.GetLocalToWorldTransform(prim)
            world_matrix = np.asarray(
                [[float(world[row][column]) for column in range(4)] for row in range(4)],
                dtype=np.float64,
            )
            world_positions = (
                local_positions @ world_matrix[:3, :3] + world_matrix[3, :3]
            )
            expected = gaussian_records[part["id"]]
            bounds_error = max(
                float(
                    np.max(
                        np.abs(
                            world_positions.min(axis=0)
                            - np.asarray(expected["bounds_min"], dtype=np.float64)
                        )
                    )
                ),
                float(
                    np.max(
                        np.abs(
                            world_positions.max(axis=0)
                            - np.asarray(expected["bounds_max"], dtype=np.float64)
                        )
                    )
                ),
            )
            if bounds_error > 1.0e-5:
                errors.append(
                    f"Gaussian world transform mismatch for {part['id']}: {bounds_error} m"
                )
            gaussian_count += 1
            gaussian_splats += len(positions)
    if gaussian_splats != sum(item["splat_count"] for item in gaussian_records.values()):
        errors.append("Gaussian splat count mismatch after composition")
    if mesh_report["emitted_face_count"] != mesh_report["source_face_count"]:
        errors.append("Mesh face conservation failed")
    if errors:
        raise RuntimeError("final stage validation failed: " + "; ".join(errors))
    return {
        "status": "passed",
        "entry_file": str(path),
        "default_prim": str(stage.GetDefaultPrim().GetPath()),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "link_count": len(links),
        "joint_count": calibration_count,
        "gaussian_part_count": gaussian_count,
        "gaussian_splat_count": gaussian_splats,
        "mesh_face_count": mesh_report["emitted_face_count"],
        "link_checks": link_checks,
        "joint_checks": joint_checks,
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    import numpy as np
    import usd_convert_gsplat as gsplat

    config_path = args.config.expanduser().resolve()
    config = _read_json(config_path)
    if config.get("coordinates", {}).get("bake_transform_into_geometry") is not False:
        raise RuntimeError(
            "v01 formal builder requires coordinates.bake_transform_into_geometry=false "
            "so Gaussian positions, orientations and spherical harmonics remain unchanged"
        )
    if not config["outputs"].get("use_relative_asset_paths", True):
        raise RuntimeError("v01 formal builder requires outputs.use_relative_asset_paths=true")
    if not config["outputs"]["gaussian_parts"].get("one_file_per_part", True):
        raise RuntimeError("v01 formal builder requires one Gaussian USD per part")
    if config["mesh"]["defaults"].get("create_collision", False):
        raise RuntimeError("v01 formal builder does not implement collision generation")
    if any(
        part.get("create_collision_override") is True
        for part in config["mesh"]["parts"]
        if part.get("enabled", True)
    ):
        raise RuntimeError("v01 formal builder does not implement collision generation")
    if config.get("physics_scene", {}).get("author_in_asset", False):
        raise RuntimeError("v01 formal builder keeps PhysicsScene outside the reusable asset")
    enabled_mesh_sources = [
        item for item in config["mesh"]["sources"] if item.get("enabled", True)
    ]
    if len(enabled_mesh_sources) != 1:
        raise RuntimeError("v01 formal builder currently requires exactly one enabled Mesh source")
    if any(
        part.get("initial_position_deg", 0.0) != 0.0
        for part in config["joints"]
        if part.get("enabled", True)
    ):
        raise RuntimeError("v01 formal builder requires zero initial Joint positions")
    if any(
        part.get("drive", {}).get("enabled", False)
        for part in config["joints"]
        if part.get("enabled", True)
    ):
        raise RuntimeError("v01 formal builder does not implement Joint drives")
    if not config["articulation"].get("enabled", True):
        raise RuntimeError("v01 formal builder requires articulation.enabled=true")
    if config["articulation"].get("mode") != "floating" or config["articulation"].get(
        "fixed_base", {}
    ).get("enabled", False):
        raise RuntimeError("v01 formal builder currently implements floating articulation only")
    config_dir = config_path.parent
    expand_env = bool(config["paths"].get("expand_environment_variables", True))
    calibration_path = _resolve_path(
        config["paths"]["joint_calibration_file"], config_dir, expand_env
    )
    calibration = _read_json(calibration_path)
    if calibration.get("migration", {}).get("normal_build_dependency") is not False:
        raise RuntimeError("formal builder requires a calibration independent of the historical USD")
    assignment_file_value = config["paths"].get("mesh_component_assignment_file")
    assignment_path = (
        _resolve_path(assignment_file_value, config_dir, expand_env)
        if assignment_file_value
        else None
    )
    frozen_assignment = _read_json(assignment_path) if assignment_path else None
    output_root = (
        args.output_directory.expanduser().resolve()
        if args.output_directory
        else _resolve_path(config["paths"]["output_directory"], config_dir, expand_env)
    )
    if output_root.exists() and not args.overwrite:
        raise FileExistsError(f"output exists; pass --overwrite to replace it: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent))
    try:
        enabled_gaussians = [
            part for part in config["gaussian"]["parts"] if part.get("enabled", True)
        ]
        source_points = {}
        link_by_part = {}
        source_hashes = {}
        for part in enabled_gaussians:
            source = _resolve_path(part["source_file"], config_dir, expand_env)
            data = gsplat.read_ply(str(source))
            units = part.get("units_to_meters_override")
            if units is None:
                units = config["gaussian"]["defaults"]["units_to_meters"]
            source_points[part["id"]] = (
                data.positions.astype(np.float64) * float(units)
            )
            link_by_part[part["id"]] = part["link_id"]
            source_hashes[part["id"]] = _sha256(source)
        frame = _compute_frame(
            source_points,
            link_by_part,
            {
                "gaussian_parts": enabled_gaussians,
                "coordinates": config["coordinates"],
            },
        )

        gaussian_records = {}
        gaussian_dir = staging / config["outputs"]["gaussian_parts"]["directory"]
        for part in enabled_gaussians:
            source = _resolve_path(part["source_file"], config_dir, expand_env)
            units = part.get("units_to_meters_override")
            if units is None:
                units = config["gaussian"]["defaults"]["units_to_meters"]
            gaussian_records[part["id"]] = _convert_gaussian(
                source,
                gaussian_dir / f"{part['id']}.usdc",
                part,
                frame,
                config["stage"]["up_axis"],
                units,
                part.get("visibility_override")
                or config["gaussian"]["defaults"]["visibility"],
                config["gaussian"]["defaults"]["purpose"],
            )

        mesh_source_cfg = next(
            item for item in config["mesh"]["sources"] if item.get("enabled", True)
        )
        mesh_source = _resolve_path(mesh_source_cfg["source_file"], config_dir, expand_env)
        if frozen_assignment is not None:
            expected_mesh_hash = frozen_assignment.get("source", {}).get("file_sha256")
            actual_mesh_hash = _sha256(mesh_source)
            if actual_mesh_hash != expected_mesh_hash:
                raise RuntimeError(
                    "frozen Mesh component assignment source hash mismatch: "
                    f"expected {expected_mesh_hash}, got {actual_mesh_hash}"
                )
        mesh_output = staging / config["outputs"]["mesh_layer_file"]
        mesh_report = _write_mesh_parts(
            mesh_source,
            mesh_source_cfg["source_prim_path"],
            mesh_output,
            [part for part in config["mesh"]["parts"] if part.get("enabled", True)],
            source_points,
            frame,
            mesh_source_cfg["split"],
            frozen_assignment,
            mesh_source_cfg["units_to_meters"],
            config["mesh"]["defaults"],
        )
        visual_layer, _ = _build_stage(
            config,
            calibration,
            staging,
            gaussian_records,
            mesh_report,
            frame,
            config["outputs"]["visual_layer_file"],
            include_visual=True,
            include_physics=False,
        )
        physics_layer, joint_records = _build_stage(
            config,
            calibration,
            staging,
            gaussian_records,
            mesh_report,
            frame,
            config["outputs"]["physics_layer_file"],
            include_visual=False,
            include_physics=True,
        )
        entry = _compose_entry(config, staging)
        debug_stage = _write_debug_stage(config, staging)
        validation = _validate_stage(entry, config, gaussian_records, mesh_report)
        resolved = json.loads(json.dumps(config))
        resolved["resolved"] = {
            "config_file": str(config_path),
            "calibration_file": str(calibration_path),
            "mesh_component_assignment_file": (
                str(assignment_path) if assignment_path else None
            ),
            "output_directory": str(output_root),
            "source_to_target_rotation": frame["source_to_target_rotation"].tolist(),
            "origin_source": frame["origin_source"].tolist(),
            "offset_target": frame["offset_target"].tolist(),
            "joint_frames": joint_records,
            "layers": {
                "visual": str(output_root / visual_layer.name),
                "physics": str(output_root / physics_layer.name),
                "entry": str(output_root / entry.name),
                "debug": str(output_root / debug_stage.name) if debug_stage else None,
            },
        }
        _write_json(staging / config["outputs"]["resolved_config_file"], resolved)
        report_gaussian = json.loads(json.dumps(gaussian_records))
        for part_id, record in report_gaussian.items():
            record["file"] = str(
                output_root
                / config["outputs"]["gaussian_parts"]["directory"]
                / f"{part_id}.usdc"
            )
        report_validation = json.loads(json.dumps(validation))
        report_validation["entry_file"] = str(
            output_root / config["outputs"]["entry_file"]
        )
        build_report = {
            "schema_version": "1.0",
            "kind": "excavator_usd_build_report",
            "status": "passed",
            "historical_usd_used": False,
            "inputs": {
                "config": {"path": str(config_path), "sha256": _sha256(config_path)},
                "calibration": {
                    "path": str(calibration_path),
                    "sha256": _sha256(calibration_path),
                    "migration_status": calibration.get("migration", {}).get("status"),
                },
                "gaussian_source_sha256": source_hashes,
                "mesh": {"path": str(mesh_source), "sha256": _sha256(mesh_source)},
                "mesh_component_assignment": (
                    {
                        "path": str(assignment_path),
                        "sha256": _sha256(assignment_path),
                        "one_time_migration_artifact": bool(
                            frozen_assignment.get("one_time_migration_artifact")
                        ),
                    }
                    if assignment_path
                    else None
                ),
            },
            "coordinate_transform": {
                "source_to_target_rotation": frame["source_to_target_rotation"].tolist(),
                "origin_source": frame["origin_source"].tolist(),
                "offset_target": frame["offset_target"].tolist(),
                "determinant": frame["determinant"],
                "orthogonality_error": frame["orthogonality_error"],
                "track_target_bounds": frame["track_target_bounds"],
            },
            "gaussian": report_gaussian,
            "mesh": mesh_report,
            "joints": joint_records,
            "validation": report_validation,
        }
        _write_json(staging / config["outputs"]["validation_report_file"], build_report)
        if output_root.exists():
            if not args.overwrite:
                raise FileExistsError(output_root)
            backup = output_root.with_name(output_root.name + ".previous")
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(output_root, backup)
            try:
                os.replace(staging, output_root)
                shutil.rmtree(backup)
            except Exception:
                if not output_root.exists() and backup.exists():
                    os.replace(backup, output_root)
                raise
        else:
            os.replace(staging, output_root)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "output_directory": str(output_root),
                    "entry_file": str(output_root / config["outputs"]["entry_file"]),
                    "links": validation["link_count"],
                    "joints": validation["joint_count"],
                    "gaussian_parts": validation["gaussian_part_count"],
                    "gaussian_splats": validation["gaussian_splat_count"],
                    "mesh_faces": validation["mesh_face_count"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
