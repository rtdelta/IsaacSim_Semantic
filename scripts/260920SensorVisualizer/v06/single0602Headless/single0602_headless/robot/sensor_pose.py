"""Temporary mount transforms and an append-only audit, using Kit's Euler convention."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from uuid import uuid4

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

AXES = (Gf.Vec3d(1, 0, 0), Gf.Vec3d(0, 1, 0), Gf.Vec3d(0, 0, 1))


def kit_quaternion(angles):
    """Matches GfQuatEulerAttributeModel._compose in the installed Kit UI."""
    rotations = [Gf.Rotation(axis, float(angle)) for axis, angle in zip(AXES, angles)]
    return (rotations[2] * rotations[1] * rotations[0]).GetQuat()


def quaternion_values(q):
    return [float(q.GetReal()), *map(float, q.GetImaginary())]


def mount_for_sensor(prim):
    """Prefer a single-sensor asset container; never move a robot rigid body."""
    parent = prim.GetParent()
    if prim.GetName().lower() in {"sensor", "lidar", "omnilidar"}:
        if (parent and not parent.IsPseudoRoot() and UsdGeom.Xformable(parent)
                and not parent.HasAPI(UsdPhysics.RigidBodyAPI)
                and (parent.HasAuthoredPayloads() or parent.HasAuthoredReferences())):
            sensors = [p for p in Usd.PrimRange(parent) if p.GetTypeName() in ("OmniLidar","Camera")]
            if len(sensors) == 1:
                return parent
    return prim


class SensorPoses:
    def __init__(self, stage, sensors, output_directory, simulation_time):
        self.stage = stage
        self.simulation_time = simulation_time
        self.time_base='native_simulation_seconds'
        self.units = UsdGeom.GetStageMetersPerUnit(stage)
        self.entries = {}
        self.revision = 0
        self.layer = Sdf.Layer.CreateAnonymous("LidarVisualizerPoses.usda")
        self.stage.GetSessionLayer().subLayerPaths.insert(0, self.layer.identifier)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:6]
        self.directory = Path(output_directory).expanduser() / "pose_adjustments" / stamp
        self.log_path = self.directory / "pose_changes.jsonl"
        try:
            for sensor in sensors:
                prim = mount_for_sensor(stage.GetPrimAtPath(sensor["prim_path"]))
                xf = UsdGeom.Xformable(prim)
                ops = xf.GetOrderedXformOps()
                types = [op.GetOpType() for op in ops]
                allowed = {UsdGeom.XformOp.TypeTranslate, UsdGeom.XformOp.TypeOrient,
                           UsdGeom.XformOp.TypeRotateXYZ, UsdGeom.XformOp.TypeScale}
                reason = None
                matrix_only = len(types)==1 and types[0]==UsdGeom.XformOp.TypeTransform and not ops[0].GetNumTimeSamples()
                if matrix_only:
                    matrix=ops[0].Get();vectors=[Gf.Vec3d(*[matrix[i][j] for j in range(3)]) for i in range(3)]
                    matrix_only=all(v.GetLength()>1e-9 for v in vectors) and all(abs(Gf.Dot(vectors[i].GetNormalized(),vectors[j].GetNormalized()))<1e-6 for i in range(3) for j in range(i)) and matrix.GetDeterminant()>0
                if prim.IsInstanceProxy() or prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    reason = "The mount is an instance proxy or physics body. Edit its asset mounting Xform instead."
                elif not matrix_only and (any(t not in allowed for t in types) or len(types) != len(set(types))
                      or any(op.IsInverseOp() or op.GetNumTimeSamples() for op in ops)
                      or (UsdGeom.XformOp.TypeOrient in types and UsdGeom.XformOp.TypeRotateXYZ in types)):
                    reason = "Animated/complex transform stack: this editor supports translate, orient/rotateXYZ, scale."
                elif not matrix_only and types != sorted(types, key=lambda t: {UsdGeom.XformOp.TypeTranslate: 0,
                          UsdGeom.XformOp.TypeOrient: 1, UsdGeom.XformOp.TypeRotateXYZ: 1,
                          UsdGeom.XformOp.TypeScale: 2}.get(t, 3)):
                    reason = "Nonstandard transform order; the original stack is preserved."
                parent = prim.GetParent()
                world = parent.IsPseudoRoot() or xf.GetResetXformStack()
                entry = dict(sensor, mount_path=str(prim.GetPath()),
                             parent_path=str(parent.GetPath()), reference="world" if world else str(parent.GetPath()),
                             reason=reason, rotation_op="xformOp:orient")
                for op in ops:
                    if op.GetOpType() in (UsdGeom.XformOp.TypeOrient, UsdGeom.XformOp.TypeRotateXYZ):
                        entry["rotation_op"] = op.GetName()
                if matrix_only:entry['rotation_op']=ops[0].GetName()
                self.entries[sensor["id"]] = entry
                binding=sensor.get('binding',{})
                if binding.get('category')=='robot_root':
                    anchor=stage.GetPrimAtPath(binding['motion_anchor'])
                    cache=UsdGeom.XformCache()
                    entry['virtual_anchor']=binding['motion_anchor']
                    entry['reference']=binding['motion_anchor']
                    entry['virtual_transform']=cache.GetLocalToWorldTransform(prim)*cache.GetLocalToWorldTransform(anchor).GetInverse()
                    if prim.IsInstanceProxy():entry['reason']='Instance proxy cannot follow a virtual root mount'
                entry["initial"] = self.read(sensor["id"])
            self.update_virtual_mounts()
            self.log("session_started", poses=self.snapshot())
        except Exception:
            self.close()
            raise

    def read(self, sid):
        entry = self.entries[sid]
        prim = self.stage.GetPrimAtPath(entry["mount_path"])
        matrix=entry.get('virtual_transform')
        if matrix is None:matrix=UsdGeom.Xformable(prim).GetLocalTransformation()
        transform=Gf.Transform(matrix)
        q=transform.GetRotation().GetQuat()
        angles=list(map(float,Gf.Rotation(q).Decompose(*AXES)))
        return {"position_m":list(transform.GetTranslation()*self.units),"rotation_deg":angles,
                "quaternion_wxyz":quaternion_values(q)}

    def update_virtual_mounts(self):
        cache=UsdGeom.XformCache()
        with Usd.EditContext(self.stage,self.layer):
            for entry in self.entries.values():
                if 'virtual_anchor' not in entry or entry['reason']:continue
                prim=self.stage.GetPrimAtPath(entry['mount_path']);xf=UsdGeom.Xformable(prim)
                world=entry['virtual_transform']*cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(entry['virtual_anchor']))
                local=world if xf.GetResetXformStack() else world*cache.GetLocalToWorldTransform(prim.GetParent()).GetInverse()
                op=entry.get('virtual_op')
                if op is None:
                    op=xf.AddTransformOp(opSuffix='single0602_root_mount')
                    xf.SetXformOpOrder([op],xf.GetResetXformStack());entry['virtual_op']=op
                op.Set(local)

    def snapshot(self):
        return [{**{k: e[k] for k in ("id", "prim_path", "mount_path", "parent_path", "reference", "rotation_op")},
                 "editable": e["reason"] is None, **self.read(sid)} for sid, e in self.entries.items()]

    def log(self, event, **details):
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {"event": event, "utc": datetime.now(timezone.utc).isoformat(),
                  "simulation_time_s": float(self.simulation_time()), "time_base":self.time_base,"revision": self.revision,
                  "stage": self.stage.GetRootLayer().identifier, **details}
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    def apply(self, sid, position, angles, recording=None):
        entry = self.entries[sid]
        if entry["reason"]:
            raise ValueError(entry["reason"])
        if len(position) != 3 or len(angles) != 3 or not all(math.isfinite(float(v)) for v in [*position, *angles]):
            raise ValueError("Position and rotation require three finite numbers each.")
        old = self.read(sid)
        if max(abs(float(a) - b) for a, b in zip([*position, *angles], old["position_m"] + old["rotation_deg"])) < 1e-7:
            return False
        # Check audit writability before modifying the stage. Log both intent and result.
        self.log("adjust_requested", sensor=sid, before=old,
                 requested={"position_m": list(position), "rotation_deg": list(angles)}, recording=recording)
        prim = self.stage.GetPrimAtPath(entry["mount_path"])
        xf = UsdGeom.Xformable(prim)
        if 'virtual_anchor' in entry:
            value=Gf.Transform(entry['virtual_transform'])
            value.SetTranslation(Gf.Vec3d(*[float(v)/self.units for v in position]))
            value.SetRotation(Gf.Rotation(kit_quaternion(angles)))
            entry['virtual_transform']=value.GetMatrix();self.update_virtual_mounts();self.revision+=1
            self.log('adjusted',sensor=sid,before=old,after=self.read(sid),recording=recording)
            return True
        with Usd.EditContext(self.stage, self.layer):
            ops = xf.GetOrderedXformOps()
            if len(ops)==1 and ops[0].GetOpType()==UsdGeom.XformOp.TypeTransform:
                transform=Gf.Transform(ops[0].Get());transform.SetTranslation(Gf.Vec3d(*[float(v)/self.units for v in position]))
                transform.SetRotation(Gf.Rotation(kit_quaternion(angles)));ops[0].Set(transform.GetMatrix())
                self.revision+=1
                self.log('adjusted',sensor=sid,mount_path=entry['mount_path'],reference=entry['reference'],
                         before=old,after=self.read(sid),recording=recording)
                return True
            translate = next((op for op in ops if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), None)
            rotation = next((op for op in ops if op.GetOpType() in
                            (UsdGeom.XformOp.TypeOrient, UsdGeom.XformOp.TypeRotateXYZ)), None)
            scale = next((op for op in ops if op.GetOpType() == UsdGeom.XformOp.TypeScale), None)
            if translate is None:
                translate = xf.AddTranslateOp()
            if rotation is None:
                rotation = xf.AddOrientOp()
            xf.SetXformOpOrder([translate, rotation] + ([scale] if scale else []), xf.GetResetXformStack())
            vector = Gf.Vec3d if translate.GetPrecision() == UsdGeom.XformOp.PrecisionDouble else Gf.Vec3f
            translate.Set(vector(*[float(v) / self.units for v in position]))
            if rotation.GetOpType() == UsdGeom.XformOp.TypeOrient:
                quat_type = Gf.Quatd if rotation.GetPrecision() == UsdGeom.XformOp.PrecisionDouble else Gf.Quatf
                rotation.Set(quat_type(kit_quaternion(angles)))
            else:
                vector = Gf.Vec3d if rotation.GetPrecision() == UsdGeom.XformOp.PrecisionDouble else Gf.Vec3f
                rotation.Set(vector(*map(float, angles)))
        self.revision += 1
        self.log("adjusted", sensor=sid, mount_path=entry["mount_path"], reference=entry["reference"],
                 before=old, after=self.read(sid), recording=recording)
        return True

    def reset(self, reason):
        changed = [sid for sid, e in self.entries.items() if self.read(sid) != e["initial"]]
        if not changed:
            return
        before = self.snapshot()
        self.layer.Clear()
        for entry in self.entries.values():
            if 'virtual_anchor' in entry:
                entry.pop('virtual_op',None)
                initial=entry['initial'];value=Gf.Transform(entry['virtual_transform'])
                value.SetTranslation(Gf.Vec3d(*[float(v)/self.units for v in initial['position_m']]))
                value.SetRotation(Gf.Rotation(kit_quaternion(initial['rotation_deg'])))
                entry['virtual_transform']=value.GetMatrix()
        self.update_virtual_mounts()
        self.revision += 1
        self.log("reset", reason=reason, before=before, after=self.snapshot())

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.directory / ("poses_" + stamp + ".json")
        document = {"schema_version": 1, "utc": datetime.now(timezone.utc).isoformat(),
                    "simulation_time_s": float(self.simulation_time()), "time_base":self.time_base,"revision": self.revision,
                    "stage": self.stage.GetRootLayer().identifier, "position_units": "meters",
                    "rotation_convention": "Isaac property panel; orient uses GfQuatEulerAttributeModel",
                    "quaternion_order": "wxyz", "poses": self.snapshot()}
        with path.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        self.log("snapshot_saved", path=str(path))
        return path

    def close(self):
        session = self.stage.GetSessionLayer()
        if self.layer.identifier in session.subLayerPaths:
            session.subLayerPaths.remove(self.layer.identifier)
