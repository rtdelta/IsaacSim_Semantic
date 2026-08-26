"""Pure-Python tests for articulation stage discovery and diagnostics."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from articulation_stage_validator import (
    ArticulationStageIssue,
    ArticulationStageReport,
    validate_articulation_stage,
)


class _ArticulationRootAPI:
    pass


class _FixedJoint:
    pass


class _RevoluteJoint:
    pass


class _RigidBodyAPI:
    pass


class _MassAPI:
    pass


USD_PHYSICS = SimpleNamespace(
    ArticulationRootAPI=_ArticulationRootAPI,
    FixedJoint=_FixedJoint,
    RevoluteJoint=_RevoluteJoint,
    RigidBodyAPI=_RigidBodyAPI,
    MassAPI=_MassAPI,
)


class _Attribute:
    def __init__(self, value=None, valid: bool = True) -> None:
        self._value = value
        self._valid = valid

    def IsValid(self) -> bool:
        return self._valid

    def Get(self):
        return self._value


class _Relationship:
    def __init__(self, targets=(), valid: bool = True) -> None:
        self._targets = tuple(targets)
        self._valid = valid

    def IsValid(self) -> bool:
        return self._valid

    def GetTargets(self):
        return self._targets


class _Prim:
    def __init__(
        self,
        path: str,
        *,
        schemas=(),
        prim_types=(),
        attributes=None,
        relationships=None,
        valid: bool = True,
    ) -> None:
        self.path = path
        self.schemas = set(schemas)
        self.prim_types = set(prim_types)
        self.attributes = dict(attributes or {})
        self.relationships = dict(relationships or {})
        self.valid = valid

    def IsValid(self) -> bool:
        return self.valid

    def HasAPI(self, schema) -> bool:
        return schema in self.schemas

    def IsA(self, prim_type) -> bool:
        return prim_type in self.prim_types

    def GetPath(self) -> str:
        return self.path

    def GetName(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def GetAppliedSchemas(self):
        values = []
        if _ArticulationRootAPI in self.schemas:
            values.append("PhysicsArticulationRootAPI")
        values.extend(self.attributes.get("__applied_schemas__", ()))
        return values

    def GetAttribute(self, name: str) -> _Attribute:
        return _Attribute(self.attributes.get(name), valid=name in self.attributes)

    def GetRelationship(self, name: str) -> _Relationship:
        targets = self.relationships.get(name)
        return _Relationship(targets or (), valid=targets is not None)


class _Stage:
    def __init__(self, prims) -> None:
        self.prims = {prim.path: prim for prim in prims}

    def Traverse(self):
        return tuple(self.prims.values())

    def GetPrimAtPath(self, path: str) -> _Prim:
        return self.prims.get(path, _Prim(path, valid=False))


def _profile():
    joint_names = ("cab_joint", "boom_joint", "arm_joint", "bucket_joint")
    logical_names = ("cab", "boom", "small_arm", "bucket")
    joints = tuple(
        SimpleNamespace(
            logical_name=logical_name,
            candidate_names=(joint_name,),
            candidate_paths=(f"/World/Joints/{joint_name}",),
            safety_margin_degrees=2.0,
        )
        for logical_name, joint_name in zip(logical_names, joint_names)
    )
    return SimpleNamespace(
        joints=joints,
        articulation_root_path=None,
        require_fixed_base=True,
    )


def _valid_stage(*, angular_drive: bool = False, broken_chain: bool = False) -> _Stage:
    body_paths = tuple(f"/World/B{index}" for index in range(5))
    bodies = [
        _Prim(
            path,
            schemas=(_RigidBodyAPI, _MassAPI),
            attributes={
                "physics:rigidBodyEnabled": True,
                "physics:kinematicEnabled": False,
                "physics:mass": 1.0,
                "physics:diagonalInertia": (1.0, 2.0, 3.0),
            },
        )
        for path in body_paths
    ]
    root = _Prim(
        "/World/Joints/fixed_root",
        schemas=(_ArticulationRootAPI,),
        prim_types=(_FixedJoint,),
        attributes={"physics:jointEnabled": True},
        relationships={"physics:body0": (body_paths[0],)},
    )
    joints = []
    for index, name in enumerate(("cab_joint", "boom_joint", "arm_joint", "bucket_joint")):
        parent = body_paths[index]
        if broken_chain and index == 2:
            parent = body_paths[0]
        applied = ("PhysicsDriveAPI:angular",) if angular_drive and index == 0 else ()
        joints.append(
            _Prim(
                f"/World/Joints/{name}",
                prim_types=(_RevoluteJoint,),
                attributes={
                    "physics:jointEnabled": True,
                    "physics:lowerLimit": -10.0 - index,
                    "physics:upperLimit": 20.0 + index,
                    "__applied_schemas__": applied,
                },
                relationships={
                    "physics:body0": (parent,),
                    "physics:body1": (body_paths[index + 1],),
                },
            )
        )
    return _Stage([root, *joints, *bodies])


class ArticulationStageReportTests(unittest.TestCase):
    def test_issue_and_report_are_json_safe(self) -> None:
        report = ArticulationStageReport(
            articulation_root_path="/World/Root",
            limits_degrees={"cab": (-8.0, 8.0)},
            issues=[ArticulationStageIssue("warning", "TEST", "diagnostic", "/World/Root")],
        )

        payload = report.to_dict()

        self.assertTrue(payload["passed"])
        self.assertEqual(payload["limits_degrees"]["cab"], [-8.0, 8.0])
        self.assertIn('"TEST"', json.dumps(payload))
        self.assertIs(report, report.require_valid())

    def test_require_valid_includes_all_error_codes(self) -> None:
        report = ArticulationStageReport()
        report.add("error", "FIRST", "first problem")
        report.add("warning", "NOTE", "not blocking")
        report.add("error", "SECOND", "second problem", "/World/Broken")

        with self.assertRaisesRegex(RuntimeError, "(?s)FIRST.*SECOND"):
            report.require_valid()

    def test_invalid_issue_severity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "severity"):
            ArticulationStageIssue("fatal", "BAD", "bad severity")


class ArticulationStageValidationTests(unittest.TestCase):
    def _validate(self, stage: _Stage) -> ArticulationStageReport:
        with patch("articulation_stage_validator._usd_physics", return_value=USD_PHYSICS):
            return validate_articulation_stage(stage, _profile())

    def test_valid_stage_discovers_complete_contract(self) -> None:
        report = self._validate(_valid_stage())

        self.assertTrue(report.ok, [issue.format() for issue in report.issues])
        self.assertEqual(report.articulation_root_path, "/World/Joints/fixed_root")
        self.assertEqual(report.root_body_path, "/World/B0")
        self.assertEqual(tuple(report.joint_paths), ("cab", "boom", "small_arm", "bucket"))
        self.assertEqual(report.dof_names["small_arm"], "arm_joint")
        self.assertEqual(report.body_paths, tuple(f"/World/B{index}" for index in range(5)))
        self.assertEqual(report.limits_degrees["cab"], (-8.0, 18.0))

    def test_angular_drive_is_a_blocking_conflict(self) -> None:
        report = self._validate(_valid_stage(angular_drive=True))

        self.assertFalse(report.ok)
        self.assertIn("DRIVE_CONFLICT", {issue.code for issue in report.errors})

    def test_broken_parent_child_order_is_rejected(self) -> None:
        report = self._validate(_valid_stage(broken_chain=True))

        self.assertFalse(report.ok)
        self.assertIn("BROKEN_CHAIN", {issue.code for issue in report.errors})

    def test_missing_stage_does_not_import_pxr(self) -> None:
        report = validate_articulation_stage(None, _profile())

        self.assertEqual([issue.code for issue in report.errors], ["NO_STAGE"])


if __name__ == "__main__":
    unittest.main()
