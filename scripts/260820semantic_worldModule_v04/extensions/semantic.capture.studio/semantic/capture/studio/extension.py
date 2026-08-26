"""Standalone Kit UI for editing v04 projects.

Business logic lives in semantic_world_v04.studio.StudioController. This
module only adapts omni.ui widgets and omni.usd selection events.
"""

import asyncio
import gc
import json
from pathlib import Path
from typing import Any, List

import carb
import omni.ext
import omni.kit.app
import omni.ui as ui
import omni.usd

from semantic_world_v04.core.errors import ValidationFailed
from semantic_world_v04.stage.omni_adapter import OmniStageService
from semantic_world_v04.studio import StudioController

WINDOW_TITLE = "Semantic Capture Studio"


class Extension(omni.ext.IExt):
    def on_startup(self, ext_id: str) -> None:
        self._ext_id = ext_id
        self._controller = StudioController()
        self._stage_service = OmniStageService()
        self._tasks: List[asyncio.Task] = []
        self._status_model = ui.SimpleStringModel("Ready")
        self._window = ui.Window(
            WINDOW_TITLE,
            width=500,
            height=820,
            visible=True,
            dockPreference=ui.DockPreference.LEFT,
        )
        self._build_ui()
        self._schedule_dock()
        carb.log_info("[semantic_world_v04] Studio extension started")

    def on_shutdown(self) -> None:
        for task in getattr(self, "_tasks", []):
            if not task.done():
                task.cancel()
        self._tasks = []
        self._window = None
        self._controller = None
        self._stage_service = None
        gc.collect()

    def _build_ui(self) -> None:
        with self._window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
            ):
                with ui.VStack(spacing=8, height=0):
                    ui.Label("Semantic Capture Studio", height=28)
                    self._build_project_panel()
                    self._build_stage_panel()
                    self._build_sensors_panel()
                    self._build_rigs_panel()
                    self._build_variants_panel()
                    self._build_render_panel()
                    self._build_capture_panel()
                    self._build_execution_panel()
                    self._build_motion_panel()
                    self._build_semantics_panel()
                    self._build_modalities_panel()
                    self._build_run_panel()
                    ui.Separator()
                    with ui.HStack(height=44):
                        ui.Label("Status", width=80)
                        ui.StringField(
                            model=self._status_model,
                            read_only=True,
                            multiline=True,
                        )

    def _build_project_panel(self) -> None:
        with ui.CollapsableFrame("Project", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._project_dir_model = ui.SimpleStringModel(
                    "/root/gpufree-data/semantic/projects/example.swproject"
                )
                self._project_id_model = ui.SimpleStringModel("semantic-capture-project")
                self._project_name_model = ui.SimpleStringModel("Semantic Capture Project")
                self._usd_path_model = ui.SimpleStringModel("")
                self._output_root_model = ui.SimpleStringModel(
                    "/root/gpufree-data/semantic/output"
                )
                self._labeled_string("Project directory", self._project_dir_model)
                self._labeled_string("Project ID", self._project_id_model)
                self._labeled_string("Name", self._project_name_model)
                self._labeled_string("USD path", self._usd_path_model)
                self._labeled_string("Output root", self._output_root_model)
                self._project_state_model = ui.SimpleStringModel("Schema 2 | not saved")
                ui.StringField(model=self._project_state_model, read_only=True)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("New", clicked_fn=self._new_project)
                    ui.Button("Open", clicked_fn=self._open_project)
                    ui.Button("Save", clicked_fn=self._save_project)
                    ui.Button("Save As", clicked_fn=self._save_project_as)

    def _build_stage_panel(self) -> None:
        with ui.CollapsableFrame("Stage", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Open USD", clicked_fn=self._open_stage)
                    ui.Button("Refresh index", clicked_fn=self._refresh_stage_index)
                    ui.Button("Close", clicked_fn=self._close_stage)
                ui.Label(
                    "Use the standard Stage window or Viewport to select a sensor Prim.",
                    word_wrap=True,
                    height=36,
                )
                self._stage_summary_model = ui.SimpleStringModel("No Stage indexed")
                ui.StringField(model=self._stage_summary_model, read_only=True)
                self._prim_search_model = ui.SimpleStringModel("")
                self._prim_path_model = ui.SimpleStringModel("")
                self._labeled_string("Search Prim", self._prim_search_model)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Search tree", clicked_fn=self._search_prims)
                    ui.Button("Select path", clicked_fn=self._select_prim_path)
                self._labeled_string("Prim path", self._prim_path_model)
                self._prim_results_model = ui.SimpleStringModel("No search results")
                ui.StringField(
                    model=self._prim_results_model,
                    read_only=True,
                    multiline=True,
                    height=84,
                )

    def _build_sensors_panel(self) -> None:
        with ui.CollapsableFrame("Sensors", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._sensor_plugin_model = ui.SimpleStringModel("pinhole_camera")
                self._labeled_string("Sensor plugin", self._sensor_plugin_model)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Catalog", clicked_fn=self._show_sensor_catalog)
                    ui.Button("Discover compatible", clicked_fn=self._discover_sensors)
                    ui.Button("Add selected", clicked_fn=self._add_selected_sensor)
                self._sensor_catalog_model = ui.SimpleStringModel(
                    "Use Catalog to list installed sensor plugins"
                )
                ui.StringField(
                    model=self._sensor_catalog_model,
                    read_only=True,
                    multiline=True,
                    height=72,
                )
                self._sensor_id_model = ui.SimpleStringModel("")
                self._sensor_overrides_model = ui.SimpleStringModel("{}")
                self._labeled_string("Sensor ID", self._sensor_id_model)
                self._sensor_schema_model = ui.SimpleStringModel("No schema loaded")
                ui.StringField(
                    model=self._sensor_schema_model,
                    read_only=True,
                    multiline=True,
                    height=64,
                )
                self._labeled_string("Overrides JSON", self._sensor_overrides_model)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Load config", clicked_fn=self._load_sensor_config)
                    ui.Button("Effective", clicked_fn=self._show_effective_sensor)
                    ui.Button("Clear override", clicked_fn=self._clear_sensor_override)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Enable/disable", clicked_fn=self._toggle_sensor)
                    ui.Button("Copy", clicked_fn=self._copy_sensor)
                    ui.Button("Delete", clicked_fn=self._delete_sensor)
                    ui.Button("Apply override", clicked_fn=self._apply_sensor_override)
                self._sensor_summary_model = ui.SimpleStringModel("No sensors")
                ui.StringField(
                    model=self._sensor_summary_model,
                    read_only=True,
                    multiline=True,
                    height=64,
                )

    def _build_rigs_panel(self) -> None:
        with ui.CollapsableFrame("Sensor Rigs / Sync Groups", collapsed=True, height=0):
            with ui.VStack(spacing=4, height=0):
                self._rig_id_model = ui.SimpleStringModel("rig_01")
                self._rig_sensors_model = ui.SimpleStringModel("")
                self._rig_reference_model = ui.SimpleStringModel("")
                self._labeled_string("Rig ID", self._rig_id_model)
                self._labeled_string(
                    "Sensor IDs (; separated)", self._rig_sensors_model
                )
                self._labeled_string(
                    "Reference Prim (optional)", self._rig_reference_model
                )
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Add Rig", clicked_fn=self._add_rig)
                    ui.Button("Delete Rig", clicked_fn=self._delete_rig)
                self._rig_summary_model = ui.SimpleStringModel("No rigs")
                ui.StringField(
                    model=self._rig_summary_model,
                    read_only=True,
                    multiline=True,
                    height=64,
                )

    def _build_variants_panel(self) -> None:
        with ui.CollapsableFrame("Variants", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._variant_id_model = ui.SimpleStringModel("isolated")
                self._include_paths_model = ui.SimpleStringModel("/World")
                self._labeled_string("Variant ID", self._variant_id_model)
                self._labeled_string(
                    "Include paths (; separated)", self._include_paths_model
                )
                ui.Button(
                    "Add semantic-only include variant",
                    clicked_fn=self._add_include_variant,
                    height=28,
                )
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Enable/disable", clicked_fn=self._toggle_variant)
                    ui.Button("Delete", clicked_fn=self._delete_variant)
                self._variant_summary_model = ui.SimpleStringModel("No project")
                ui.StringField(
                    model=self._variant_summary_model,
                    read_only=True,
                    multiline=True,
                    height=64,
                )

    def _build_modalities_panel(self) -> None:
        with ui.CollapsableFrame("Modality Matrix", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                ui.Label(
                    "Modalities come from the selected sensor plugin. Enter only "
                    "IDs shown in Available modalities.",
                    word_wrap=True,
                    height=54,
                )
                self._matrix_variant_model = ui.SimpleStringModel("full_scene")
                self._matrix_sensor_model = ui.SimpleStringModel("")
                self._labeled_string("Variant ID", self._matrix_variant_model)
                self._labeled_string("Sensor ID", self._matrix_sensor_model)
                self._matrix_available_model = ui.SimpleStringModel(
                    "Load row to inspect sensor capabilities"
                )
                self._matrix_modalities_model = ui.SimpleStringModel("")
                self._labeled_string(
                    "Available modalities", self._matrix_available_model, read_only=True
                )
                self._labeled_string(
                    "Selected (; separated)", self._matrix_modalities_model
                )
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Load row", clicked_fn=self._load_modality_row)
                    ui.Button("Apply row", clicked_fn=self._apply_modality_row)
                self._modality_summary_model = ui.SimpleStringModel("No project")
                ui.StringField(
                    model=self._modality_summary_model,
                    read_only=True,
                    multiline=True,
                    height=90,
                )

    def _build_render_panel(self) -> None:
        with ui.CollapsableFrame("Render Profile", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._renderer_model = ui.SimpleStringModel("RayTracedLighting")
                self._resolution_width_model = ui.SimpleStringModel("640")
                self._resolution_height_model = ui.SimpleStringModel("480")
                self._warmup_frames_model = ui.SimpleStringModel("8")
                self._rt_subframes_model = ui.SimpleStringModel("1")
                self._spp_per_frame_model = ui.SimpleStringModel("1")
                self._total_spp_model = ui.SimpleStringModel("1")
                self._max_bounces_model = ui.SimpleStringModel("4")
                self._denoiser_model = ui.SimpleBoolModel(True)
                self._render_settings_model = ui.SimpleStringModel("{}")
                self._labeled_string(
                    "Renderer", self._renderer_model
                )
                ui.Label(
                    "Renderer: RayTracedLighting or PathTracing",
                    word_wrap=True,
                    height=28,
                )
                self._labeled_string("Width", self._resolution_width_model)
                self._labeled_string("Height", self._resolution_height_model)
                self._labeled_string("Warmup frames", self._warmup_frames_model)
                self._labeled_string("RT subframes", self._rt_subframes_model)
                self._labeled_string("SPP / frame", self._spp_per_frame_model)
                self._labeled_string("Total SPP", self._total_spp_model)
                self._labeled_string("Max bounces", self._max_bounces_model)
                self._labeled_bool("Denoiser", self._denoiser_model)
                self._labeled_string("Settings JSON", self._render_settings_model)
                ui.Button("Apply render profile", clicked_fn=self._on_apply_render_config)

    def _build_capture_panel(self) -> None:
        with ui.CollapsableFrame("Capture Schedule", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._physics_hz_model = ui.SimpleStringModel("60")
                self._capture_fps_model = ui.SimpleStringModel("10")
                self._start_frame_model = ui.SimpleStringModel("0")
                self._frame_count_model = ui.SimpleStringModel("1")
                self._capture_initial_frame_model = ui.SimpleBoolModel(True)
                self._segment_frames_model = ui.SimpleStringModel("100")
                self._labeled_string("Physics Hz", self._physics_hz_model)
                self._labeled_string("Capture FPS", self._capture_fps_model)
                self._labeled_string("Start frame", self._start_frame_model)
                self._labeled_string("Frame count", self._frame_count_model)
                self._labeled_bool(
                    "Capture initial frame", self._capture_initial_frame_model
                )
                self._labeled_string("Segment frames", self._segment_frames_model)
                ui.Button("Apply capture schedule", clicked_fn=self._on_apply_capture_config)

    def _build_execution_panel(self) -> None:
        with ui.CollapsableFrame("Long-job Execution", collapsed=True, height=0):
            with ui.VStack(spacing=4, height=0):
                self._segmentation_strategy_model = ui.SimpleStringModel("auto")
                self._heartbeat_timeout_model = ui.SimpleStringModel("120")
                self._no_progress_timeout_model = ui.SimpleStringModel("600")
                self._segment_start_timeout_model = ui.SimpleStringModel("300")
                self._graceful_stop_timeout_model = ui.SimpleStringModel("30")
                self._telemetry_interval_model = ui.SimpleStringModel("5")
                self._labeled_string(
                    "Segmentation strategy", self._segmentation_strategy_model
                )
                ui.Label(
                    "Strategy: auto, single_worker, or replay_from_zero",
                    word_wrap=True,
                    height=28,
                )
                self._labeled_string(
                    "Heartbeat timeout (s)", self._heartbeat_timeout_model
                )
                self._labeled_string(
                    "No-progress timeout (s)", self._no_progress_timeout_model
                )
                self._labeled_string(
                    "Segment start timeout (s)", self._segment_start_timeout_model
                )
                self._labeled_string(
                    "Graceful stop timeout (s)", self._graceful_stop_timeout_model
                )
                self._labeled_string(
                    "Telemetry interval (s)", self._telemetry_interval_model
                )
                ui.Button(
                    "Apply execution policy",
                    clicked_fn=self._on_apply_execution_config,
                )

    def _build_motion_panel(self) -> None:
        with ui.CollapsableFrame("Motion / Trajectory", collapsed=True, height=0):
            with ui.VStack(spacing=4, height=0):
                self._motion_plugin_model = ui.SimpleStringModel("none")
                self._motion_source_model = ui.SimpleStringModel("")
                self._motion_absolute_seek_model = ui.SimpleBoolModel(False)
                self._motion_options_model = ui.SimpleStringModel("{}")
                self._labeled_string("Plugin", self._motion_plugin_model)
                ui.Label(
                    "Plugin: none or csv_articulation",
                    word_wrap=True,
                    height=28,
                )
                self._labeled_string("CSV source", self._motion_source_model)
                self._labeled_bool(
                    "Supports absolute seek", self._motion_absolute_seek_model
                )
                self._labeled_string("Options JSON", self._motion_options_model)
                ui.Label(
                    "CSV options require articulation_prim_path and joint_columns.",
                    word_wrap=True,
                    height=36,
                )
                ui.Button("Apply motion", clicked_fn=self._on_apply_motion_config)

    def _build_semantics_panel(self) -> None:
        with ui.CollapsableFrame("Semantic Profile", collapsed=True, height=0):
            with ui.VStack(spacing=4, height=0):
                self._semantic_mapping_model = ui.SimpleStringModel("")
                self._semantic_label_model = ui.SimpleStringModel("class")
                self._semantic_background_model = ui.SimpleStringModel("0")
                self._semantic_options_model = ui.SimpleStringModel("{}")
                self._labeled_string("Mapping path", self._semantic_mapping_model)
                self._labeled_string("Label attribute", self._semantic_label_model)
                self._labeled_string("Background ID", self._semantic_background_model)
                self._labeled_string("Options JSON", self._semantic_options_model)
                ui.Button("Apply semantic profile", clicked_fn=self._on_apply_semantic_config)

    def _build_run_panel(self) -> None:
        with ui.CollapsableFrame("Run", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Validate", clicked_fn=self._validate)
                    ui.Button("Preflight", clicked_fn=self._preflight)
                    ui.Button("Compile JobSpec", clicked_fn=self._compile_job)
                self._preflight_model = ui.SimpleStringModel(
                    "Run preflight before starting a production capture"
                )
                ui.StringField(
                    model=self._preflight_model,
                    read_only=True,
                    multiline=True,
                    height=82,
                )
                self._last_job_id_model = ui.SimpleStringModel("")
                self._labeled_string("Job ID", self._last_job_id_model)
                with ui.HStack(height=28, spacing=4):
                    ui.Button(
                        "Run headless & exit",
                        clicked_fn=self._run_headless_and_exit,
                    )
                    ui.Button("Run + monitor", clicked_fn=self._run_headless_monitor)
                    ui.Button("Refresh status", clicked_fn=self._refresh_job_status)
                    ui.Button("Stop", clicked_fn=self._stop_job)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Resume", clicked_fn=self._resume_job)
                    ui.Button("Tail logs", clicked_fn=self._tail_logs)
                    ui.Button("Job history", clicked_fn=self._refresh_job_history)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Segments", clicked_fn=self._refresh_segments)
                    ui.Button("Failure report", clicked_fn=self._show_failure_report)
                self._job_history_model = ui.SimpleStringModel("No job history loaded")
                ui.StringField(
                    model=self._job_history_model,
                    read_only=True,
                    multiline=True,
                    height=82,
                )
                self._log_tail_model = ui.SimpleStringModel("No Runtime log loaded")
                ui.StringField(
                    model=self._log_tail_model,
                    read_only=True,
                    multiline=True,
                    height=100,
                )
                ui.Label(
                    "Recommended: Run headless & exit. Monitor mode keeps this "
                    "Kit process open and can consume GPU resources.",
                    word_wrap=True,
                    height=52,
                )

    @staticmethod
    def _labeled_string(
        label: str,
        model: ui.SimpleStringModel,
        *,
        read_only: bool = False,
    ) -> None:
        with ui.HStack(height=26, spacing=4):
            ui.Label(label, width=160)
            ui.StringField(model=model, read_only=read_only)

    @staticmethod
    def _labeled_bool(label: str, model: ui.SimpleBoolModel) -> None:
        with ui.HStack(height=26, spacing=4):
            ui.Label(label, width=160)
            ui.CheckBox(model=model, width=24)

    def _new_project(self) -> None:
        try:
            self._controller.new_project(
                project_id=self._project_id_model.as_string,
                name=self._project_name_model.as_string,
                usd_path=self._usd_path_model.as_string,
                output_root=self._output_root_model.as_string,
            )
            self._set_status("New project created; add a Stage and sensors")
            self._load_configuration_models()
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("new project", exc)

    def _open_project(self) -> None:
        try:
            project = self._controller.open_project(
                Path(self._project_dir_model.as_string)
            )
            self._project_id_model.set_value(project.project_id)
            self._project_name_model.set_value(project.name)
            self._usd_path_model.set_value(project.stage.usd_path)
            self._output_root_model.set_value(project.output.root_dir)
            self._load_configuration_models()
            self._set_status(f"Opened project {project.project_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("open project", exc)

    def _save_project(self) -> None:
        try:
            project = self._controller.project
            if project is None:
                self._new_project()
                project = self._controller.project
            if project is None:
                raise RuntimeError("project creation failed")
            self._prepare_project()
            self._persist_project()
        except Exception as exc:
            self._set_error("save project", exc)

    def _save_project_as(self) -> None:
        try:
            self._prepare_project()
            destination = self._controller.save_project_as(
                Path(self._project_dir_model.as_string)
            )
            self._set_status(f"Saved project as {destination}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("save project as", exc)

    def _open_stage(self) -> None:
        self._spawn(self._open_stage_async())

    async def _open_stage_async(self) -> None:
        try:
            usd_path = self._usd_path_model.as_string
            self._set_status(f"Opening Stage: {usd_path}")
            index = await self._stage_service.open(usd_path)
            self._controller.set_stage_index(index)
            self._stage_summary_model.set_value(
                f"{len(index)} prims; "
                f"{len(self._controller.discover_sensors())} compatible sensor Prim(s)"
            )
            self._set_status("Stage loaded and indexed")
        except Exception as exc:
            self._set_error("open Stage", exc)

    def _refresh_stage_index(self) -> None:
        try:
            index = self._stage_service.rebuild_index()
            self._controller.set_stage_index(index)
            self._stage_summary_model.set_value(
                f"{len(index)} prims; "
                f"{len(self._controller.discover_sensors())} compatible sensor Prim(s)"
            )
            self._set_status("Stage index refreshed")
        except Exception as exc:
            self._set_error("refresh Stage", exc)

    def _close_stage(self) -> None:
        try:
            self._stage_service.close()
            self._controller.set_stage_index(None)
            self._stage_summary_model.set_value("No Stage indexed")
            self._prim_results_model.set_value("No search results")
            self._set_status("Stage closed")
        except Exception as exc:
            self._set_error("close Stage", exc)

    def _search_prims(self) -> None:
        try:
            index = self._controller.stage_index
            if index is None:
                raise RuntimeError("open or index a Stage first")
            results = index.search(self._prim_search_model.as_string)[:100]
            self._prim_results_model.set_value(
                "\n".join(f"{item.path} [{item.type_name}]" for item in results)
                or "No search results"
            )
            if results:
                self._prim_path_model.set_value(results[0].path)
            self._set_status(f"Found {len(results)} Prim(s); showing at most 100")
        except Exception as exc:
            self._set_error("search Stage", exc)

    def _select_prim_path(self) -> None:
        try:
            path = self._prim_path_model.as_string
            if self._controller.stage_index is None:
                raise RuntimeError("open or index a Stage first")
            self._controller.stage_index.require(path)
            omni.usd.get_context().get_selection().set_selected_prim_paths(
                [path], True
            )
            self._set_status(f"Selected {path} in Stage and Viewport")
        except Exception as exc:
            self._set_error("select Prim", exc)

    def _show_sensor_catalog(self) -> None:
        try:
            rows = []
            for item in self._controller.sensor_plugin_catalog():
                manifest = item["manifest"]
                capabilities = item["capabilities"]
                rows.append(
                    f"{manifest['plugin_id']} {manifest['plugin_version']} | "
                    f"{manifest['display_name']} | "
                    f"time={capabilities.get('time_model', 'unknown')} | "
                    f"modalities={', '.join(manifest.get('supported_modalities', []))}"
                )
            self._sensor_catalog_model.set_value("\n".join(rows) or "No plugins")
            self._load_plugin_schema()
            self._set_status(f"Loaded {len(rows)} sensor plugin(s)")
        except Exception as exc:
            self._set_error("show sensor catalog", exc)

    def _load_plugin_schema(self) -> None:
        plugin = self._controller.registry.sensor(self._sensor_plugin_model.as_string)
        schema = plugin.parameter_schema()
        self._sensor_schema_model.set_value(
            json.dumps(schema, ensure_ascii=False, indent=2)
        )

    def _discover_sensors(self) -> None:
        try:
            plugin_id = self._sensor_plugin_model.as_string
            matches = self._controller.discover_sensors(plugin_id)
            self._sensor_catalog_model.set_value(
                "\n".join(matches) or f"No compatible Prim for {plugin_id}"
            )
            if matches:
                self._prim_path_model.set_value(matches[0])
            self._load_plugin_schema()
            self._set_status(f"Found {len(matches)} {plugin_id} Prim(s)")
        except Exception as exc:
            self._set_error("discover compatible sensors", exc)

    def _add_selected_sensor(self) -> None:
        try:
            selection = omni.usd.get_context().get_selection()
            selected = selection.get_selected_prim_paths()
            if not selected:
                raise ValueError("select a sensor Prim in Stage or Viewport first")
            requested_id = self._sensor_id_model.as_string.strip() or None
            sensor = self._controller.add_sensor_from_stage(
                self._sensor_plugin_model.as_string,
                selected[-1],
                sensor_id=requested_id,
            )
            self._sensor_id_model.set_value(sensor.sensor_id)
            self._matrix_sensor_model.set_value(sensor.sensor_id)
            self._prim_path_model.set_value(sensor.prim_path)
            self._load_sensor_config()
            self._set_status(
                f"Added {sensor.plugin} sensor {sensor.sensor_id} from Stage"
            )
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("add selected sensor", exc)

    def _load_sensor_config(self) -> None:
        try:
            sensor = self._controller.get_sensor(self._sensor_id_model.as_string)
            self._sensor_plugin_model.set_value(sensor.plugin)
            overrides = {
                name: value
                for name, value in sensor.parameters.items()
                if sensor.parameter_sources.get(name) == "override"
            }
            self._sensor_overrides_model.set_value(
                json.dumps(overrides, ensure_ascii=False, indent=2)
            )
            self._load_plugin_schema()
            self._matrix_sensor_model.set_value(sensor.sensor_id)
            self._set_status(f"Loaded configuration for {sensor.sensor_id}")
        except Exception as exc:
            self._set_error("load sensor config", exc)

    def _show_effective_sensor(self) -> None:
        try:
            preview = self._controller.effective_sensor_preview(
                self._sensor_id_model.as_string
            )
            self._sensor_schema_model.set_value(
                json.dumps(preview, ensure_ascii=False, indent=2)
            )
            self._set_status("Effective sensor configuration preview loaded")
        except Exception as exc:
            self._set_error("effective sensor preview", exc)

    def _clear_sensor_override(self) -> None:
        try:
            sensor = self._controller.get_sensor(self._sensor_id_model.as_string)
            names = [
                name
                for name, source in sensor.parameter_sources.items()
                if source == "override"
            ]
            self._controller.clear_sensor_overrides(sensor.sensor_id, names)
            self._sensor_overrides_model.set_value("{}")
            self._show_effective_sensor()
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("clear sensor overrides", exc)

    # Compatibility aliases retained for older UI automation probes.
    def _discover_cameras(self) -> None:
        self._sensor_plugin_model.set_value("pinhole_camera")
        self._discover_sensors()

    def _add_selected_camera(self) -> None:
        self._sensor_plugin_model.set_value("pinhole_camera")
        self._add_selected_sensor()

    def _toggle_sensor(self) -> None:
        try:
            sensor = self._controller.get_sensor(self._sensor_id_model.as_string)
            self._controller.set_sensor_enabled(sensor.sensor_id, not sensor.enabled)
            self._set_status(f"Sensor {sensor.sensor_id} enabled={sensor.enabled}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("toggle sensor", exc)

    def _copy_sensor(self) -> None:
        try:
            sensor = self._controller.copy_sensor(self._sensor_id_model.as_string)
            self._sensor_id_model.set_value(sensor.sensor_id)
            self._set_status(f"Copied sensor as {sensor.sensor_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("copy sensor", exc)

    def _delete_sensor(self) -> None:
        try:
            sensor_id = self._sensor_id_model.as_string
            self._controller.delete_sensor(sensor_id)
            self._sensor_id_model.set_value("")
            self._set_status(f"Deleted sensor {sensor_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("delete sensor", exc)

    def _apply_sensor_override(self) -> None:
        try:
            overrides = json.loads(self._sensor_overrides_model.as_string)
            sensor = self._controller.set_sensor_overrides(
                self._sensor_id_model.as_string, overrides
            )
            self._set_status(f"Applied overrides to {sensor.sensor_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("apply sensor override", exc)

    def _add_rig(self) -> None:
        try:
            sensor_ids = [
                item.strip()
                for item in self._rig_sensors_model.as_string.split(";")
                if item.strip()
            ]
            reference = self._rig_reference_model.as_string.strip() or None
            rig = self._controller.add_rig(
                self._rig_id_model.as_string,
                sensor_ids,
                reference_frame_prim_path=reference,
            )
            self._set_status(
                f"Added Rig {rig.rig_id} with {len(rig.sensor_ids)} sensor(s)"
            )
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("add Rig", exc)

    def _delete_rig(self) -> None:
        try:
            rig_id = self._rig_id_model.as_string
            self._controller.delete_rig(rig_id)
            self._set_status(f"Deleted Rig {rig_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("delete Rig", exc)

    def _add_include_variant(self) -> None:
        try:
            paths = [
                item.strip()
                for item in self._include_paths_model.as_string.split(";")
                if item.strip()
            ]
            variant = self._controller.add_include_variant(
                self._variant_id_model.as_string, paths
            )
            self._set_status(f"Added variant {variant.variant_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("add variant", exc)

    def _toggle_variant(self) -> None:
        try:
            variant = self._controller.get_variant(self._variant_id_model.as_string)
            self._controller.set_variant_enabled(
                variant.variant_id, not variant.enabled
            )
            self._set_status(
                f"Variant {variant.variant_id} enabled={variant.enabled}"
            )
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("toggle variant", exc)

    def _delete_variant(self) -> None:
        try:
            variant_id = self._variant_id_model.as_string
            self._controller.delete_variant(variant_id)
            self._set_status(f"Deleted variant {variant_id}")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("delete variant", exc)

    def _apply_modality_row(self) -> None:
        try:
            modalities = [
                item.strip()
                for item in self._matrix_modalities_model.as_string.split(";")
                if item.strip()
            ]
            self._controller.set_modalities(
                self._matrix_variant_model.as_string,
                self._matrix_sensor_model.as_string,
                modalities,
            )
            self._set_status("Modality matrix row updated")
            self._refresh_summaries()
        except Exception as exc:
            self._set_error("apply modality row", exc)

    def _load_modality_row(self) -> None:
        try:
            variant = self._controller.get_variant(
                self._matrix_variant_model.as_string
            )
            modalities = set(
                variant.modalities_by_sensor.get(
                    self._matrix_sensor_model.as_string, []
                )
            )
            sensor = self._controller.get_sensor(
                self._matrix_sensor_model.as_string
            )
            supported = list(
                self._controller.registry.sensor(sensor.plugin).supported_modalities()
            )
            self._matrix_available_model.set_value("; ".join(supported))
            self._matrix_modalities_model.set_value("; ".join(sorted(modalities)))
            self._set_status("Modality matrix row loaded")
        except Exception as exc:
            self._set_error("load modality row", exc)

    @staticmethod
    def _int_value(model: ui.SimpleStringModel, name: str) -> int:
        try:
            return int(model.as_string.strip())
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc

    @staticmethod
    def _float_value(model: ui.SimpleStringModel, name: str) -> float:
        try:
            return float(model.as_string.strip())
        except ValueError as exc:
            raise ValueError(f"{name} must be a number") from exc

    @staticmethod
    def _json_object(model: ui.SimpleStringModel, name: str) -> dict:
        value = json.loads(model.as_string or "{}")
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be a JSON object")
        return value

    def _apply_render_config(self, announce: bool = True) -> None:
        render = self._controller.set_render_profile(
            renderer=self._renderer_model.as_string.strip(),
            resolution_width=self._int_value(
                self._resolution_width_model, "resolution width"
            ),
            resolution_height=self._int_value(
                self._resolution_height_model, "resolution height"
            ),
            warmup_frames=self._int_value(
                self._warmup_frames_model, "warmup frames"
            ),
            rt_subframes=self._int_value(self._rt_subframes_model, "RT subframes"),
            spp_per_frame=self._int_value(
                self._spp_per_frame_model, "SPP per frame"
            ),
            total_spp=self._int_value(self._total_spp_model, "total SPP"),
            max_bounces=self._int_value(
                self._max_bounces_model, "max bounces"
            ),
            denoiser=self._denoiser_model.as_bool,
            settings=self._json_object(
                self._render_settings_model, "render settings"
            ),
        )
        if announce:
            self._set_status(
                f"Render profile applied: {render.renderer} "
                f"{render.resolution_width}×{render.resolution_height}"
            )

    def _apply_capture_config(self, announce: bool = True) -> None:
        capture = self._controller.set_capture_schedule(
            physics_hz=self._int_value(self._physics_hz_model, "physics Hz"),
            capture_fps=self._int_value(self._capture_fps_model, "capture FPS"),
            start_frame=self._int_value(self._start_frame_model, "start frame"),
            frame_count=self._int_value(self._frame_count_model, "frame count"),
            capture_initial_frame=self._capture_initial_frame_model.as_bool,
            segment_frames=self._int_value(
                self._segment_frames_model, "segment frames"
            ),
        )
        if announce:
            self._set_status(
                f"Capture schedule applied: {capture.frame_count} frames at "
                f"{capture.capture_fps} FPS"
            )

    def _apply_execution_config(self, announce: bool = True) -> None:
        execution = self._controller.set_execution_policy(
            segmentation_strategy=self._segmentation_strategy_model.as_string.strip(),
            heartbeat_timeout_seconds=self._float_value(
                self._heartbeat_timeout_model, "heartbeat timeout"
            ),
            no_progress_timeout_seconds=self._float_value(
                self._no_progress_timeout_model, "no-progress timeout"
            ),
            segment_start_timeout_seconds=self._float_value(
                self._segment_start_timeout_model, "segment start timeout"
            ),
            graceful_stop_timeout_seconds=self._float_value(
                self._graceful_stop_timeout_model, "graceful stop timeout"
            ),
            telemetry_interval_seconds=self._float_value(
                self._telemetry_interval_model, "telemetry interval"
            ),
        )
        if announce:
            self._set_status(
                "Execution policy applied: "
                f"{execution.segmentation_strategy}, "
                f"heartbeat={execution.heartbeat_timeout_seconds}s"
            )

    def _apply_motion_config(self, announce: bool = True) -> None:
        motion = self._controller.set_motion_spec(
            plugin=self._motion_plugin_model.as_string.strip(),
            source_path=self._motion_source_model.as_string.strip() or None,
            supports_absolute_seek=self._motion_absolute_seek_model.as_bool,
            options=self._json_object(self._motion_options_model, "motion options"),
        )
        if announce:
            self._set_status(f"Motion applied: {motion.plugin}")

    def _apply_semantic_config(self, announce: bool = True) -> None:
        semantics = self._controller.set_semantic_profile(
            mapping_path=self._semantic_mapping_model.as_string.strip() or None,
            label_attribute=self._semantic_label_model.as_string.strip(),
            background_id=self._int_value(
                self._semantic_background_model, "background ID"
            ),
            options=self._json_object(
                self._semantic_options_model, "semantic options"
            ),
        )
        if announce:
            self._set_status(
                f"Semantic profile applied: label={semantics.label_attribute}"
            )

    def _apply_all_configuration(self) -> None:
        self._apply_render_config(announce=False)
        self._apply_capture_config(announce=False)
        self._apply_execution_config(announce=False)
        self._apply_motion_config(announce=False)
        self._apply_semantic_config(announce=False)

    def _sync_project_header(self) -> None:
        project = self._controller.project
        if project is None:
            raise RuntimeError("create or open a project first")
        values = {
            "project_id": self._project_id_model.as_string.strip(),
            "name": self._project_name_model.as_string.strip(),
            "usd_path": self._usd_path_model.as_string.strip(),
            "output_root": self._output_root_model.as_string.strip(),
        }
        if not values["project_id"] or not values["name"]:
            raise ValueError("Project ID and name must not be empty")
        changed = (
            project.project_id != values["project_id"]
            or project.name != values["name"]
            or project.stage.usd_path != values["usd_path"]
            or project.output.root_dir != values["output_root"]
        )
        project.project_id = values["project_id"]
        project.name = values["name"]
        project.stage.usd_path = values["usd_path"]
        project.output.root_dir = values["output_root"]
        if changed:
            self._controller.dirty = True

    def _prepare_project(self) -> None:
        self._sync_project_header()
        self._apply_all_configuration()

    def _persist_project(self) -> Path:
        destination = self._controller.save_project(
            self._controller.project_dir
            or Path(self._project_dir_model.as_string)
        )
        self._project_dir_model.set_value(str(destination))
        self._set_status(f"Saved project to {destination}")
        self._refresh_summaries()
        return destination

    def _on_apply_render_config(self) -> None:
        try:
            self._apply_render_config()
        except Exception as exc:
            self._set_error("apply render profile", exc)

    def _on_apply_capture_config(self) -> None:
        try:
            self._apply_capture_config()
        except Exception as exc:
            self._set_error("apply capture schedule", exc)

    def _on_apply_execution_config(self) -> None:
        try:
            self._apply_execution_config()
        except Exception as exc:
            self._set_error("apply execution policy", exc)

    def _on_apply_motion_config(self) -> None:
        try:
            self._apply_motion_config()
        except Exception as exc:
            self._set_error("apply motion", exc)

    def _on_apply_semantic_config(self) -> None:
        try:
            self._apply_semantic_config()
        except Exception as exc:
            self._set_error("apply semantic profile", exc)

    def _load_configuration_models(self) -> None:
        project = self._controller.project
        if project is None:
            return
        render = project.render
        self._renderer_model.set_value(render.renderer)
        self._resolution_width_model.set_value(str(render.resolution_width))
        self._resolution_height_model.set_value(str(render.resolution_height))
        self._warmup_frames_model.set_value(str(render.warmup_frames))
        self._rt_subframes_model.set_value(str(render.rt_subframes))
        self._spp_per_frame_model.set_value(str(render.spp_per_frame))
        self._total_spp_model.set_value(str(render.total_spp))
        self._max_bounces_model.set_value(str(render.max_bounces))
        self._denoiser_model.set_value(render.denoiser)
        self._render_settings_model.set_value(
            json.dumps(render.settings, ensure_ascii=False, sort_keys=True)
        )
        capture = project.capture
        self._physics_hz_model.set_value(str(capture.physics_hz))
        self._capture_fps_model.set_value(str(capture.capture_fps))
        self._start_frame_model.set_value(str(capture.start_frame))
        self._frame_count_model.set_value(str(capture.frame_count))
        self._capture_initial_frame_model.set_value(
            capture.capture_initial_frame
        )
        self._segment_frames_model.set_value(str(capture.segment_frames))
        execution = project.execution
        self._segmentation_strategy_model.set_value(
            execution.segmentation_strategy
        )
        self._heartbeat_timeout_model.set_value(
            str(execution.heartbeat_timeout_seconds)
        )
        self._no_progress_timeout_model.set_value(
            str(execution.no_progress_timeout_seconds)
        )
        self._segment_start_timeout_model.set_value(
            str(execution.segment_start_timeout_seconds)
        )
        self._graceful_stop_timeout_model.set_value(
            str(execution.graceful_stop_timeout_seconds)
        )
        self._telemetry_interval_model.set_value(
            str(execution.telemetry_interval_seconds)
        )
        motion = project.motion
        self._motion_plugin_model.set_value(motion.plugin)
        self._motion_source_model.set_value(motion.source_path or "")
        self._motion_absolute_seek_model.set_value(
            motion.supports_absolute_seek
        )
        self._motion_options_model.set_value(
            json.dumps(motion.options, ensure_ascii=False, sort_keys=True)
        )
        semantics = project.semantics
        self._semantic_mapping_model.set_value(semantics.mapping_path or "")
        self._semantic_label_model.set_value(semantics.label_attribute)
        self._semantic_background_model.set_value(str(semantics.background_id))
        self._semantic_options_model.set_value(
            json.dumps(semantics.options, ensure_ascii=False, sort_keys=True)
        )

    def _validate(self) -> None:
        try:
            self._prepare_project()
            issues = self._controller.validate()
            if issues:
                self._set_status("\n".join(str(issue) for issue in issues))
            else:
                self._set_status("Validation passed")
        except Exception as exc:
            self._set_error("validate", exc)

    def _preflight(self) -> None:
        try:
            self._prepare_project()
            summary = self._controller.preflight_summary()
            estimate = summary["estimate"]
            lines = [
                "READY" if summary["can_run"] else "BLOCKED",
                (
                    f"{estimate['capture_groups']} capture groups, "
                    f"~{estimate['artifact_files']} files, "
                    f"~{estimate['estimated_gib']:.2f} GiB"
                ),
                (
                    f"{estimate['enabled_sensors']} sensor(s), "
                    f"{estimate['enabled_variants']} variant(s), "
                    f"{estimate['simulated_duration_seconds']:.1f}s simulated"
                ),
                f"Stage indexed: {summary['stage_indexed']}",
                (
                    f"Disk free: {summary['disk'].get('free_bytes', 0) / (1024 ** 3):.2f} GiB"
                    if summary["disk"].get("available")
                    else "Disk check unavailable"
                ),
            ]
            lines.extend(
                (
                    f"CAP {item['sensor_id']}: {item['plugin_id']}@"
                    f"{item['plugin_version']} | "
                    f"time={item['capabilities'].get('time_model', 'unknown')} | "
                    f"continuous={item['capabilities'].get('requires_continuous_history', False)}"
                )
                for item in summary["sensor_capabilities"]
            )
            lines.extend(
                f"[{item['severity']}] {item['path']}: {item['message']}"
                for item in summary["issues"]
            )
            self._preflight_model.set_value("\n".join(lines))
            self._set_status("Preflight ready" if summary["can_run"] else "Preflight blocked")
        except Exception as exc:
            self._set_error("preflight", exc)

    def _require_preflight_ready(self) -> None:
        summary = self._controller.preflight_summary()
        if not summary["can_run"]:
            problems = "; ".join(
                f"{item['path']}: {item['message']}"
                for item in summary["issues"]
                if item["severity"] == "error"
            )
            raise RuntimeError(f"preflight blocked: {problems}")

    def _compile_job(self) -> None:
        try:
            self._prepare_project()
            if self._controller.dirty:
                self._persist_project()
            job = self._controller.compile_job()
            self._last_job_id_model.set_value(job.job_id)
            self._set_status(
                f"Compiled {job.job_id}\nDigest: {job.content_digest}"
            )
        except ValidationFailed as exc:
            self._set_status("\n".join(str(issue) for issue in exc.issues))
        except Exception as exc:
            self._set_error("compile JobSpec", exc)

    def _run_headless_and_exit(self) -> None:
        try:
            self._prepare_project()
            self._require_preflight_ready()
            if self._controller.dirty:
                self._persist_project()
            status = self._controller.run_headless(
                self._last_job_id_model.as_string or None
            )
            self._last_job_id_model.set_value(status.job_id)
            self._set_status(
                f"Launched {status.job_id} (PID {status.pid}); closing Studio"
            )
            self._spawn(self._quit_after_launch())
        except ValidationFailed as exc:
            self._set_status("\n".join(str(issue) for issue in exc.issues))
        except Exception as exc:
            self._set_error("run headless", exc)

    async def _quit_after_launch(self) -> None:
        await omni.kit.app.get_app().next_update_async()
        omni.kit.app.get_app().post_quit(0)

    def _run_headless_monitor(self) -> None:
        try:
            self._prepare_project()
            self._require_preflight_ready()
            if self._controller.dirty:
                self._persist_project()
            status = self._controller.run_headless(
                self._last_job_id_model.as_string or None
            )
            self._last_job_id_model.set_value(status.job_id)
            self._set_status(f"Launched {status.job_id}; monitoring in Studio")
            self._spawn(self._monitor_job(status.job_id))
        except ValidationFailed as exc:
            self._set_status("\n".join(str(issue) for issue in exc.issues))
        except Exception as exc:
            self._set_error("run and monitor", exc)

    async def _monitor_job(self, job_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                status = self._controller.job_status(
                    job_id, Path(self._output_root_model.as_string)
                )
                self._set_status(
                    self._job_status_text(status)
                )
                if status.state in {"completed", "failed", "cancelled"}:
                    self._tail_logs()
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._set_error("monitor job", exc)

    def _refresh_job_status(self) -> None:
        try:
            status = self._controller.job_status(
                self._last_job_id_model.as_string,
                Path(self._output_root_model.as_string),
            )
            self._set_status(
                self._job_status_text(status)
            )
        except Exception as exc:
            self._set_error("refresh status", exc)

    def _stop_job(self) -> None:
        try:
            status = self._controller.stop_job(
                self._last_job_id_model.as_string,
                Path(self._output_root_model.as_string),
            )
            self._set_status(f"Stop requested for {status.job_id}")
        except Exception as exc:
            self._set_error("stop job", exc)

    def _resume_job(self) -> None:
        try:
            status = self._controller.resume_job(
                self._last_job_id_model.as_string,
                Path(self._output_root_model.as_string),
            )
            self._set_status(f"Resumed {status.job_id} with PID {status.pid}")
        except Exception as exc:
            self._set_error("resume job", exc)

    def _tail_logs(self) -> None:
        try:
            lines = self._controller.tail_job_logs(
                self._last_job_id_model.as_string,
                Path(self._output_root_model.as_string),
                lines=30,
            )
            self._log_tail_model.set_value("".join(lines) or "No Runtime log yet")
        except Exception as exc:
            self._set_error("tail logs", exc)

    def _refresh_job_history(self) -> None:
        try:
            self._prepare_project()
            jobs = self._controller.list_jobs()
            self._job_history_model.set_value(
                "\n".join(
                    f"{item['job_id']} | {item['state']} | "
                    f"groups {item['progress']} | segments {item['segment_progress']}"
                    for item in jobs
                )
                or "No compiled or submitted jobs"
            )
            if jobs and not self._last_job_id_model.as_string:
                self._last_job_id_model.set_value(str(jobs[0]["job_id"]))
            self._set_status(f"Loaded {len(jobs)} job(s)")
        except Exception as exc:
            self._set_error("load job history", exc)

    def _refresh_segments(self) -> None:
        try:
            segments = self._controller.list_segments(
                self._last_job_id_model.as_string,
                Path(self._output_root_model.as_string),
            )
            self._job_history_model.set_value(
                "\n".join(
                    f"{item['segment_id']} | {item['state']} | "
                    f"{item.get('capture_group_current', 0)}/"
                    f"{item.get('capture_group_total', 0)} | "
                    f"frames {item.get('start_frame', '?')}.."
                    f"{item.get('end_frame_exclusive', '?')}"
                    for item in segments
                )
                or "No segment state available"
            )
            self._set_status(f"Loaded {len(segments)} segment(s)")
        except Exception as exc:
            self._set_error("load segments", exc)

    def _show_failure_report(self) -> None:
        try:
            report = self._controller.read_failure_report(
                self._last_job_id_model.as_string,
                Path(self._output_root_model.as_string),
            )
            if report is None:
                self._log_tail_model.set_value("No failure report")
                self._set_status("This job has no failure report")
                return
            self._log_tail_model.set_value(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            self._set_status(f"Loaded failure report: {report['path']}")
        except Exception as exc:
            self._set_error("load failure report", exc)

    @staticmethod
    def _job_status_text(status: Any) -> str:
        segment = (
            f"segment {status.segment_current}/{status.segment_total}"
            + (f" ({status.current_segment_id})" if status.current_segment_id else "")
        )
        gpu = (
            ""
            if status.gpu_memory_used_mb is None
            else f" | GPU {status.gpu_memory_used_mb} MiB"
        )
        eta = (
            ""
            if status.estimated_remaining_seconds is None
            else f" | ETA {status.estimated_remaining_seconds:.0f}s"
        )
        return (
            f"{status.job_id}: {status.state} | groups "
            f"{status.frame_current}/{status.frame_total} | {segment}{gpu}{eta}\n"
            f"{status.message}"
        )

    def _refresh_summaries(self) -> None:
        project = self._controller.project
        if project is None:
            self._sensor_summary_model.set_value("No sensors")
            self._rig_summary_model.set_value("No rigs")
            self._variant_summary_model.set_value("No project")
            self._modality_summary_model.set_value("No project")
            return
        self._sensor_summary_model.set_value(
            "\n".join(
                f"{sensor.sensor_id} [{'on' if sensor.enabled else 'off'}]: "
                f"{sensor.plugin}@{sensor.plugin_version or 'uncompiled'} | "
                f"{sensor.prim_path} | sync={sensor.sync_group_id or sensor.sensor_id}; "
                f"sources={sensor.parameter_sources}"
                for sensor in project.sensors
            )
            or "No sensors"
        )
        self._rig_summary_model.set_value(
            "\n".join(
                f"{rig.rig_id} [{'on' if rig.enabled else 'off'}]: "
                f"{', '.join(rig.sensor_ids)} | {rig.sync_policy} | "
                f"reference={rig.reference_frame_prim_path or 'none'}"
                for rig in project.rigs
            )
            or "No rigs"
        )
        self._variant_summary_model.set_value(
            "\n".join(
                f"{variant.variant_id} [{'on' if variant.enabled else 'off'}]: "
                f"{variant.strategy}"
                for variant in project.variants
            )
            or "No variants"
        )
        rows = []
        for variant in project.variants:
            for sensor_id, modalities in variant.modalities_by_sensor.items():
                rows.append(
                    f"{variant.variant_id} × {sensor_id}: {', '.join(modalities)}"
                )
        self._modality_summary_model.set_value("\n".join(rows) or "No bindings")
        state = "modified" if self._controller.dirty else "saved"
        self._project_state_model.set_value(
            f"Schema {project.schema_version} | {state} | "
            f"{self._controller.project_dir or 'not saved'}"
            + (
                f" | {self._controller.migration_notice}"
                if self._controller.migration_notice
                else ""
            )
        )

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.append(task)
        task.add_done_callback(
            lambda completed: self._tasks.remove(completed)
            if completed in self._tasks
            else None
        )

    def _schedule_dock(self) -> None:
        async def dock() -> None:
            await omni.kit.app.get_app().next_update_async()
            viewport = ui.Workspace.get_window("Viewport")
            if viewport and self._window:
                self._window.dock_in(viewport, ui.DockPosition.LEFT, 0.3)

        self._spawn(dock())

    def _set_status(self, message: str) -> None:
        self._status_model.set_value(message)
        carb.log_info(f"[semantic_world_v04] {message}")

    def _set_error(self, operation: str, exc: Exception) -> None:
        message = f"{operation} failed: {exc}"
        self._status_model.set_value(message)
        carb.log_error(f"[semantic_world_v04] {message}")
