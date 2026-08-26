#!/usr/bin/env python3
"""Run a minimal Gaussian PLY to USD conversion inside Isaac Sim Kit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _value_size(value):
    try:
        return len(value)
    except (TypeError, AttributeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--prim-name", default="GaussianProbe")
    parser.add_argument("--up-axis", choices=("Y", "Z"), default="Z")
    parser.add_argument("--rotate-x", type=float, default=0.0)
    parser.add_argument("--rotate-y", type=float, default=0.0)
    parser.add_argument("--rotate-z", type=float, default=0.0)
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    if not input_path.is_file():
        parser.error(f"input file does not exist: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # SimulationApp forwards unknown process arguments to Kit. Keep project CLI
    # arguments out of Kit's settings parser after argparse has consumed them.
    sys.argv = [sys.argv[0]]

    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True, "sync_loads": True})
    try:
        import omni.kit.app

        manager = omni.kit.app.get_app().get_extension_manager()
        manager.set_extension_enabled_immediate("omni.kit.converter.gsplat", True)
        app.update()

        import omni.kit.converter.gsplat as gsplat
        from pxr import Usd, UsdGeom

        splat_data = gsplat.read_ply(str(input_path))
        actual_output = gsplat.write_gaussian_splat_usd(
            splat_data,
            str(output_path),
            source_file=str(input_path),
            prim_name=args.prim_name,
            up_axis=args.up_axis,
            rotation_degrees=(args.rotate_x, args.rotate_y, args.rotate_z),
        )

        stage = Usd.Stage.Open(actual_output)
        if stage is None:
            raise RuntimeError(f"failed to reopen converted stage: {actual_output}")
        default_prim = stage.GetDefaultPrim()
        attributes = []
        for attribute in default_prim.GetAttributes():
            value = attribute.Get()
            attributes.append({
                "name": attribute.GetName(),
                "type_name": str(attribute.GetTypeName()),
                "value_size": _value_size(value),
            })

        report = {
            "schema_version": "1.0",
            "kind": "gaussian_converter_probe",
            "converter_extension": "omni.kit.converter.gsplat",
            "converter_version": gsplat.get_version(),
            "input_file": str(input_path),
            "input_splat_count": int(splat_data.count),
            "input_has_sh_rest": splat_data.f_rest is not None,
            "input_sh_rest_coefficient_count": (
                int(splat_data.f_rest.shape[1]) if splat_data.f_rest is not None else 0
            ),
            "requested_output": str(output_path),
            "actual_output": str(actual_output),
            "rotation_degrees_xyz": [args.rotate_x, args.rotate_y, args.rotate_z],
            "stage_up_axis": str(UsdGeom.GetStageUpAxis(stage)),
            "stage_meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
            "default_prim_path": str(default_prim.GetPath()),
            "default_prim_type": default_prim.GetTypeName(),
            "attributes": attributes,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
