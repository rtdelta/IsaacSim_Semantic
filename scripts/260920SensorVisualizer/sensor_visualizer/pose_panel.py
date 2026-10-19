"""Small UI adapter; the runtime owns all editing/recording transitions."""
import omni.ui as ui


class PosePanel:
    def __init__(self, runtime):
        self.runtime = runtime
        self.models = {}
        self.rows = {}
        with ui.HStack(height=30, spacing=6):
            self.enter = ui.Button("Adjust LiDAR", clicked_fn=runtime.request_begin_adjustment)
            self.finish = ui.Button("Done / Resume", clicked_fn=runtime.request_finish_adjustment)
            self.save = ui.Button("Save Current Poses", clicked_fn=runtime.request_save_poses)
        ui.Label("Position: meters | Rotation X/Y/Z: degrees (Isaac convention)", height=20)
        with ui.ScrollingFrame(height=225):
            with ui.VStack(spacing=8):
                if runtime.poses:
                    for sid, entry in runtime.poses.entries.items():
                        with ui.VStack(spacing=3):
                            ui.Label(sid + " | relative to " + entry["reference"], height=20,
                                     tooltip=entry["mount_path"])
                            if entry["reason"]:
                                ui.Label(entry["reason"], word_wrap=True, height=40)
                                continue
                            self.models[sid] = []
                            with ui.VStack(spacing=3) as row:
                                for title, step in (("Position", 0.01), ("Rotation", 0.2)):
                                    with ui.HStack(height=25, spacing=4):
                                        ui.Label(title, width=65)
                                        for axis in "XYZ":
                                            ui.Label(axis, width=12)
                                            model = ui.SimpleFloatModel(0.0)
                                            ui.FloatDrag(model=model, step=step)
                                            model.add_end_edit_fn(lambda _m, sid=sid: self.commit(sid))
                                            self.models[sid].append(model)
                            self.rows[sid] = row
        self.refresh_values()
        self.refresh()

    def commit(self, sid):
        if self.runtime.pose_state != "editing":
            return
        values = [m.as_float for m in self.models[sid]]
        try:
            self.runtime.apply_pose(sid, values[:3], values[3:])
        except Exception as exc:
            self.runtime.set_status(str(exc))
            self.refresh_values()

    def refresh_values(self):
        if not self.runtime.poses:
            return
        for sid, models in self.models.items():
            pose = self.runtime.poses.read(sid)
            for model, value in zip(models, pose["position_m"] + pose["rotation_deg"]):
                model.set_value(value)

    def refresh(self):
        r = self.runtime
        available = r.poses is not None and not r.closing and not r.closed
        busy_record = r.record_task and not r.record_task.done()
        busy_pose = r.pose_task and not r.pose_task.done()
        self.enter.enabled = available and r.pose_state == "idle" and not busy_record and not busy_pose
        self.finish.enabled = available and r.pose_state == "editing" and not busy_pose
        self.save.enabled = available and r.pose_state in ("idle", "editing") and not busy_pose
        for row in self.rows.values():
            row.enabled = available and r.pose_state == "editing"
