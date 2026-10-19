"""Isaac Script Editor runtime. Import only inside a running Kit application."""

import asyncio
from copy import deepcopy
import json
import time
from pathlib import Path

import carb
import omni.graph.core as og
import omni.kit.app
import omni.replicator.core as rep
import omni.timeline
import omni.ui as ui
import omni.usd
from pxr import Sdf, Usd, UsdGeom

from .config import load_config, validate_sensors, write_resolved_config, write_rviz
from .discovery import discover_sensors
from .recording import Recorder
from .sensor_pose import SensorPoses
from .pose_panel import PosePanel
from .joint_panel import JointPanel
from .simulation_pacing import SimulationPacing
from .cloud_rate import CloudPublishers, resolve_scan_rates, prune_invalid_sdg_handles
from .robot_discovery import discover_robots, bind_config
from .state_publication import StatePublication
from .render_lease import RenderLease
from .performance import Performance

GRAPH_PATH = "/LidarVisualizer"
PUBLISH_SETTING = "/exts/isaacsim.ros2.bridge/publish_without_verification"


class LidarVisualizer:
    def __init__(self, project_dir, config=None, *, artifact_dir=None):
        self.project_dir = Path(project_dir)
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else self.project_dir
        self.config = deepcopy(config) if config is not None else load_config(self.project_dir / "config/sensors.json")
        self.config.setdefault('root_frame', 'swing_coordinate')
        self.config.setdefault('horizontal_frame', 'swing_horizontal_coordinate')
        self.app = omni.kit.app.get_app()
        self.context = omni.usd.get_context()
        self.timeline = omni.timeline.get_timeline_interface()
        self.stage = None
        self.layer = None
        self.products = []
        self.recorder = Recorder(self.config)
        self.window = None
        self.status_label = None
        self.simulation_label = None
        self.play_button = None
        self.pause_button = None
        self.start_button = None
        self.stop_button = None
        self.record_models = {}
        self.output_model = None
        self.subscriptions = []
        self.record_task = None
        self.close_task = None
        self.closed = False
        self.closing = False
        self.last_time = None
        self.motion = None
        self.next_poll = 0
        self.status = "Initializing..."
        self.close_lock = asyncio.Lock()
        self.poses = None
        self.pose_panel = None
        self.joint_panel = None
        self.next_joint_poll = 0
        self.pose_state = "idle"
        self.pose_task = None
        self.resume_plan = None
        self.stop_serial = 0
        self.publisher_generation = 0
        self.original_publish_setting = None
        self.pacing = None
        self.cloud_publishers = None
        self.pacing_label = None
        self.state_publication = None
        self.render_lease = None
        self.frame_overlay = None
        self.camera = self.camera_panel = self.base_panel = None
        self.exporting = False
        self.pending_export = None
        self.performance_label = None
        self.performance = Performance(self.project_dir, self.config['output_directory'])
        self.recorder.performance = self.performance

    async def initialize(self, show_ui=True):
        # RTX allocates many exported buffers per sensor. A low desktop shell
        # limit can crash Kit while rebuilding thirteen scan pipelines.
        import os
        if os.name == 'posix':
            # A failed ROS factory may still appear as an enabled extension.
            # Querying its native interface can segfault this Isaac 6 build.
            # Validate this project's launch contract before enabling/querying ROS.
            install = Path(os.environ.get('ISAACSIM_PATH', '/root/isaacsim')).resolve()
            core = install / 'exts/isaacsim.ros2.core'
            library_paths = {str(Path(p).resolve()) for p in os.environ.get('LD_LIBRARY_PATH', '').split(':') if p}
            required = (core / 'bin', core / 'jazzy/lib')
            missing = [str(p) for p in required if str(p.resolve()) not in library_paths]
            if os.environ.get('ROS_DISTRO') != 'jazzy' or missing:
                raise RuntimeError(
                    'ROS launch environment is incomplete. Close Isaac and restart with '
                    '/usr/bin/python3 /root/gpufree-data/semantic/scripts/260907LidarVisualizer/launch_isaac.py. '
                    'Do not enable the failed ROS interface in this process. Missing paths: '
                    + ', '.join(missing))
            import resource
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(max(soft, 65536), hard), hard))
        if self.config.get("robot_motion", {}).get("enabled", False):
            settings = carb.settings.get_settings()
            if any(settings.get_as_bool(path) for path in (
                    "/renderer/raytracingMotion/enabled", "/rtx/hydra/supportMultiTickRate",
                    "/rtx/rendering/perSensorTickTlas")):
                raise RuntimeError("For this 3DGS scene, restart Isaac using this project's launch_isaac.py, then run the entry again.")
        manager = self.app.get_extension_manager()
        for ext in ("isaacsim.core.nodes", "isaacsim.sensors.rtx.nodes",
                    "isaacsim.ros2.bridge", "isaacsim.ros2.nodes",
                    "isaacsim.core.experimental.prims", "omni.graph.scriptnode"):
            manager.set_extension_enabled_immediate(ext, True)
            if not manager.is_extension_enabled(ext):
                raise RuntimeError(f"Could not enable extension: {ext}")
        await self.app.next_update_async()
        if not manager.is_extension_enabled("isaacsim.ros2.core"):
            raise RuntimeError("ROS 2 Core failed to start. Close Isaac and restart with this project's launch_isaac.py.")
        from isaacsim.ros2.core.bindings import _ros2_core
        bridge = _ros2_core.acquire_ros2_core_interface()
        ready = bridge.get_startup_status()
        _ros2_core.release_ros2_core_interface(bridge)
        if not ready:
            raise RuntimeError("ROS 2 Bridge is unavailable. Restart Isaac using this project's launch_isaac.py.")
        self.stage = self.context.get_stage()
        if self.stage is None:
            raise RuntimeError("Open a scene in Isaac Sim before running this script.")
        if self.config.get('auto_bind_robot') and not self.config.get('robot_binding'):
            candidates = [c for c in discover_robots(self.stage) if c['auto_eligible']]
            if len(candidates) != 1:
                raise ValueError('Select one excavator in the Excavator Connection window')
            self.config = bind_config(self.config, candidates[0])
            self.recorder.config = self.config
        self.config.setdefault('control_mode', 'scripted')
        self.config.setdefault('robot_motion', {})['control_mode'] = self.config['control_mode']
        self.config['robot_motion']['reference_frame'] = self.config.get('root_frame', 'swing_coordinate')
        self.config['robot_motion']['horizontal_frame'] = self.config.get('horizontal_frame', 'swing_horizontal_coordinate')
        if self.config.get("auto_discover", not bool(self.config.get("sensors"))):
            self.config["sensors"] = discover_sensors(self.stage, self.config["world_frame"],
                self.config.get('robot_binding', {}).get('robot_prim'))
        validate_sensors(self.config)
        resolve_scan_rates(self.stage, self.config["sensors"])
        if any(not self.stage.GetPrimAtPath(s['prim_path']).GetAttribute(
                'omni:sensor:Core:instantLidar').Get() for s in self.config['sensors']):
            raise ValueError('This Sensor Visualizer version expects Instant LiDARs only')
        import math
        sim_hz = self.config.get('simulation_pacing', {}).get('simulation_hz', 60.)
        rates = [s['publish_rate_hz'] for s in self.config['sensors']]
        from .camera_rig import resolve_camera_configs
        self.camera_configs = resolve_camera_configs(self.stage,self.config)
        self.config['active_cameras'] = self.camera_configs
        rates.extend(float(c['save_rate_hz']) for c in self.camera_configs)
        for rate in rates:
            if (not math.isfinite(rate) or rate <= 0 or rate > sim_hz or
                    abs(sim_hz/rate-round(sim_hz/rate)) > 1e-6):
                raise ValueError('Synchronized capture rates must divide simulation_hz (e.g. 5, 10, 15, 20, 30 Hz at 60 Hz)')
        for sensor in self.config["sensors"]:
            print(f"[LidarVisualizer] {sensor['prim_path']} -> {sensor['topic']} (frame: {sensor['frame_id']})", flush=True)
        for sensor in self.config["sensors"]:
            prim = self.stage.GetPrimAtPath(sensor["prim_path"])
            if not prim or not prim.IsActive() or prim.GetTypeName() != "OmniLidar":
                raise RuntimeError(f"No active OmniLidar at: {sensor['prim_path']}")
        if self.stage.GetPrimAtPath(GRAPH_PATH):
            raise RuntimeError(f"{GRAPH_PATH} already exists outside this instance. Remove the old graph or change GRAPH_PATH.")
        was_playing = self.timeline.is_playing()
        moving = self.config.get("robot_motion", {}).get("enabled", False) and self.config['control_mode'] == 'scripted'
        if moving and not self.timeline.is_stopped():
            # Physics schema edits invalidate live articulation tensor views.
            # Rebuild while stopped so Play creates a fresh physics view.
            self.timeline.stop()
            await self.app.next_update_async()
        elif was_playing:
            self.timeline.pause()
            await self.app.next_update_async()
        try:
            # Populate real TF history before RViz/rosbag joins the topics.
            settings = carb.settings.get_settings()
            self.original_publish_setting = settings.get_as_bool(PUBLISH_SETTING)
            settings.set_bool(PUBLISH_SETTING, True)
            self.layer = Sdf.Layer.CreateAnonymous("LidarVisualizer.usda")
            self.stage.GetSessionLayer().subLayerPaths.insert(0, self.layer.identifier)
            self.render_lease = RenderLease(self.stage, self.layer,
                [s['prim_path'] for s in self.config['sensors']])
            with Usd.EditContext(self.stage, self.layer):
                if self.config.get("robot_motion", {}).get("enabled", False):
                    from .articulation_motion import ArticulationMotion
                    self.motion = ArticulationMotion(self.stage, self.layer, self.config["robot_motion"], self._motion_error)
                    self.motion.performance = self.performance
                    self.motion.prepare()
            self.pacing = SimulationPacing(self.app, self.timeline, self.stage, self.layer, self.config)
            self.pacing.performance = self.performance
            await self._create_publishers()
            if self.camera_configs:
                if not self.motion:
                    raise ValueError('Camera frame matching requires a connected excavator')
                if len(self.camera_configs)>1:
                    from .camera_rig import CameraRig
                    self.camera = CameraRig(self,self.camera_configs)
                    await self.camera.initialize()
                else:
                    from .camera_capture import CameraCapture
                    self.camera = CameraCapture(self,self.camera_configs[0])
            self.poses = SensorPoses(self.stage, self.config["sensors"], self.config["output_directory"],
                                     self.timeline.get_current_time)
            write_rviz(self.config, self.artifact_dir / "rviz/lidars.rviz")
            if show_ui:
                self._build_window()
            self.subscriptions.append(self.timeline.get_timeline_event_stream().create_subscription_to_pop(
                self._on_timeline, name="LidarVisualizer timeline"))
            self.subscriptions.append(self.context.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage, name="LidarVisualizer stage"))
            self.subscriptions.append(self.app.get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="LidarVisualizer recorder"))
            self.subscriptions.append(self.app.get_shutdown_event_stream().create_subscription_to_pop(
                self._on_shutdown, name="LidarVisualizer shutdown"))
            write_resolved_config(self.config, self.stage.GetRootLayer().identifier, self.artifact_dir)
            self.set_status(f"Publishers ready: {len(self.config['sensors'])} LiDAR(s). Click Play Simulation, then view clouds in RViz.")
            self.performance.event('span', name='runtime.initialize', duration_s=time.monotonic()-self.performance.started)
        except Exception:
            await self.close()
            raise
        finally:
            if was_playing and not self.closed:
                self.timeline.play()
        return self

    async def _create_publishers(self):
        self.publisher_generation += 1
        with Usd.EditContext(self.stage, self.layer):
            for sensor in self.config["sensors"]:
                prim = self.stage.GetPrimAtPath(sensor["prim_path"])
                prim.CreateAttribute("omni:sensor:Core:outputFrameOfReference", Sdf.ValueTypeNames.Token).Set("SENSOR")
                prim.CreateAttribute("omni:sensor:Core:accumulateOutputs", Sdf.ValueTypeNames.Bool).Set(True)
                # A new product path prevents reuse of an old render/scan pipeline.
                product = rep.create.render_product(sensor["prim_path"], (300, 300),
                    name=f"LV_{sensor['id']}_g{self.publisher_generation}", force_new=True,
                    write_to_session_layer=False)
                self.products.append(product)
            self._build_graph()
        if self.motion and self.config.get('state_publication', {}).get('enabled', False):
            self.state_publication = StatePublication(self)
            await self.state_publication.build(GRAPH_PATH)
        self.cloud_publishers = CloudPublishers()
        await self.cloud_publishers.attach(self, self.cloud_qos)

    async def _release_publishers(self):
        if not self.layer or self.context.get_stage() != self.stage:
            return
        if self.state_publication:
            self.state_publication.close()
            self.state_publication = None
        if self.cloud_publishers:
            await self.cloud_publishers.close(self.app)
            self.cloud_publishers = None
        with Usd.EditContext(self.stage, self.layer):
            if self.stage.GetPrimAtPath(GRAPH_PATH):
                self.stage.RemovePrim(GRAPH_PATH)
        await self.app.next_update_async()
        await self.app.next_update_async()
        paths = {Sdf.Path(product.path) for product in self.products}
        for product in self.products:
            product.destroy()
        self.products.clear()
        prune_invalid_sdg_handles()
        for layer in (self.stage.GetRootLayer(), self.stage.GetSessionLayer()):
            def remove_links(path):
                spec = layer.GetObjectAtPath(path)
                if isinstance(spec, Sdf.RelationshipSpec) and spec.name == "products":
                    for field in ("explicitItems", "prependedItems", "appendedItems", "addedItems", "deletedItems", "orderedItems"):
                        items = list(getattr(spec.targetPathList, field))
                        if any(item in paths for item in items):
                            setattr(spec.targetPathList, field, [item for item in items if item not in paths])
            layer.Traverse(Sdf.Path.absoluteRootPath, remove_links)
        await self.app.next_update_async()

    async def begin_adjustment(self):
        if self.closing or self.closed or self.pose_state != "idle":
            return
        self.pose_state = "entering"
        self.resume_plan = {"playing": self.timeline.is_playing(), "recording": None,
                            "stop_serial": self.stop_serial}
        self.timeline.pause()
        self._refresh_controls()
        self.set_status("Pausing and finishing the recording before adjusting LiDAR...")
        try:
            if self.record_task and not self.record_task.done():
                await self.record_task
            if self.recorder.running:
                self.resume_plan["recording"] = {
                    "sensor_ids": [s["id"] for s in self.recorder.manifest["sensors"]],
                    "output_directory": str(self.recorder.session_dir.parent),
                    "previous_segment": str(self.recorder.session_dir)}
            await self.stop_recording()
            await self._release_publishers()
            if self.closing:
                return
            self.poses.log("adjustment_started", resume_plan=self.resume_plan)
            self.pose_state = "editing"
            if self.pose_panel:
                self.pose_panel.refresh_values()
            self.set_status("Adjust Position / Rotation below. Done / Resume restores prior playback and recording.")
        except Exception:
            self.pose_state = "idle"
            raise
        finally:
            self._refresh_controls()

    def apply_pose(self, sid, position, angles):
        if self.pose_state != "editing" or self.timeline.is_playing() or self.closing:
            raise ValueError("Click Adjust LiDAR and wait for the controls to unlock first.")
        record = (self.resume_plan or {}).get("recording")
        changed = self.poses.apply(sid, position, angles, record)
        if changed:
            self.set_status(f"Updated {sid}. Click Done / Resume to scan, or Save Current Poses to export.")
        return changed

    async def finish_adjustment(self):
        if self.closing or self.closed or self.pose_state != "editing":
            return
        self.pose_state = "resuming"
        plan = self.resume_plan or {}
        self._refresh_controls()
        self.set_status("Preparing fresh LiDAR publishers...")
        try:
            # Covers retry after a partially completed recreation.
            if self.products or self.stage.GetPrimAtPath(GRAPH_PATH):
                await self._release_publishers()
            await self._create_publishers()
            await self.app.next_update_async()
            self.poses.log("adjustment_finished", poses=self.poses.snapshot())
            self.pose_state = "idle"
            if self.closing:
                return
            resume = plan.get("stop_serial") == self.stop_serial and plan.get("playing")
            if resume:
                self.timeline.play()
                # Timeline play is committed on a Kit update, not at the call site.
                await self.app.next_update_async()
                if self.closing or self.stop_serial != plan.get("stop_serial") or not self.timeline.is_playing():
                    self.resume_plan = None
                    return
                record = plan.get("recording")
                if record:
                    path = await self.start_recording(record["sensor_ids"], record["output_directory"])
                    self.poses.log("recording_resumed", previous_segment=record["previous_segment"], segment=str(path))
                else:
                    self.set_status("Scanning resumed with updated LiDAR poses. Recording remains off.")
            else:
                self.set_status("LiDAR poses applied. Click Play Simulation when ready; recording remains off.")
            self.resume_plan = None
        except Exception:
            self.timeline.pause()
            self.pose_state = "editing"
            raise
        finally:
            self._refresh_controls()

    def _schedule_pose(self, action):
        if self.closing or self.closed or (self.pose_task and not self.pose_task.done()):
            return
        async def guarded():
            try:
                await action()
            except Exception as exc:
                self.set_status(str(exc))
                carb.log_error(str(exc))
        self.pose_task = asyncio.ensure_future(guarded())
        self.pose_task.add_done_callback(lambda _: self._refresh_controls())

    def request_begin_adjustment(self):
        self._schedule_pose(self.begin_adjustment)

    def request_finish_adjustment(self):
        self._schedule_pose(self.finish_adjustment)

    def request_save_poses(self):
        if self.closing or not self.poses or self.pose_state not in ("idle", "editing"):
            return
        try:
            path = self.poses.save()
            self.set_status(f"Saved current poses: {path}. Stop still restores original mounting poses.")
        except Exception as exc:
            self.set_status(f"Could not save poses: {exc}")

    def _build_graph(self):
        keys = og.Controller.Keys
        tick = "Motion.outputs:execOut" if self.motion else "Tick.outputs:tick"
        nodes = [("Tick", "omni.graph.action.OnPlaybackTick"),
                 ("Context", "isaacsim.ros2.bridge.ROS2Context"),
                 ("Time", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                 ("Clock", "isaacsim.ros2.bridge.ROS2PublishClock")]
        values = [("Context.inputs:domain_id", self.config["ros_domain_id"]),
                  ("Context.inputs:useDomainIDEnvVar", False),
                  ("Time.inputs:resetOnStop", True), ("Clock.inputs:topicName", "/clock")]
        connections = [(tick, "Clock.inputs:execIn"),
                       ("Time.outputs:simulationTime", "Clock.inputs:timeStamp"),
                       ("Context.outputs:context", "Clock.inputs:context")]
        qos = json.dumps({"history": "keepLast", "depth": 20, "reliability": "reliable",
                          "durability": "volatile", "deadline": 0.0, "lifespan": 0.0,
                          "liveliness": "systemDefault", "leaseDuration": 0.0})
        self.cloud_qos = qos
        # A full scan may be stamped before recording begins. Retain recent real
        # poses for late-joining recorders instead of inventing an earlier TF.
        tf_qos = json.dumps({"history": "keepLast", "depth": 120, "reliability": "reliable",
                             "durability": "transientLocal", "deadline": 0.0, "lifespan": 0.0,
                             "liveliness": "systemDefault", "leaseDuration": 0.0})
        clock_qos = json.loads(tf_qos)
        clock_qos["depth"] = 1
        values.append(("Clock.inputs:qosProfile", json.dumps(clock_qos)))
        if self.motion:
            nodes += [("Motion", "omni.graph.scriptnode.ScriptNode"),
                      ("HorizontalPose", "isaacsim.core.nodes.IsaacComputeTransformTree"),
                      ("HorizontalTF", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                      ("RootPose", "isaacsim.core.nodes.IsaacComputeTransformTree"),
                      ("RootTF", "isaacsim.ros2.bridge.ROS2PublishTransformTree")]
            values += [("Motion.inputs:script", self.motion.script()),
                       ("RootPose.inputs:targetPrims", [Sdf.Path(self.motion.reference_path)]),
                       ("RootPose.inputs:parentPrim", [Sdf.Path(self.motion.horizontal_path)]),
                       ("RootTF.inputs:parentFrames", [self.config["horizontal_frame"]]),
                       ("RootTF.inputs:childFrames", [self.config["root_frame"]]),
                       ("RootTF.inputs:topicName", "/tf"), ("RootTF.inputs:qosProfile", tf_qos),
                       ("HorizontalPose.inputs:targetPrims", [Sdf.Path(self.motion.horizontal_path)]),
                       ("HorizontalTF.inputs:parentFrames", [self.config["world_frame"]]),
                       ("HorizontalTF.inputs:childFrames", [self.config["horizontal_frame"]]),
                       ("HorizontalTF.inputs:topicName", "/tf"), ("HorizontalTF.inputs:qosProfile", tf_qos)]
            connections += [("Tick.outputs:tick", "Motion.inputs:execIn"),
                            (tick, "RootPose.inputs:execIn"),
                            ("RootPose.outputs:execOut", "RootTF.inputs:execIn"),
                            ("RootPose.outputs:translations", "RootTF.inputs:translations"),
                            ("RootPose.outputs:orientations", "RootTF.inputs:orientations"),
                            ("Time.outputs:simulationTime", "RootTF.inputs:timeStamp"),
                            ("Context.outputs:context", "RootTF.inputs:context")]
            connections += [(tick, 'HorizontalPose.inputs:execIn'),
                            ('HorizontalPose.outputs:execOut', 'HorizontalTF.inputs:execIn'),
                            ('HorizontalPose.outputs:translations', 'HorizontalTF.inputs:translations'),
                            ('HorizontalPose.outputs:orientations', 'HorizontalTF.inputs:orientations'),
                            ('Time.outputs:simulationTime', 'HorizontalTF.inputs:timeStamp'),
                            ('Context.outputs:context', 'HorizontalTF.inputs:context')]
        for sensor, product in zip(self.config["sensors"], self.products):
            sid = sensor["id"]
            cloud, pose, tf = sid + "_Cloud", sid + "_Pose", sid + "_TF"
            nodes += [(pose, "isaacsim.core.nodes.IsaacComputeTransformTree"),
                      (tf, "isaacsim.ros2.bridge.ROS2PublishTransformTree")]
            values += [(pose + ".inputs:targetPrims", [Sdf.Path(sensor["prim_path"])]),
                       (tf + ".inputs:topicName", "/tf"),
                       (tf + ".inputs:qosProfile", tf_qos),
                       # A non-articulation target gives exactly one sensor pose.
                       (tf + ".inputs:parentFrames", [self.config["root_frame"] if self.motion else self.config["world_frame"]]),
                       (tf + ".inputs:childFrames", [sensor["frame_id"]])]
            if self.motion:
                values.append((pose + ".inputs:parentPrim", [Sdf.Path(self.motion.reference_path)]))
            connections += [(tick, pose + ".inputs:execIn"),
                            (pose + ".outputs:execOut", tf + ".inputs:execIn"),
                            (pose + ".outputs:translations", tf + ".inputs:translations"),
                            (pose + ".outputs:orientations", tf + ".inputs:orientations"),
                            ("Time.outputs:simulationTime", tf + ".inputs:timeStamp"),
                            ("Context.outputs:context", tf + ".inputs:context")]
        og.Controller.edit({"graph_path": GRAPH_PATH, "evaluator_name": "execution"},
                           {keys.CREATE_NODES: nodes, keys.SET_VALUES: values, keys.CONNECT: connections})
        if self.motion:
            node = og.Controller.node(GRAPH_PATH + "/Motion")
            og.Controller.create_attribute(node, "inputs:simulationTime", og.Type(og.BaseDataType.DOUBLE))
            og.Controller.connect(GRAPH_PATH + "/Time.outputs:simulationTime", GRAPH_PATH + "/Motion.inputs:simulationTime")

    def _motion_error(self, message):
        self.timeline.pause()
        self.set_status(message)
        carb.log_error(message)

    def _build_window(self):
        # Kit's default font may not contain CJK glyphs. Keep built-in UI text ASCII.
        self.window = ui.Window("Sensor Visualizer", width=860, height=900)
        with self.window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(height=0, spacing=8):
                    ui.Label(f"ROS 2 LiDAR - {len(self.config['sensors'])} sensors - simulation and recording", height=25)
                    ui.Label('Stage: ' + self.stage.GetRootLayer().identifier, word_wrap=True, height=35)
                    binding = self.config.get('robot_binding', {})
                    ui.Label('Robot: ' + self.config['robot_motion'].get('robot_prim', 'none') +
                             ' | Mode: ' + self.config['control_mode'], word_wrap=True, height=30)
                    ui.Label('Angles: native asset radians on ROS; degrees in GUI. Root: ' +
                             self.config.get('root_frame', 'world'), height=22)
                    if self.motion:
                        ui.Label('TF: ' + self.config['world_frame'] + ' -> ' + self.config['horizontal_frame'] +
                                 ' -> ' + self.config['root_frame'] + ' -> sensors', word_wrap=True, height=30)
                        with ui.HStack(height=24):
                            self.axes_model = ui.SimpleBoolModel(False)
                            ui.CheckBox(model=self.axes_model, width=24)
                            ui.Label('Reference axes: short/thick = swing; long/thin = horizontal (RGB = XYZ)')
                            self.axes_model.add_value_changed_fn(self._toggle_frame_overlay)
                    if binding:
                        ui.Label('DOFs: ' + ' | '.join(r + '=' + j['name'] for r, j in binding['joints'].items()),
                                 word_wrap=True, height=30)
                    self.simulation_label = ui.Label("Simulation: stopped", height=20)
                    self.pacing_label = ui.Label("RTF limit: 0.100 | Main loop: 6 FPS while playing", height=20)
                    self.performance_label = ui.Label("Performance monitor starting...", height=20)
                    with ui.HStack(height=30, spacing=8):
                        self.play_button = ui.Button("Play Simulation", clicked_fn=self.request_play)
                        self.pause_button = ui.Button("Pause Simulation", clicked_fn=self.request_pause)
                    ui.Label("View: toggle sensors in RViz > Displays. Select sensors to RECORD below.", height=22)
                    with ui.ScrollingFrame(height=110):
                        with ui.VStack(spacing=4):
                            for sensor in self.config["sensors"]:
                                with ui.HStack(height=25):
                                    model = ui.SimpleBoolModel(sensor.get("record", True))
                                    self.record_models[sensor["id"]] = model
                                    ui.CheckBox(model=model, width=25)
                                    ui.Label(sensor["id"], width=180, tooltip=sensor["prim_path"])
                                    ui.Label(sensor["topic"], tooltip=sensor["prim_path"])
                    ui.Label("Save directory (selection and path apply to the next recording)", height=20)
                    self.output_model = ui.SimpleStringModel(self.config["output_directory"])
                    ui.StringField(model=self.output_model, height=25)
                    with ui.HStack(height=30, spacing=8):
                        self.start_button = ui.Button("Start Recording", clicked_fn=self.request_start_recording)
                        self.stop_button = ui.Button("Stop Recording", clicked_fn=self.request_stop_recording)
                    if self.motion and self.motion.mode == 'scripted':
                        from .base_panel import BasePanel
                        with ui.CollapsableFrame('Whole Excavator Motion', height=0, collapsed=False):
                            with ui.VStack(height=0, spacing=6):
                                self.base_panel = BasePanel(self)
                        with ui.CollapsableFrame("Joint Control", height=0, collapsed=False):
                            with ui.VStack(height=0, spacing=6):
                                self.joint_panel = JointPanel(self)
                    elif self.motion:
                        self.observer_label = ui.Label('Observe mode: waiting for Play to read actual states',
                                                       word_wrap=True, height=65)
                    with ui.CollapsableFrame("LiDAR Mount Adjustment", height=0, collapsed=True):
                        with ui.VStack(height=0, spacing=6):
                            self.pose_panel = PosePanel(self)
                    if self.camera:
                        from .base_panel import CameraPanel
                        with ui.CollapsableFrame('Fisheye Cameras', height=0, collapsed=False):
                            with ui.VStack(height=0, spacing=6):
                                self.camera_panel = CameraPanel(self)
                    self.status_label = ui.Label(self.status, word_wrap=True, height=65)
                    ui.Label("Closing this window stops recording and removes this session's publishers.", height=20)
        self.window.set_visibility_changed_fn(lambda visible: None if visible else self.request_close())
        self._refresh_controls()

    def _refresh_controls(self):
        if not self.window or self.closed:
            return
        playing = self.timeline.is_playing()
        busy = bool(self.record_task and not self.record_task.done())
        running = self.recorder.running
        available = (not self.closing and self.pose_state == "idle"
                     and not (self.pose_task and not self.pose_task.done()))
        self.play_button.enabled = available and not playing
        self.pause_button.enabled = available and playing
        self.start_button.enabled = available and playing and not busy and not running
        # Allow finishing a recording while paused, including retrying a failed stop.
        self.stop_button.enabled = available and not busy and (self.recorder.process is not None or self.pending_export is not None)
        state = "playing" if playing else ("stopped" if self.timeline.is_stopped() else "paused")
        recording = "working..." if busy else ("active" if running else "off")
        self.simulation_label.text = f"Simulation: {state} | Recording: {recording} | Pose: {self.pose_state}"
        if self.performance_label:
            p = self.performance
            rate = p.active_sim/p.active_wall if p.active_wall else 0.
            groups = getattr(self.camera, 'count', 0)
            self.performance_label.text = (f"Runtime wall: {time.monotonic()-p.started:.1f}s | Active sim: {p.active_sim:.2f}s"
                f" | Play RTF: {rate:.3f} | Saved camera groups: {groups}" + (" | Monitor error" if p.error else ""))
        if self.pacing_label and self.pacing:
            actual = self.pacing.actual_rtf
            measured = f"{actual:.3f}" if actual is not None else "--"
            self.pacing_label.text = (f"RTF limit: {self.pacing.config['max_real_time_factor']:.3f} | Actual: {measured}"
                                      f" | Main loop cap: {self.pacing.config['main_loop_fps']} FPS")
        if self.pose_panel:
            self.pose_panel.refresh()
        if self.joint_panel:
            self.joint_panel.refresh()
        if self.base_panel:
            self.base_panel.refresh()
        if self.camera_panel and self.camera:
            self.camera_panel.refresh()
        if self.motion and self.motion.mode == 'observe' and self.motion.last_snapshot:
            row = self.motion.last_snapshot
            import math
            self.observer_label.text = 'Observed: ' + ' | '.join(
                f'{n}: {math.degrees(q):.2f} deg' for n, q in zip(row['names'], row['positions']))

    def _toggle_frame_overlay(self, model):
        if self.frame_overlay:
            self.frame_overlay.close()
            self.frame_overlay = None
        if model.as_bool and self.motion:
            try:
                from .frame_overlay import FrameOverlay
                self.frame_overlay = FrameOverlay(self.motion)
                self.frame_overlay.show()
            except Exception as exc:
                if self.frame_overlay:
                    self.frame_overlay.close()
                    self.frame_overlay = None
                self.set_status(f'Reference axes unavailable: {exc}')
                model.set_value(False)

    def request_play(self):
        if self.closed or self.closing or self.pose_state != "idle":
            return
        self.timeline.play()
        self.set_status("Play requested. View clouds in RViz; Start Recording saves the selected sensors.")
        self._refresh_controls()

    def request_pause(self):
        if self.closed or self.closing or self.pose_state != "idle":
            return
        self.timeline.pause()
        self.set_status("Pause requested. Click Play Simulation to resume; Stop Recording finishes the bag.")
        self._refresh_controls()

    def set_status(self, text):
        self.status = text
        if self.status_label:
            self.status_label.text = text
        print("[LidarVisualizer] " + text, flush=True)

    def scene_metadata(self):
        stage = self.stage
        parameters = {}
        for sensor in self.config["sensors"]:
            prim = stage.GetPrimAtPath(sensor["prim_path"])
            parameters[sensor["id"]] = {
                a.GetName(): str(a.Get()) for a in prim.GetAttributes()
                if a.GetName().startswith("omni:sensor:") and a.HasAuthoredValueOpinion()
            }
        return {"root_layer": stage.GetRootLayer().identifier,
                "used_layers": [l.identifier for l in stage.GetUsedLayers() if not l.anonymous],
                "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
                "sensor_parameters": parameters,
                "pointcloud_qos": json.loads(self.cloud_qos),
                "simulation_pacing": self.pacing.metadata() if self.pacing else None,
                "base_control_at_recording_start": self.motion.base_controller.snapshot()
                    if self.motion and self.motion.mode == 'scripted' and self.motion.base_controller else None,
                "terrain": stage.GetRootLayer().customLayerData.get('sensorVisualizerTerrain'),
                "tf_layout": "world_to_horizontal_to_swing_to_sensor" if self.motion else "world_to_each_sensor",
                "frame_convention_version": 'swing_horizontal_v1',
                "reference_frames": {
                    'world': self.config['world_frame'], 'horizontal': self.config.get('horizontal_frame'),
                    'swing': self.config.get('root_frame'), 'follows': 'track/base_body; not cab swing DOF',
                    'definition': 'H and S share origin; H.Z=world.Z; H.X=normalized XY projection of S.X',
                    'singularity_policy': 'Hold previous valid heading below projection norm 1e-6; recover above 2e-6; first fallback yaw=0',
                    'heading_valid': self.motion.frame_snapshot['heading_valid'] if self.motion else None,
                    'root_pose_semantics': 'Pose of swing frame in world, including full roll/pitch/yaw',
                    'asset_origin_policy': stage.GetPrimAtPath(self.config['robot_motion']['robot_prim']).GetCustomDataByKey('baseOriginPolicy') if self.motion else None,
                    'asset_origin_revision': stage.GetPrimAtPath(self.config['robot_motion']['robot_prim']).GetCustomDataByKey('originRevision') if self.motion else None},
                "reference_prim": self.motion.reference_path if self.motion else None,
                "horizontal_prim": self.motion.horizontal_path if self.motion else None,
                "output_frame": "SENSOR",
                "pose_revision": self.poses.revision if self.poses else None,
                "pose_log": str(self.poses.log_path) if self.poses else None,
                "mount_poses": self.poses.snapshot() if self.poses else [],
                'control_mode': self.config['control_mode'],
                'robot_binding': self.config.get('robot_binding'),
                'state_publication': self.config.get('state_publication'),
                'render_lease': self.render_lease.metadata() if self.render_lease else None,
                'camera_configs': self.config.get('active_cameras', [])}

    async def start_recording(self, sensor_ids=None, output_directory=None):
        if self.pending_export is not None:
            raise ValueError('Finish or retry the previous unified export before starting a new recording.')
        if self.closing or self.closed:
            raise ValueError("The window is closing.")
        if self.pose_state != "idle":
            raise ValueError("Finish adjusting LiDAR before starting a recording.")
        if not self.timeline.is_playing():
            raise ValueError("Click Play Simulation before Start Recording.")
        if sensor_ids is None:
            sensor_ids = [sid for sid, model in self.record_models.items() if model.as_bool]
        if not sensor_ids:
            raise ValueError("Select at least one sensor to record.")
        if output_directory is None:
            output_directory = self.output_model.as_string if self.output_model else self.config["output_directory"]
        with self.performance.span('recording.start_and_metadata'):
            path = self.recorder.start(sensor_ids, output_directory, self.scene_metadata())
        self.performance.track('recorder', self.recorder.process)
        self.performance.event('recording_started', session=str(path))
        (path/'performance_reference.json').write_text(json.dumps({'directory':str(self.performance.directory),
            'recording_start_monotonic_s':time.monotonic()},indent=2)+'\n')
        await asyncio.sleep(0.5)
        if not self.recorder.running:
            code = self.recorder.reap()
            raise RuntimeError(f"Recorder failed to start (exit {code}). See {path}/recorder.log")
        if self.camera:
            try:
                self.camera.start(path)
            except Exception:
                await asyncio.to_thread(self.recorder.stop)
                raise
        self.set_status(f"Recorder running (writes after /clock arrives): {path}")
        return path

    async def stop_recording(self):
        if self.camera:
            with self.performance.span('recording.camera_stop'): self.camera.stop()
        if self.recorder.process is not None:
            self.set_status("Stopping recorder and finishing the bag files...")
            with self.performance.span('recording.ros_stop'):
                code = await asyncio.to_thread(self.recorder.stop)
            self.performance.track('recorder', None)
            self.performance.event('recording_stopped', session=str(self.recorder.session_dir), code=code)
            if code not in (0, -2): raise RuntimeError('Original ROS recorder failed; see recorder.log')
            self.pending_export = self.recorder.session_dir
        if self.pending_export is not None:
            from .bag_export import export_session
            path = await export_session(self, self.pending_export)
            self.pending_export = None
            self.set_status(f"Recording complete. Unified bag: {path or self.recorder.session_dir}")

    def _schedule_record(self, action):
        if self.closing or self.closed or (self.record_task and not self.record_task.done()):
            return
        async def guarded():
            try:
                await action()
            except ValueError as exc:
                # A user-action prerequisite is guidance, not a runtime error.
                self.set_status(str(exc))
            except Exception as exc:
                self.set_status(str(exc))
                carb.log_error(str(exc))
        self.record_task = asyncio.ensure_future(guarded())
        self.record_task.add_done_callback(lambda _task: self._refresh_controls())
        self._refresh_controls()

    def request_start_recording(self):
        if self.pose_state != "idle" or (self.pose_task and not self.pose_task.done()):
            return
        self._schedule_record(self.start_recording)

    def request_stop_recording(self):
        # Serialize after a pending start, including Stop immediately after Start.
        pending = self.record_task
        async def stop_after_pending():
            if pending and not pending.done():
                await pending
            try:
                await self.stop_recording()
            except Exception as exc:
                self.set_status(str(exc))
        if not self.closed:
            self.record_task = asyncio.ensure_future(stop_after_pending())
            self.record_task.add_done_callback(lambda _task: self._refresh_controls())
            self._refresh_controls()

    def _on_timeline(self, event):
        if self.pacing:
            if event.type == int(omni.timeline.TimelineEventType.PLAY):
                self.pacing.play()
            elif event.type in (int(omni.timeline.TimelineEventType.PAUSE), int(omni.timeline.TimelineEventType.STOP)):
                self.pacing.pause()
        if event.type == int(omni.timeline.TimelineEventType.PLAY) and self.pose_state != "idle":
            self.timeline.pause()
            self.set_status("Finish the LiDAR adjustment using Done / Resume before playing.")
        if event.type == int(omni.timeline.TimelineEventType.STOP):
            if self.camera:
                self.camera.reset()
            if self.cloud_publishers:
                self.cloud_publishers.reset()
            self.stop_serial += 1
            self.last_time = None
            self.request_stop_recording()
            if self.motion and not self.closing:
                self.motion.reset()
            if self.poses and not self.closing:
                try:
                    self.poses.reset("stop")
                    if self.pose_panel:
                        self.pose_panel.refresh_values()
                except Exception as exc:
                    self.set_status(f"Pose reset/log error: {exc}")
        self._refresh_controls()

    def _on_stage(self, event):
        if event.type == int(omni.usd.StageEventType.CLOSING):
            if self.pacing:
                self.pacing.close()
            if self.cloud_publishers and self.context.get_stage() == self.stage:
                self.cloud_publishers.prepare_stage_close()
            self.request_close()

    def _on_shutdown(self, _event):
        self.performance.close(wait=False)
        if self.camera:
            self.camera.stop()
        if self.pacing:
            self.pacing.close()
        # Kit cannot await coroutines after shutdown; finish our child synchronously.
        if self.recorder.process:
            try:
                self.recorder.stop()
            except Exception as exc:
                carb.log_error(str(exc))
        if self.poses:
            try:
                self.poses.reset("shutdown")
                self.poses.close()
            except Exception as exc:
                carb.log_error(str(exc))
        if self.original_publish_setting is not None:
            carb.settings.get_settings().set_bool(PUBLISH_SETTING, self.original_publish_setting)

    def _on_update(self, _event):
        if self.camera and self.camera.error and self.recorder.running:
            self.set_status(self.camera.error)
            self.request_stop_recording()
        if self.frame_overlay and not self.closing:
            try:
                self.frame_overlay.update()
            except Exception as exc:
                self._toggle_frame_overlay(ui.SimpleBoolModel(False))
                self.set_status(f'Reference axes closed: {exc}')
        current = self.timeline.get_current_time()
        if self.pacing:
            self.pacing.update(current)
        if self.last_time is not None and current < self.last_time - 1e-6 and self.recorder.running:
            self.request_stop_recording()
        self.last_time = current
        now = time.monotonic()
        phase = ('packing' if self.exporting else 'finishing' if self.record_task and not self.record_task.done() and not self.recorder.running
                 else 'recording' if self.recorder.running else 'playing' if self.timeline.is_playing() else 'paused_or_ready')
        self.performance.update(current, self.timeline.is_playing(), phase, camera_groups=getattr(self.camera,'count',0))
        if self.joint_panel and not self.closed and not self.closing and now >= self.next_joint_poll:
            self.next_joint_poll = now + 0.1
            self.joint_panel.refresh()
        if now >= self.next_poll:
            self.next_poll = now + 0.5
            if not (self.record_task and not self.record_task.done()) and not self.closing:
                code = self.recorder.reap()
                if code is not None:
                    self.set_status(f"Recorder exited ({code}). See {self.recorder.session_dir}/recorder.log")
            self._refresh_controls()

    def request_close(self):
        if self.close_task and not self.close_task.done():
            return
        async def guarded():
            try:
                await self.close()
            except Exception as exc:
                self.set_status(str(exc))
                if self.window:
                    self.window.visible = True
        self.close_task = asyncio.ensure_future(guarded())

    async def close(self):
        async with self.close_lock:
            await self._close_impl()

    async def _close_impl(self):
        if self.closed:
            return
        self.closing = True
        if self.frame_overlay:
            self.frame_overlay.close()
            self.frame_overlay = None
        self._refresh_controls()
        try:
            if self.pose_task and not self.pose_task.done():
                await self.pose_task
            if self.record_task and not self.record_task.done():
                await self.record_task
            await self.stop_recording()
        except Exception:
            self.closing = False
            self._refresh_controls()
            raise
        same_stage = self.context.get_stage() == self.stage
        was_playing = same_stage and self.timeline.is_playing()
        if self.motion and self.motion.mode == 'scripted' and same_stage:
            was_playing = False
            self.timeline.stop()
            await self.app.next_update_async()
        elif was_playing:
            self.timeline.pause()
            await self.app.next_update_async()
        try:
            if self.poses:
                try:
                    if same_stage:
                        self.poses.reset("close")
                        self.poses.log("session_closed")
                finally:
                    if same_stage:
                        self.poses.close()
                    self.poses = None
            if self.motion:
                if self.camera:
                    await self.camera.close()
                    self.camera = None
                self.motion.close(restore=same_stage)
                self.motion = None
            if self.state_publication:
                self.state_publication.close()
                self.state_publication = None
            if same_stage and self.layer:
                await self._release_publishers()
                session = self.stage.GetSessionLayer()
                if self.layer.identifier in session.subLayerPaths:
                    session.subLayerPaths.remove(self.layer.identifier)
                prune_invalid_sdg_handles()
            if self.cloud_publishers:
                await self.cloud_publishers.close(self.app, same_stage=same_stage)
                self.cloud_publishers = None
            if self.pacing:
                self.pacing.close()
                self.pacing = None
            self.products.clear()
            self.layer = None
            self.subscriptions.clear()
            if self.original_publish_setting is not None:
                carb.settings.get_settings().set_bool(PUBLISH_SETTING, self.original_publish_setting)
                self.original_publish_setting = None
            if self.window:
                self.window.set_visibility_changed_fn(None)
                self.window.destroy()
                self.window = None
            self.closed = True
            await asyncio.to_thread(self.performance.close)
        finally:
            self.closing = False
            if was_playing and self.context.get_stage() == self.stage:
                self.timeline.play()
