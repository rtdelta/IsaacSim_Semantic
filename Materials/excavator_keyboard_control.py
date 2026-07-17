from pxr import Gf, Sdf, UsdPhysics, PhysxSchema
import omni.usd
import omni.timeline
import omni.physx
import omni.appwindow
import carb


stage = omni.usd.get_context().get_stage()

BODY_PATHS = {
    "track": Sdf.Path("/root/Xform/track_mesh"),
    "cab": Sdf.Path("/root/Xform/operator_cab_mesh"),
    "boom": Sdf.Path("/root/Xform/boom_mesh"),
    "small_arm": Sdf.Path("/root/Xform/small_arm_mesh"),
    "bucket": Sdf.Path("/root/Xform/bucket_only_full_teeth_mesh"),
}

JOINTS = {
    "track_operator_cab_joint": {
        "path": Sdf.Path("/World/Joints/track_operator_cab_joint"),
        "pos": "KEY_1",
        "neg": "KEY_2",
        "lower": -180.0,
        "upper": 180.0,
        "speed": 8.0,
    },
    "platform_boom_joint": {
        "path": Sdf.Path("/World/Joints/platform_boom_joint"),
        "pos": "KEY_3",
        "neg": "KEY_4",
        "lower": -35.0,
        "upper": 70.0,
        "speed": 5.0,
    },
    "boom_small_arm_joint": {
        "path": Sdf.Path("/World/Joints/boom_small_arm_joint"),
        "pos": "KEY_5",
        "neg": "KEY_6",
        "lower": -80.0,
        "upper": 70.0,
        "speed": 5.0,
    },
    "small_arm_bucket_joint": {
        "path": Sdf.Path("/World/Joints/small_arm_bucket_joint"),
        "pos": "KEY_7",
        "neg": "KEY_8",
        "lower": -90.0,
        "upper": 80.0,
        "speed": 5.0,
    },
}

RESET_KEY = "KEY_0"

STIFFNESS = 500000.0
DAMPING = 220000.0
MAX_FORCE = 120000000.0


def get_prim(path):
    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid():
        raise RuntimeError(f"找不到 Prim: {path}")
    return prim


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def setup_body(path, kinematic=False, disable_gravity=True):
    prim = get_prim(path)

    rb = UsdPhysics.RigidBodyAPI.Apply(prim)
    rb.CreateRigidBodyEnabledAttr().Set(True)
    rb.CreateKinematicEnabledAttr().Set(bool(kinematic))
    rb.CreateVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    rb.CreateAngularVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))

    physx_rb = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    physx_rb.CreateDisableGravityAttr().Set(bool(disable_gravity))


def setup_joint(cfg):
    prim = get_prim(cfg["path"])
    joint = UsdPhysics.RevoluteJoint(prim)

    joint.CreateLowerLimitAttr().Set(float(cfg["lower"]))
    joint.CreateUpperLimitAttr().Set(float(cfg["upper"]))
    joint.CreateCollisionEnabledAttr().Set(False)

    drive = UsdPhysics.DriveAPI.Apply(prim, "angular")
    drive.CreateTypeAttr().Set("force")
    drive.CreateTargetPositionAttr().Set(0.0)
    drive.CreateTargetVelocityAttr().Set(0.0)
    drive.CreateStiffnessAttr().Set(STIFFNESS)
    drive.CreateDampingAttr().Set(DAMPING)
    drive.CreateMaxForceAttr().Set(MAX_FORCE)

    return drive


def key_name(event):
    return str(event.input).split(".")[-1].upper()


def main():
    timeline = omni.timeline.get_timeline_interface()
    timeline.pause()

    setup_body(BODY_PATHS["track"], kinematic=True, disable_gravity=True)
    setup_body(BODY_PATHS["cab"], kinematic=False, disable_gravity=True)
    setup_body(BODY_PATHS["boom"], kinematic=False, disable_gravity=True)
    setup_body(BODY_PATHS["small_arm"], kinematic=False, disable_gravity=True)
    setup_body(BODY_PATHS["bucket"], kinematic=False, disable_gravity=True)

    app_window = omni.appwindow.get_default_app_window()
    keyboard = app_window.get_keyboard()
    input_iface = carb.input.acquire_input_interface()
    physx = omni.physx.get_physx_interface()

    old_k = globals().get("_excavator_keyboard_sub")
    if old_k is not None:
        input_iface.unsubscribe_to_keyboard_events(keyboard, old_k)

    old_p = globals().get("_excavator_physics_sub")
    if old_p is not None:
        old_p.unsubscribe()

    state = {
        "pressed": set(),
        "targets": {},
        "initial_targets": {},
        "drives": {},
    }

    for name, cfg in JOINTS.items():
        state["targets"][name] = 0.0
        state["initial_targets"][name] = 0.0
        state["drives"][name] = setup_joint(cfg)
        print("joint ready:", name, cfg["path"])

    def hard_hold_all():
        for name, drive in state["drives"].items():
            target = state["targets"][name]
            drive.GetTargetPositionAttr().Set(float(target))
            drive.GetTargetVelocityAttr().Set(0.0)

        # Clear velocities on key release or idle so joints do not coast.
        for path in BODY_PATHS.values():
            prim = get_prim(path)
            rb = UsdPhysics.RigidBodyAPI.Apply(prim)
            rb.GetVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
            rb.GetAngularVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))

    def on_key(event):
        k = key_name(event)

        if event.type == carb.input.KeyboardEventType.KEY_PRESS:
            state["pressed"].add(k)

            if k == RESET_KEY:
                for name in state["targets"]:
                    state["targets"][name] = state["initial_targets"][name]
                hard_hold_all()
                print("Reset all joint targets")

        elif event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            state["pressed"].discard(k)
            hard_hold_all()

        return True

    def on_step(dt):
        active = False

        for name, cfg in JOINTS.items():
            direction = 0.0

            if cfg["pos"] in state["pressed"]:
                direction += 1.0
            if cfg["neg"] in state["pressed"]:
                direction -= 1.0

            if direction != 0.0:
                active = True
                target = state["targets"][name]
                target += direction * cfg["speed"] * dt
                target = clamp(target, cfg["lower"], cfg["upper"])
                state["targets"][name] = target

            drive = state["drives"][name]
            drive.GetTargetPositionAttr().Set(float(state["targets"][name]))
            drive.GetTargetVelocityAttr().Set(0.0)

        if not active:
            hard_hold_all()

    state["keyboard_sub"] = input_iface.subscribe_to_keyboard_events(keyboard, on_key)
    state["physics_sub"] = physx.subscribe_physics_step_events(on_step)

    globals()["_excavator_keyboard_sub"] = state["keyboard_sub"]
    globals()["_excavator_physics_sub"] = state["physics_sub"]

    hard_hold_all()

    print("\nKeyboard control enabled")
    print("1/2: track_operator_cab_joint")
    print("3/4: platform_boom_joint")
    print("5/6: boom_small_arm_joint")
    print("7/8: small_arm_bucket_joint")
    print("0: reset")
    print("Release key: hard hold current joint targets")

    timeline.play()


main()
