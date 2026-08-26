#!/usr/bin/env python3
"""Print Mesh attributes and Primvars for builder implementation diagnostics."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--prim", default="/World/mesh_")
    args = parser.parse_args()

    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(args.input, load=Usd.Stage.LoadNone)
    prim = stage.GetPrimAtPath(args.prim)
    print("prim", prim.GetTypeName())
    for attribute in prim.GetAttributes():
        value = attribute.Get()
        try:
            size = len(value)
        except (TypeError, AttributeError):
            size = None
        print("attribute", attribute.GetName(), attribute.GetTypeName(), size)
    for primvar in UsdGeom.PrimvarsAPI(prim).GetPrimvars():
        print(
            "primvar",
            primvar.GetPrimvarName(),
            primvar.GetTypeName(),
            primvar.GetInterpolation(),
            primvar.GetElementSize(),
        )
    for relationship in prim.GetRelationships():
        print("relationship", relationship.GetName(), list(relationship.GetTargets()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
