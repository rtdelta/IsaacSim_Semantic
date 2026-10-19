"""Scripted articulation state updates, ordered before TF and RTX publication."""
import uuid
import numpy as np
import omni.physx
from isaacsim.core.experimental.prims import Articulation
from isaacsim.core.simulation_manager import SimulationManager
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics

from .motion_profile import validate_motion
from .joint_control import JointController
from .reference_frames import HorizontalFrame
from .base_control import BaseController
from .performance import timed

FRAME_PATH = "/SensorVisualizerV05Frames"
_instances = {}


def graph_tick(key, simulation_time):
    instance = _instances.get(key)
    return instance.tick(simulation_time) if instance else False


class ArticulationMotion:
    def __init__(self, stage, layer, config, on_error):
        validate_motion(config)
        self.stage, self.layer, self.config, self.on_error = stage, layer, config, on_error
        self.key = uuid.uuid4().hex
        self.articulation = None
        self.initial_position = self.initial_orientation = self.initial_angles = None
        self.epoch = None
        self.last_time = None
        self.elapsed = 0.0
        self.failed = False
        self.saved_xforms = []
        self.reference_path = FRAME_PATH + '/' + config.get('reference_frame', 'swing_coordinate')
        self.horizontal_path = FRAME_PATH + '/' + config.get('horizontal_frame', 'swing_horizontal_coordinate')
        self.horizontal = HorizontalFrame()
        self.frame_snapshot = None
        self.initialized_count = 0
        self.controller = None
        self.mode = config.get('control_mode', 'scripted')
        self.last_snapshot = None
        self.base_controller = None
        self.frame_observer = None

    def prepare(self):
        robot = self.stage.GetPrimAtPath(self.config["robot_prim"])
        root = self.stage.GetPrimAtPath(self.config["articulation_root"])
        if not robot or not root or not root.HasAPI(UsdPhysics.ArticulationRootAPI):
            raise ValueError("Configured robot/articulation root is missing or has no ArticulationRootAPI")
        if self.stage.GetPrimAtPath(FRAME_PATH):
            raise ValueError(f"{FRAME_PATH} already exists outside this instance")
        units = UsdGeom.GetStageMetersPerUnit(self.stage)
        if abs(units - 1.0) > 1e-9:
            raise ValueError("This motion configuration requires a stage with metersPerUnit=1")
        self.initial_reference = UsdGeom.Xformable(robot).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        base = self.stage.GetPrimAtPath(self.config.get('base_body', self.config['articulation_root']))
        base_world = UsdGeom.Xformable(base).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        self.reference_in_root = self.initial_reference * base_world.GetInverse()
        for prim in (Usd.PrimRange(robot) if self.mode == 'scripted' else []):
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                self.saved_xforms.append((prim.GetPath(), [(op.GetAttr().GetName(), op.GetAttr().Get())
                    for op in UsdGeom.Xformable(prim).GetOrderedXformOps()]))
                PhysxSchema.PhysxRigidBodyAPI.Apply(prim).CreateDisableGravityAttr().Set(True)
            # Motion is prescribed, not driven by contact forces.
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr().Set(False)
            if prim.IsA(UsdPhysics.RevoluteJoint) and prim.HasAPI(UsdPhysics.DriveAPI, 'angular'):
                # Script writes states directly. Suppress inherited force targets
                # in this removable layer, including the 05 folded-pose drives.
                drive = UsdPhysics.DriveAPI(prim, 'angular')
                drive.CreateStiffnessAttr().Set(0.)
                drive.CreateDampingAttr().Set(0.)
                drive.CreateMaxForceAttr().Set(0.)
        for prim in (self.stage.Traverse() if self.mode == 'scripted' else []):
            if prim.IsA(UsdPhysics.FixedJoint):
                joint = UsdPhysics.Joint(prim)
                a, b = joint.GetBody0Rel().GetTargets(), joint.GetBody1Rel().GetTargets()
                if (not a and b == [base.GetPath()]) or (not b and a == [base.GetPath()]):
                    joint.CreateJointEnabledAttr().Set(False)
        UsdGeom.Xform.Define(self.stage, FRAME_PATH)
        self.reference_op = UsdGeom.Xform.Define(self.stage, self.reference_path).AddTransformOp()
        self.horizontal_op = UsdGeom.Xform.Define(self.stage, self.horizontal_path).AddTransformOp()
        self._update_reference(self.initial_reference)
        self.articulation = Articulation(self.config["articulation_root"], reset_xform_op_properties=False)
        _instances[self.key] = self

    def script(self):
        return ("import omni.graph.core as og\n"
                "from sensor_visualizer_v05.robot.articulation_motion import graph_tick\n"
                "def compute(db):\n"
                f"    ready = graph_tick({self.key!r}, db.inputs.simulationTime)\n"
                "    db.outputs.execOut = og.ExecutionAttributeState.ENABLED if ready else og.ExecutionAttributeState.DISABLED\n"
                "    return True\n")

    def _capture_initial_state(self, simulation_time):
        art = self.articulation
        names = [j["name"] for j in self.config["joints"]]
        self.joint_indices = art.get_dof_indices(names).numpy().astype(int).ravel().tolist()
        self.fixed_index = int(art.get_dof_indices(self.config["fixed_joint"]).numpy().ravel()[0])
        positions, orientations = art.get_world_poses()
        if self.initial_position is None:
            self.initial_position = positions.numpy()[0].astype(np.float64).copy()
            self.initial_orientation = orientations.numpy()[0].astype(np.float64).copy()
            self.initial_angles = art.get_dof_positions().numpy()[0].astype(np.float64).copy()
            # Gf uses row vectors: reference_world = reference_in_root * root_world.
            direction = self.initial_reference.TransformDir(Gf.Vec3d(1, 0, 0))
            self.forward = np.array(direction) / np.linalg.norm(direction)
            q = self.initial_reference.ExtractRotationQuat().GetNormalized()
            heading = np.arctan2(direction[1], direction[0])
            self.base_controller = BaseController(self.initial_reference.ExtractTranslation(),
                [q.GetReal(), *q.GetImaginary()], heading)
        if self.controller is None and self.mode == 'scripted':
            lower, upper = art.get_dof_limits()
            lower, upper = np.rad2deg(lower.numpy()[0].astype(np.float64)), np.rad2deg(upper.numpy()[0].astype(np.float64))
            self.controller = JointController(
                {name: float(np.rad2deg(self.initial_angles[i])) for name, i in zip(names, self.joint_indices)},
                {name: (float(lower[i]), float(upper[i])) for name, i in zip(names, self.joint_indices)},
                {j["name"]: j.get("speed_deg_s", 5.0) for j in self.config["joints"]})
        self.epoch = float(simulation_time)
        self.initialized_count += 1

    @property
    def ready(self):
        return (not self.failed and self.initial_angles is not None and self.epoch is not None
                and self.articulation is not None and self.articulation.is_physics_tensor_entity_valid())

    def actual_degrees(self):
        angles = np.rad2deg(self.articulation.get_dof_positions().numpy()[0])
        return {j["name"]: float(angles[i]) for j, i in zip(self.config["joints"], self.joint_indices)}

    def _command_angles(self):
        angles = self.initial_angles.copy()
        for joint, index in zip(self.config["joints"], self.joint_indices):
            angles[index] = np.deg2rad(self.controller.states[joint["name"]].angle)
        return angles

    def command(self, action, *, commands=None, name=None, mode=None):
        if self.mode != 'scripted':
            raise RuntimeError('Observe mode does not command the robot')
        if not self.ready:
            raise RuntimeError("Press Play Simulation once to initialize joint controls")
        actual = self.actual_degrees()
        if action == "execute":
            self.controller.execute(commands, actual)
        elif action == "mode":
            self.controller.select_mode(name, mode, actual)
        elif action == "hold":
            self.controller.hold([name] if name else list(actual), actual)
        else:
            raise ValueError(f"Unknown joint action: {action}")
        # Direct Apply also works while paused. Root translation is not advanced here.
        try:
            positions, orientations = self.articulation.get_world_poses()
            self._apply(positions.numpy()[0], self._command_angles(), orientations.numpy()[0])
        except Exception as exc:
            self.failed = True
            self.on_error(f"Joint command failed: {exc}")
            raise

    @staticmethod
    def _root_matrix(position, orientation):
        w, x, y, z = [float(v) for v in orientation]
        result = Gf.Matrix4d(1).SetRotate(Gf.Quatd(w, Gf.Vec3d(x, y, z)))
        result.SetTranslateOnly(Gf.Vec3d(*[float(v) for v in position]))
        return result

    def _update_reference(self, reference):
        q = reference.ExtractRotationQuat().GetNormalized()
        xyzw = [*q.GetImaginary(), q.GetReal()]
        row = self.horizontal.update(reference.ExtractTranslation(), xyzw)
        row['root_xyzw'] = list(map(float, xyzw))
        self.frame_snapshot = row
        x, y, z, w = row['xyzw']
        horizontal = self._root_matrix(row['position'], [w, x, y, z])
        with Usd.EditContext(self.stage, self.layer):
            self.reference_op.Set(reference)
            self.horizontal_op.Set(horizontal)

    def command_base(self, action, **values):
        if self.mode != 'scripted' or not self.ready:
            raise RuntimeError('Base controls require Scripted mode and Play/Pause')
        controller = self.base_controller
        if action == 'direct':
            controller.direct(values['x'], values['y'], values['yaw_deg'])
        elif action == 'velocity':
            controller.velocity(values['speed'], values['yaw_rate_deg'])
        elif action == 'height':
            controller.height(values['z'])
        elif action == 'hold':
            controller.hold()
        elif action == 'reset':
            controller.reset()
        else:
            raise ValueError('Unknown base command: '+action)
        self._apply_controlled_base(self._command_angles())

    def command_tilt(self, action, **values):
        if self.mode != 'scripted' or not self.ready:
            raise RuntimeError('Tilt controls require Scripted mode and Play/Pause')
        self.base_controller.command_tilt(action, **values)
        self._apply_controlled_base(self._command_angles())

    def _apply_controlled_base(self, angles):
        controller = self.base_controller
        reference = self._root_matrix(controller.position, controller.orientation)
        root = self.reference_in_root.GetInverse() * reference
        q = root.ExtractRotationQuat().GetNormalized()
        self._apply(root.ExtractTranslation(), angles, [q.GetReal(), *q.GetImaginary()])

    def _apply(self, position, angles, orientation=None):
        art = self.articulation
        art.set_world_poses(positions=[position], orientations=[
            self.initial_orientation if orientation is None else orientation])
        art.set_dof_positions([angles])
        art.set_dof_velocities(np.zeros((1, art.num_dofs), dtype=np.float32))
        art.set_velocities(linear_velocities=[[0, 0, 0]], angular_velocities=[[0, 0, 0]])
        view = SimulationManager.get_physics_simulation_view()
        view.update_articulations_kinematic()
        # Materialize the backend's link poses before downstream USD/Fabric TF reads.
        omni.physx.get_physx_interface().update_transformations(False, True, False, False)
        positions, orientations = art.get_world_poses()
        reference = self.reference_in_root * self._root_matrix(positions.numpy()[0], orientations.numpy()[0])
        self._update_reference(reference)

    def snapshot(self, simulation_time):
        names = [self.config['fixed_joint']] + [j['name'] for j in self.config['joints']]
        indices = [self.fixed_index] + self.joint_indices
        angles = self.articulation.get_dof_positions().numpy()[0]
        positions, orientations = self.articulation.get_world_poses()
        reference = self.reference_in_root * self._root_matrix(positions.numpy()[0], orientations.numpy()[0])
        self._update_reference(reference)
        q = reference.ExtractRotationQuat().GetNormalized()
        self.last_snapshot = {'time': float(simulation_time), 'names': names,
            'positions': [float(angles[i]) for i in indices],
            'root_position': list(reference.ExtractTranslation()),
            'root_xyzw': [*list(q.GetImaginary()), float(q.GetReal())],
            'horizontal': dict(self.frame_snapshot)}
        if self.mode == 'scripted' and self.base_controller:
            self.last_snapshot['base_control'] = self.base_controller.snapshot()
        return self.last_snapshot

    @timed('motion.tick')
    def tick(self, simulation_time):
        if self.failed or self.articulation is None:
            return False
        if not self.articulation.is_physics_tensor_entity_valid():
            return False
        try:
            if self.epoch is None:
                self._capture_initial_state(simulation_time)
            if self.last_time is not None and simulation_time < self.last_time - 1e-6:
                self.horizontal.reset()
                self.epoch = float(simulation_time)
                if self.controller:
                    self.controller.reset()
                if self.base_controller:
                    self.base_controller.reset()
                self.last_time = None
            self.elapsed = max(0.0, float(simulation_time) - self.epoch)
            dt = max(0.0, float(simulation_time) - self.last_time) if self.last_time is not None else 0.0
            if self.mode == 'scripted':
                self.controller.step(dt)
                self.base_controller.step(dt)
                self._apply_controlled_base(self._command_angles())
            self.snapshot(simulation_time)
            if self.frame_observer:
                self.frame_observer(self.last_snapshot)
            self.last_time = float(simulation_time)
            return True
        except Exception as exc:
            self.failed = True
            self.on_error(f"Robot motion stopped: {exc}")
            return False

    def reset(self):
        self.horizontal.reset()
        if self.controller:
            self.controller.reset()
        if self.base_controller:
            self.base_controller.reset()
        if self.mode == 'scripted' and self.initial_angles is not None and self.articulation.is_physics_tensor_entity_valid():
            self._apply(self.initial_position, self.initial_angles)
        with Usd.EditContext(self.stage, self.layer):
            for path, attributes in self.saved_xforms:
                prim = self.stage.GetPrimAtPath(path)
                if prim:
                    for name, value in attributes:
                        if value is not None:
                            prim.GetAttribute(name).Set(value)
            self._update_reference(self.initial_reference)
        self.last_snapshot = None
        self.epoch = self.last_time = None
        self.elapsed = 0.0

    def close(self, restore=True):
        _instances.pop(self.key, None)
        if restore:
            self.reset()
        self.articulation = None
