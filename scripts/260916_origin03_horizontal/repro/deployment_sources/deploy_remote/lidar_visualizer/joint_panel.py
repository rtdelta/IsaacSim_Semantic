"""Joint UI drafts and explicit commands; ArticulationMotion owns state writes."""
import omni.ui as ui
from .joint_control import MODES


class JointPanel:
    def __init__(self, runtime):
        self.runtime = runtime
        self.rows = {}
        self.bound_controller = None
        self.syncing = False
        ui.Label("Actual joint angles: deg | Speed: deg/s | Edit fields, then Apply or Start", height=20)
        self.info = ui.Label("Press Play Simulation once to initialize. Joints start in Hold.", height=20)
        for joint in runtime.config["robot_motion"]["joints"]:
            name = joint["name"]
            with ui.VStack(height=0, spacing=3):
                row = {"readout": ui.Label(name + " | waiting", height=20)}
                with ui.HStack(height=27, spacing=4) as controls:
                    row["mode"] = ui.ComboBox(0, "Direct set", "Target + speed", "Periodic", width=145)
                    row["mode"].model.add_item_changed_fn(lambda _m, _i, n=name: self.select_mode(n))
                    ui.Label("Target", width=42)
                    row["target"] = ui.SimpleFloatModel(0)
                    row["target_field"] = ui.FloatField(model=row["target"], width=90)
                    ui.Label("Speed", width=42)
                    row["speed"] = ui.SimpleFloatModel(joint.get("speed_deg_s", 5.0))
                    row["speed_field"] = ui.FloatField(model=row["speed"], width=90)
                    row["go"] = ui.Button("Apply", clicked_fn=lambda n=name: self.execute(n))
                    ui.Button("Hold", clicked_fn=lambda n=name: self.hold(n), width=70)
                row["controls"] = controls
                with ui.HStack(height=25, spacing=4) as bounds:
                    ui.Label("Periodic limits:", width=145)
                    ui.Label("Lower", width=42)
                    row["lower"] = ui.SimpleFloatModel(-15)
                    ui.FloatField(model=row["lower"], width=90)
                    ui.Label("Upper", width=42)
                    row["upper"] = ui.SimpleFloatModel(15)
                    ui.FloatField(model=row["upper"], width=90)
                    row["limits"] = ui.Label("Articulation limits: waiting")
                row["bounds"] = bounds
            self.rows[name] = row
        self.fixed = ui.Label("Cab-track: fixed at startup angle (read only)", height=20)
        with ui.HStack(height=28, spacing=6):
            self.start_all = ui.Button("Start All", clicked_fn=self.execute_all,
                tooltip="Starts Target + speed and Periodic rows. Direct set rows require their own Apply.")
            self.hold_all = ui.Button("Hold All", clicked_fn=self.hold,
                tooltip="Holds all controlled joints. Root forward motion continues until Pause Simulation.")
        ui.Label("Start All uses Target/Periodic rows. Hold stops joints; Pause stops the whole simulation.", height=20)
        self.refresh()

    def _available(self):
        r = self.runtime
        return (not r.closed and not r.closing and r.pose_state == "idle"
                and not (r.pose_task and not r.pose_task.done())
                and not r.timeline.is_stopped() and r.motion is not None and r.motion.ready)

    def _run(self, callback):
        try:
            if not self._available():
                raise RuntimeError("Joint controls require Play/Pause and no active LiDAR adjustment")
            callback()
        except Exception as exc:
            self.runtime.set_status(str(exc))
        self.refresh()

    def mode(self, name):
        return MODES[self.rows[name]["mode"].model.get_item_value_model().as_int]

    def select_mode(self, name):
        if not self.syncing:
            self._run(lambda: self.runtime.motion.command("mode", name=name, mode=self.mode(name)))

    def draft(self, name):
        row = self.rows[name]
        return dict(mode=self.mode(name), **{key: row[key].as_float for key in ("target", "speed", "lower", "upper")})

    def execute(self, name):
        def apply():
            self.runtime.motion.command("execute", commands={name: self.draft(name)})
            suffix = " (paused; Play resumes motion)" if not self.runtime.timeline.is_playing() and self.mode(name) != "direct" else ""
            self.runtime.set_status(f"{name}: {self.mode(name)} command accepted" + suffix)
        self._run(apply)

    def execute_all(self):
        def apply():
            commands = {name: self.draft(name) for name in self.rows if self.mode(name) != "direct"}
            if not commands:
                raise ValueError("Choose Target + speed or Periodic first. Direct set uses each row's Apply.")
            self.runtime.motion.command("execute", commands=commands)
            self.runtime.set_status("Start All accepted" + (" (paused; Play resumes motion)" if not self.runtime.timeline.is_playing() else ""))
        self._run(apply)

    def hold(self, name=None):
        self._run(lambda: self.runtime.motion.command("hold", name=name))

    def refresh(self):
        r = self.runtime
        motion = r.motion
        ready = bool(motion and motion.ready)
        available = self._available()
        if ready and self.bound_controller is not motion.controller:
            self.syncing = True
            for name, row in self.rows.items():
                state = motion.controller.states[name]
                for key in ("target", "speed", "lower", "upper"):
                    row[key].set_value(getattr(state, key))
                row["mode"].model.get_item_value_model().set_value(MODES.index(state.mode))
                row["limits"].text = f"Allowed: [{state.minimum:.1f}, {state.maximum:.1f}] deg"
            self.bound_controller = motion.controller
            self.syncing = False
        if ready:
            actual = motion.actual_degrees()
            for name, row in self.rows.items():
                state = motion.controller.states[name]
                status = "Running" if state.running and r.timeline.is_playing() else ("Paused / armed" if state.running else "Hold")
                row["readout"].text = f"{name} | Actual: {actual[name]:.2f} deg | {status}"
            fixed_deg = float(motion.articulation.get_dof_positions().numpy()[0][motion.fixed_index]) * 180.0 / 3.141592653589793
            self.fixed.text = f"{r.config['robot_motion']['fixed_joint']} | Actual: {fixed_deg:.2f} deg | Locked"
            self.info.text = "Switching mode holds that joint. Stop restores startup pose and clears motion."
        else:
            self.info.text = "Joint controls unavailable. Press Play to initialize." if not (motion and motion.failed) else "Joint controller failed; see status below."
            for name, row in self.rows.items():
                row["readout"].text = name + " | waiting for Play"
        for name, row in self.rows.items():
            mode = self.mode(name)
            row["controls"].enabled = available
            row["bounds"].enabled = available and mode == "periodic"
            row["target_field"].enabled = mode != "periodic"
            row["speed_field"].enabled = mode != "direct"
            row["go"].text = "Apply" if mode == "direct" else "Start"
        self.start_all.enabled = self.hold_all.enabled = available
