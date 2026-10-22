"""Task-oriented v04.4 Kit window for Semantic Capture Studio."""

import asyncio
import gc
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import carb
import omni.kit.app
import omni.ui as ui
import omni.usd

from semantic_world_v04.core.errors import ValidationFailed
from semantic_world_v04.project.paths import ProjectPathResolver
from semantic_world_v04.stage.omni_adapter import (
    OmniStageService,
    SessionVisibilityController,
)
from semantic_world_v04.studio import RecentProjectStore, StudioController

from .file_dialogs import FileDialogController


WINDOW_TITLE = "Semantic Capture Studio"
PAGE_NAMES = (
    "1 Project & Stage",
    "2 Sensors",
    "3 Variants",
    "4 Capture Outputs",
    "5 Render & Frames",
    "6 Review & Run",
    "Advanced",
)

BASIC_CAMERA_MODALITIES = (
    ("rgb", "RGB", "PNG"),
    ("depth_linear", "Depth Data", "NPY"),
    ("depth_color", "Depth Color", "PNG"),
    ("semantic_id", "Semantic ID", "NPY"),
    ("semantic_color", "Semantic Color", "PNG"),
)


class StudioWindow:
    def __init__(self) -> None:
        self.controller = StudioController()
        self.stage_service = OmniStageService()
        self.file_dialogs = FileDialogController()
        self.recent_projects = RecentProjectStore(
            Path.home() / ".semantic_world_v04" / "recent_projects.json"
        )
        self._visibility: Optional[SessionVisibilityController] = None
        self._tasks: List[asyncio.Task] = []
        self._dynamic_models: List[Any] = []
        self._page_index = 0
        self._active_sensor_id = ""
        self._init_models()
        self.window = ui.Window(
            WINDOW_TITLE,
            width=980,
            height=860,
            visible=True,
            dockPreference=ui.DockPreference.LEFT,
        )
        self.window.frame.set_build_fn(self._build_ui)
        self.window.frame.rebuild()

    def shutdown(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks = []
        self.file_dialogs.shutdown()
        if self._visibility is not None:
            self._visibility.clear()
        self._visibility = None
        self.window = None
        self.controller = None
        self.stage_service = None
        gc.collect()

    def _init_models(self) -> None:
        self._status_model = ui.SimpleStringModel("Ready")
        self._dirty_model = ui.SimpleStringModel("No project open")
        self._project_state_model = ui.SimpleStringModel("Schema 2 | not saved")
        self._stage_summary_model = ui.SimpleStringModel("No Stage indexed")
        self._project_dir_model = ui.SimpleStringModel(
            "/root/gpufree-data/semantic/projects/new_capture.swproject"
        )
        self._project_id_model = ui.SimpleStringModel("semantic-capture-project")
        self._project_name_model = ui.SimpleStringModel("Semantic Capture Project")
        self._usd_path_model = ui.SimpleStringModel("")
        self._output_root_model = ui.SimpleStringModel(
            "/root/gpufree-data/semantic/output"
        )
        self._stage_search_model = ui.SimpleStringModel("")
        self._stage_results_model = ui.SimpleStringModel("No search results")
        self._prim_path_model = ui.SimpleStringModel("")
        self._sensor_search_model = ui.SimpleStringModel("")
        self._sensor_details_model = ui.SimpleStringModel(
            "Open a Stage to discover sensors"
        )
        self._variant_selection_model = ui.SimpleStringModel("")
        self._variant_keep_lights_model = ui.SimpleBoolModel(True)
        self._variant_summary_model = ui.SimpleStringModel("No project")
        self._capture_summary_model = ui.SimpleStringModel("No project")

        self._renderer_model = ui.SimpleStringModel("PathTracing")
        self._resolution_width_model = ui.SimpleStringModel("1280")
        self._resolution_height_model = ui.SimpleStringModel("720")
        self._warmup_frames_model = ui.SimpleStringModel("16")
        self._rt_subframes_model = ui.SimpleStringModel("1")
        self._spp_per_frame_model = ui.SimpleStringModel("8")
        self._total_spp_model = ui.SimpleStringModel("64")
        self._max_bounces_model = ui.SimpleStringModel("4")
        self._denoiser_model = ui.SimpleBoolModel(True)
        self._render_settings_model = ui.SimpleStringModel("{}")

        self._physics_hz_model = ui.SimpleStringModel("60")
        self._capture_fps_model = ui.SimpleStringModel("10")
        self._start_frame_model = ui.SimpleStringModel("0")
        self._frame_count_model = ui.SimpleStringModel("1")
        self._capture_initial_frame_model = ui.SimpleBoolModel(True)
        self._segment_frames_model = ui.SimpleStringModel("100")

        self._segmentation_strategy_model = ui.SimpleStringModel("auto")
        self._heartbeat_timeout_model = ui.SimpleStringModel("120")
        self._no_progress_timeout_model = ui.SimpleStringModel("600")
        self._segment_start_timeout_model = ui.SimpleStringModel("300")
        self._graceful_stop_timeout_model = ui.SimpleStringModel("30")
        self._telemetry_interval_model = ui.SimpleStringModel("5")

        self._motion_plugin_model = ui.SimpleStringModel("none")
        self._motion_source_model = ui.SimpleStringModel("")
        self._motion_absolute_seek_model = ui.SimpleBoolModel(False)
        self._motion_options_model = ui.SimpleStringModel("{}")
        self._semantic_mapping_model = ui.SimpleStringModel("")
        self._semantic_label_model = ui.SimpleStringModel("class")
        self._semantic_background_model = ui.SimpleStringModel("0")
        self._semantic_options_model = ui.SimpleStringModel("{}")

        self._sensor_override_model = ui.SimpleStringModel("{}")
        self._sensor_advanced_model = ui.SimpleStringModel("No sensor selected")
        self._rig_id_model = ui.SimpleStringModel("rig_01")
        self._rig_sensors_model = ui.SimpleStringModel("")
        self._rig_reference_model = ui.SimpleStringModel("")
        self._rig_summary_model = ui.SimpleStringModel("No rigs")
        self._plugin_details_model = ui.SimpleStringModel("Plugin catalog not loaded")

        self._review_model = ui.SimpleStringModel("Open or create a project")
        self._preflight_model = ui.SimpleStringModel("Preflight not run")
        self._job_id_model = ui.SimpleStringModel("")
        self._job_history_model = ui.SimpleStringModel("No job history loaded")
        self._log_tail_model = ui.SimpleStringModel("No Runtime log loaded")

    def _build_ui(self) -> None:
        self._dynamic_models = []
        # The root stack must occupy the complete Window frame.  Giving it a
        # zero-pixel height collapses the flexible page area into a thin line
        # and leaves the rest of the Window unassigned.
        with ui.VStack(spacing=6) as root_stack:
            self._root_stack = root_stack
            self._build_header()
            self._build_navigation()
            ui.Separator()
            with ui.ScrollingFrame(
                height=ui.Fraction(1),
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
            ) as page_scroll:
                self._page_scroll = page_scroll
                with ui.VStack(spacing=8, height=0):
                    builders = (
                        self._build_project_page,
                        self._build_sensors_page,
                        self._build_variants_page,
                        self._build_capture_page,
                        self._build_render_page,
                        self._build_review_page,
                        self._build_advanced_page,
                    )
                    builders[self._page_index]()
                    ui.Spacer(height=12)
            ui.Separator()
            with ui.HStack(height=48, spacing=6):
                ui.Label("Status", width=70)
                ui.StringField(
                    model=self._status_model,
                    read_only=True,
                    multiline=True,
                )

    def _build_header(self) -> None:
        with ui.HStack(height=32, spacing=8):
            ui.Label("Semantic Capture Studio v04.4", width=230)
            ui.Label(PAGE_NAMES[self._page_index], width=180)
            ui.StringField(model=self._dirty_model, read_only=True)
            ui.Button("Save", width=70, clicked_fn=self._save_project)

    def _build_navigation(self) -> None:
        with ui.HStack(height=30, spacing=3):
            for index, name in enumerate(PAGE_NAMES):
                ui.Button(
                    ("● " if index == self._page_index else "") + name,
                    clicked_fn=lambda value=index: self._set_page(value),
                )

    def _set_page(self, index: int) -> None:
        if index == self._page_index:
            return
        if self.controller.project is not None:
            try:
                self._prepare_project()
            except Exception as exc:
                self._set_error("preserve page edits", exc)
                return
        self._page_index = index
        self._rebuild()

    def _build_project_page(self) -> None:
        ui.Label("Project & Stage", height=30)
        ui.Label(
            "Open an existing .swproject, or choose a new project location and "
            "USD Stage before creating it. Invalid drafts are never written to disk.",
            word_wrap=True,
            height=42,
        )
        with ui.HStack(height=30, spacing=4):
            ui.Label("Project directory", width=190)
            ui.StringField(model=self._project_dir_model)
            ui.Button("Open Existing…", width=125, clicked_fn=self._browse_project)
            ui.Button(
                "Choose New Parent…",
                width=145,
                clicked_fn=self._browse_new_project_parent,
            )
        self._labeled_string("Project ID", self._project_id_model)
        self._labeled_string("Name", self._project_name_model)
        self._path_row(
            "USD Stage",
            self._usd_path_model,
            self._browse_usd,
            "Choose USD…",
        )
        self._path_row(
            "Output root", self._output_root_model, self._browse_output, "Browse…"
        )
        ui.StringField(model=self._project_state_model, read_only=True)
        with ui.HStack(height=30, spacing=4):
            ui.Button("Create New Project", clicked_fn=self._new_project)
            ui.Button("Open Entered Project", clicked_fn=self._open_project)
            ui.Button("Save Project", clicked_fn=self._save_project)
            ui.Button("Save Project As", clicked_fn=self._save_project_as)
            ui.Button("Open / Reload USD", clicked_fn=self._open_stage)
            ui.Button("Close USD", clicked_fn=self._close_stage)

        recent = self.recent_projects.list(existing_only=True)
        with ui.CollapsableFrame("Recent Projects", collapsed=not bool(recent), height=0):
            with ui.VStack(spacing=3, height=0):
                if not recent:
                    ui.Label("No recent project", height=24)
                for item in recent:
                    label = item.get("name") or Path(item["path"]).name
                    with ui.HStack(height=28, spacing=4):
                        ui.Button(
                            f"Open {label}",
                            width=220,
                            clicked_fn=lambda path=item["path"]: self._open_recent(path),
                        )
                        ui.Label(item["path"], word_wrap=False)

        with ui.CollapsableFrame("Stage Browser", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                ui.StringField(model=self._stage_summary_model, read_only=True)
                self._labeled_string("Search Stage", self._stage_search_model)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Search", clicked_fn=self._search_stage)
                    ui.Button("Refresh index", clicked_fn=self._refresh_stage_index)
                    ui.Button("Locate path", clicked_fn=self._locate_prim)
                self._labeled_string("Prim path", self._prim_path_model)
                ui.StringField(
                    model=self._stage_results_model,
                    read_only=True,
                    multiline=True,
                    height=130,
                )

    def _build_sensors_page(self) -> None:
        ui.Label("Choose Sensors", height=30)
        ui.Label(
            "Compatible USD sensors are detected automatically. Check a row to "
            "add or enable it; uncheck to disable it without losing configuration.",
            word_wrap=True,
            height=42,
        )
        with ui.HStack(height=28, spacing=4):
            ui.Label("Search", width=80)
            ui.StringField(model=self._sensor_search_model)
            ui.Button("Refresh", width=90, clicked_fn=self._rebuild)

        if self.controller.project is None:
            ui.Label("Create or open a project first.", height=28)
            return
        if self.controller.stage_index is None:
            ui.Label("Open the project USD Stage first.", height=28)
            return
        candidates = self.controller.discover_sensor_candidates()
        needle = self._sensor_search_model.as_string.strip().casefold()
        if needle:
            candidates = [
                item
                for item in candidates
                if needle in item["prim_path"].casefold()
                or needle in item["plugin_display_name"].casefold()
            ]
        if not candidates:
            ui.Label("No compatible sensor Prim found.", height=28)
        for item in candidates:
            with ui.CollapsableFrame(
                f"{item['prim_name']} — {item['plugin_display_name']}",
                collapsed=True,
                height=0,
            ):
                with ui.VStack(spacing=3, height=0):
                    with ui.HStack(height=28, spacing=5):
                        model = self._bool_model(
                            item["enabled"],
                            lambda value, row=item: self._toggle_sensor_candidate(
                                row, value
                            ),
                        )
                        ui.CheckBox(model=model, width=24)
                        ui.Label(
                            "Use in capture" if item["enabled"] else "Not enabled",
                            width=120,
                        )
                        ui.Button(
                            "Locate",
                            width=80,
                            clicked_fn=lambda path=item["prim_path"]: self._locate_path(
                                path
                            ),
                        )
                        ui.Button(
                            "Details",
                            width=80,
                            clicked_fn=lambda row=item: self._show_sensor_candidate(row),
                        )
                    ui.Label(f"Prim: {item['prim_path']}", word_wrap=True, height=34)
                    ui.Label(
                        "Outputs: " + ", ".join(item["supported_modalities"]),
                        word_wrap=True,
                        height=38,
                    )
                    if item["sensor_ids"]:
                        ui.Label(
                            "Sensor ID: " + ", ".join(item["sensor_ids"]),
                            height=24,
                        )
        ui.Separator()
        ui.Label("Selected sensor details", height=26)
        ui.StringField(
            model=self._sensor_details_model,
            read_only=True,
            multiline=True,
            height=180,
        )

    def _build_variants_page(self) -> None:
        ui.Label("Scene Variants", height=30)
        ui.Label(
            "A Variant defines scene visibility. Use the standard Stage tree or "
            "Viewport selection, then create an isolate Variant without typing a Prim path.",
            word_wrap=True,
            height=44,
        )
        if self.controller.project is None:
            ui.Label("Create or open a project first.")
            return
        with ui.CollapsableFrame("Create from current Stage selection", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._labeled_string(
                    "Selected Prim paths", self._variant_selection_model, read_only=True
                )
                with ui.HStack(height=28, spacing=5):
                    ui.Button(
                        "Use current selection",
                        clicked_fn=self._read_variant_selection,
                    )
                    ui.Button(
                        "Create Isolate Variant",
                        clicked_fn=self._create_variant_from_selection,
                    )
                    ui.Button("Clear preview", clicked_fn=self._clear_variant_preview)
                self._labeled_bool("Keep all Stage lights", self._variant_keep_lights_model)
                ui.Label(
                    "The Variant ID is generated automatically from the first selected Prim.",
                    word_wrap=True,
                    height=30,
                )

        for variant in self.controller.project.variants:
            with ui.CollapsableFrame(variant.variant_id, collapsed=True, height=0):
                with ui.VStack(spacing=3, height=0):
                    with ui.HStack(height=28, spacing=4):
                        model = self._bool_model(
                            variant.enabled,
                            lambda value, variant_id=variant.variant_id: self._toggle_variant(
                                variant_id, value
                            ),
                        )
                        ui.CheckBox(model=model, width=24)
                        ui.Label("Enabled", width=80)
                        ui.Button(
                            "Preview",
                            clicked_fn=lambda variant_id=variant.variant_id: self._preview_variant(
                                variant_id
                            ),
                        )
                        ui.Button(
                            "Duplicate",
                            clicked_fn=lambda variant_id=variant.variant_id: self._duplicate_variant(
                                variant_id
                            ),
                        )
                        if variant.variant_id != "full_scene":
                            ui.Button(
                                "Delete",
                                clicked_fn=lambda variant_id=variant.variant_id: self._delete_variant(
                                    variant_id
                                ),
                            )
                    ui.Label(f"Strategy: {variant.strategy}", height=24)
                    ui.Label(
                        "Include: " + ("; ".join(variant.include_paths) or "entire Stage"),
                        word_wrap=True,
                        height=38,
                    )
                    ui.Label(
                        "Protected: "
                        + ("; ".join(variant.protected_paths) or "registered sensors"),
                        word_wrap=True,
                        height=38,
                    )

    def _build_capture_page(self) -> None:
        ui.Label("Capture Outputs", height=30)
        ui.Label(
            "Select a sensor, enable the scene Variants it should capture, then "
            "check every output artifact independently.",
            word_wrap=True,
            height=42,
        )
        if self.controller.project is None:
            ui.Label("Create or open a project first.")
            return
        sensors = [item for item in self.controller.project.sensors if item.enabled]
        if not sensors:
            ui.Label("Enable at least one sensor on the Sensors page.")
            return
        if not self._active_sensor_id or self._active_sensor_id not in {
            item.sensor_id for item in sensors
        }:
            self._active_sensor_id = sensors[0].sensor_id
        with ui.HStack(height=30, spacing=4):
            ui.Label("Sensor", width=70)
            for sensor in sensors:
                ui.Button(
                    ("● " if sensor.sensor_id == self._active_sensor_id else "")
                    + sensor.sensor_id,
                    clicked_fn=lambda sensor_id=sensor.sensor_id: self._select_capture_sensor(
                        sensor_id
                    ),
                )
        matrix = self.controller.capture_matrix(self._active_sensor_id)
        supported = set(matrix["supported_modalities"])
        with ui.HStack(height=28, spacing=3):
            ui.Label("Apply to enabled rows", width=155)
            ui.Button(
                "RGB + Semantics",
                clicked_fn=lambda: self._apply_capture_preset("rgb_semantics"),
            )
            ui.Button(
                "Depth Complete",
                clicked_fn=lambda: self._apply_capture_preset("depth_complete"),
            )
            ui.Button(
                "All Common",
                clicked_fn=lambda: self._apply_capture_preset("common_all"),
            )
            ui.Button(
                "Semantic Only",
                clicked_fn=lambda: self._apply_capture_preset("semantic_only"),
            )
            ui.Button(
                "Clear", clicked_fn=lambda: self._apply_capture_preset("none")
            )

        self._build_capture_header()
        for row in matrix["rows"]:
            self._build_capture_row(row, supported)

        advanced = [
            item
            for item in matrix["supported_modalities"]
            if item not in {entry[0] for entry in BASIC_CAMERA_MODALITIES}
        ]
        with ui.CollapsableFrame("More outputs", collapsed=True, height=0):
            with ui.VStack(spacing=3, height=0):
                if not advanced:
                    ui.Label("No additional output from this sensor plugin.")
                for row in matrix["rows"]:
                    if not row["variant_enabled"]:
                        continue
                    with ui.HStack(height=28, spacing=4):
                        ui.Label(row["variant_id"], width=190)
                        for modality in advanced:
                            selected = modality in row["selected_modalities"]
                            model = self._bool_model(
                                selected,
                                lambda value, variant_id=row["variant_id"], modality_id=modality: self._toggle_modality(
                                    variant_id, modality_id, value
                                ),
                            )
                            ui.CheckBox(
                                model=model,
                                enabled=row["binding_enabled"],
                                width=24,
                            )
                            ui.Label(modality, width=150)

    def _build_capture_header(self) -> None:
        with ui.HStack(height=46, spacing=3):
            ui.Label("Scene Variant", width=190)
            ui.Label("Use", width=45)
            for _modality, label, suffix in BASIC_CAMERA_MODALITIES:
                ui.Label(f"{label}\n{suffix}", width=115, word_wrap=True)

    def _build_capture_row(self, row: Dict[str, Any], supported: set) -> None:
        enabled = bool(row["binding_enabled"])
        with ui.HStack(height=34, spacing=3):
            ui.Label(row["variant_id"], width=190)
            binding_model = self._bool_model(
                enabled,
                lambda value, variant_id=row["variant_id"]: self._toggle_binding(
                    variant_id, value
                ),
            )
            ui.CheckBox(
                model=binding_model,
                enabled=row["variant_enabled"],
                width=45,
            )
            for modality_id, _label, _suffix in BASIC_CAMERA_MODALITIES:
                selected = modality_id in row["selected_modalities"]
                supported_here = modality_id in supported
                model = self._bool_model(
                    selected,
                    lambda value, variant_id=row["variant_id"], modality=modality_id: self._toggle_modality(
                        variant_id, modality, value
                    ),
                )
                ui.CheckBox(
                    model=model,
                    enabled=(
                        enabled and row["variant_enabled"] and supported_here
                    ),
                    width=115,
                )

    def _build_render_page(self) -> None:
        ui.Label("Render & Frames", height=30)
        ui.Label(
            "New projects default to Path Tracing production quality. Realtime and "
            "low-SPP presets remain explicit diagnostic choices.",
            word_wrap=True,
            height=42,
        )
        if self.controller.project is None:
            ui.Label("Create or open a project first.")
            return
        current = self.controller.current_render_preset_id()
        with ui.CollapsableFrame("Render Presets", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                for preset in self.controller.render_presets():
                    marker = "● " if current == preset["preset_id"] else ""
                    with ui.HStack(height=28, spacing=4):
                        ui.Button(
                            marker + preset["display_name"],
                            width=260,
                            clicked_fn=lambda preset_id=preset["preset_id"]: self._apply_render_preset(
                                preset_id
                            ),
                        )
                        ui.Label(preset["description"])
                if current == "custom":
                    ui.Label("● Custom render settings", height=24)

        with ui.CollapsableFrame("Render Details", collapsed=False, height=0):
            with ui.VStack(spacing=3, height=0):
                self._labeled_string("Renderer", self._renderer_model)
                self._labeled_string("Width", self._resolution_width_model)
                self._labeled_string("Height", self._resolution_height_model)
                self._labeled_string("Warmup frames", self._warmup_frames_model)
                self._labeled_string("RT subframes", self._rt_subframes_model)
                self._labeled_string("SPP / frame", self._spp_per_frame_model)
                self._labeled_string("Total SPP", self._total_spp_model)
                self._labeled_string("Max bounces", self._max_bounces_model)
                self._labeled_bool("Denoiser", self._denoiser_model)
                self._labeled_string("Settings JSON", self._render_settings_model)
                ui.Label(
                    "Detail edits are captured when you Save, switch pages, or open Review.",
                    word_wrap=True,
                    height=30,
                )

        with ui.CollapsableFrame("Capture Schedule", collapsed=False, height=0):
            with ui.VStack(spacing=3, height=0):
                self._labeled_string("Physics Hz", self._physics_hz_model)
                self._labeled_string("Capture FPS", self._capture_fps_model)
                self._labeled_string("Start frame", self._start_frame_model)
                self._labeled_string("Frame count", self._frame_count_model)
                self._labeled_bool(
                    "Capture initial frame", self._capture_initial_frame_model
                )
                self._labeled_string("Segment frames", self._segment_frames_model)

    def _build_review_page(self) -> None:
        ui.Label("Review & Run", height=30)
        if self.controller.project is None:
            ui.Label("Create or open a project first.")
            return
        try:
            self._prepare_project()
            self._refresh_review()
        except Exception as exc:
            self._review_model.set_value(f"Configuration error: {exc}")
        ui.StringField(
            model=self._review_model,
            read_only=True,
            multiline=True,
            height=230,
        )
        with ui.HStack(height=30, spacing=4):
            ui.Button("Validate", clicked_fn=self._validate)
            ui.Button("Preflight", clicked_fn=self._preflight)
            ui.Button("Save", clicked_fn=self._save_project)
            ui.Button("Compile JobSpec", clicked_fn=self._compile_job)
        ui.StringField(
            model=self._preflight_model,
            read_only=True,
            multiline=True,
            height=130,
        )
        self._labeled_string("Job ID", self._job_id_model)
        with ui.HStack(height=32, spacing=4):
            ui.Button("Run Headless & Exit", clicked_fn=self._run_headless_and_exit)
            ui.Button("Run + Monitor", clicked_fn=self._run_headless_monitor)
            ui.Button("Refresh", clicked_fn=self._refresh_job_status)
            ui.Button("Stop", clicked_fn=self._stop_job)
            ui.Button("Resume", clicked_fn=self._resume_job)
        with ui.HStack(height=30, spacing=4):
            ui.Button("Tail Logs", clicked_fn=self._tail_logs)
            ui.Button("Job History", clicked_fn=self._refresh_job_history)
            ui.Button("Segments", clicked_fn=self._refresh_segments)
            ui.Button("Failure Report", clicked_fn=self._show_failure_report)
        ui.StringField(
            model=self._job_history_model,
            read_only=True,
            multiline=True,
            height=120,
        )
        ui.StringField(
            model=self._log_tail_model,
            read_only=True,
            multiline=True,
            height=130,
        )
        ui.Label(
            "Production recommendation: Run Headless & Exit. The Job Runner and "
            "Segment Workers continue after this Kit editor closes.",
            word_wrap=True,
            height=42,
        )

    def _build_advanced_page(self) -> None:
        ui.Label("Advanced Settings", height=30)
        ui.Label(
            "These controls are optional. Common project creation and capture do not "
            "require editing JSON or plugin IDs.",
            word_wrap=True,
            height=42,
        )
        if self.controller.project is None:
            ui.Label("Create or open a project first.")
            return
        with ui.CollapsableFrame("Sensor Overrides", collapsed=False, height=0):
            with ui.VStack(spacing=4, height=0):
                self._build_sensor_selector_buttons()
                self._labeled_string("Overrides JSON", self._sensor_override_model)
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Load", clicked_fn=self._load_sensor_override)
                    ui.Button("Save Override", clicked_fn=self._save_sensor_override)
                    ui.Button("Clear Override", clicked_fn=self._clear_sensor_override)
                    ui.Button("Delete Sensor", clicked_fn=self._delete_active_sensor)
                ui.StringField(
                    model=self._sensor_advanced_model,
                    read_only=True,
                    multiline=True,
                    height=130,
                )

        with ui.CollapsableFrame("Sensor Rigs / Sync Groups", collapsed=True, height=0):
            with ui.VStack(spacing=3, height=0):
                self._labeled_string("Rig ID", self._rig_id_model)
                self._labeled_string(
                    "Sensor IDs (; separated)", self._rig_sensors_model
                )
                self._labeled_string(
                    "Reference Prim", self._rig_reference_model
                )
                with ui.HStack(height=28, spacing=4):
                    ui.Button("Add Rig", clicked_fn=self._add_rig)
                    ui.Button("Delete Rig", clicked_fn=self._delete_rig)
                ui.StringField(
                    model=self._rig_summary_model,
                    read_only=True,
                    multiline=True,
                    height=80,
                )

        with ui.CollapsableFrame("Motion / Trajectory", collapsed=True, height=0):
            with ui.VStack(spacing=3, height=0):
                self._labeled_string("Plugin", self._motion_plugin_model)
                self._path_row(
                    "CSV source", self._motion_source_model, self._browse_csv, "Browse…"
                )
                self._labeled_bool(
                    "Supports absolute seek", self._motion_absolute_seek_model
                )
                self._labeled_string("Options JSON", self._motion_options_model)

        with ui.CollapsableFrame("Semantic Profile", collapsed=True, height=0):
            with ui.VStack(spacing=3, height=0):
                self._path_row(
                    "Mapping path",
                    self._semantic_mapping_model,
                    self._browse_semantic_mapping,
                    "Browse…",
                )
                self._labeled_string("Label attribute", self._semantic_label_model)
                self._labeled_string("Background ID", self._semantic_background_model)
                self._labeled_string("Options JSON", self._semantic_options_model)

        with ui.CollapsableFrame("Long-job Execution", collapsed=True, height=0):
            with ui.VStack(spacing=3, height=0):
                self._labeled_string(
                    "Segmentation strategy", self._segmentation_strategy_model
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

        with ui.CollapsableFrame("Plugin Catalog", collapsed=True, height=0):
            with ui.VStack(spacing=3, height=0):
                ui.Button("Refresh Catalog", clicked_fn=self._load_plugin_catalog)
                ui.StringField(
                    model=self._plugin_details_model,
                    read_only=True,
                    multiline=True,
                    height=180,
                )

    def _build_sensor_selector_buttons(self) -> None:
        sensors = self.controller.project.sensors if self.controller.project else []
        with ui.HStack(height=28, spacing=4):
            ui.Label("Sensor", width=80)
            for sensor in sensors:
                ui.Button(
                    ("● " if sensor.sensor_id == self._active_sensor_id else "")
                    + sensor.sensor_id,
                    clicked_fn=lambda sensor_id=sensor.sensor_id: self._select_advanced_sensor(
                        sensor_id
                    ),
                )

    @staticmethod
    def _labeled_string(
        label: str,
        model: ui.SimpleStringModel,
        *,
        read_only: bool = False,
    ) -> None:
        with ui.HStack(height=28, spacing=4):
            ui.Label(label, width=190)
            ui.StringField(model=model, read_only=read_only)

    @staticmethod
    def _labeled_bool(label: str, model: ui.SimpleBoolModel) -> None:
        with ui.HStack(height=28, spacing=4):
            ui.Label(label, width=190)
            ui.CheckBox(model=model, width=24)

    @staticmethod
    def _path_row(label, model, callback, button_label) -> None:
        with ui.HStack(height=28, spacing=4):
            ui.Label(label, width=190)
            ui.StringField(model=model)
            ui.Button(button_label, width=90, clicked_fn=callback)

    def _bool_model(self, value: bool, callback) -> ui.SimpleBoolModel:
        model = ui.SimpleBoolModel(bool(value))
        model.add_value_changed_fn(lambda current: callback(current.as_bool))
        self._dynamic_models.append(model)
        return model

    def _rebuild(self) -> None:
        if self.window is not None:
            self.window.frame.rebuild()

    def _defer_rebuild(self) -> None:
        self._spawn(self._rebuild_next_update())

    async def _rebuild_next_update(self) -> None:
        await omni.kit.app.get_app().next_update_async()
        self._rebuild()

    def _spawn(self, coroutine) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.append(task)

        def done(completed) -> None:
            if completed in self._tasks:
                self._tasks.remove(completed)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._set_error("asynchronous operation", exc)

        task.add_done_callback(done)

    def _set_status(self, message: str) -> None:
        self._status_model.set_value(str(message))
        self._refresh_dirty_state()

    def _set_error(self, operation: str, exc: Exception) -> None:
        message = f"Failed to {operation}: {exc}"
        carb.log_error(f"[semantic_world_v04] {message}")
        self._status_model.set_value(message)

    def _refresh_dirty_state(self) -> None:
        project = self.controller.project
        if project is None:
            self._dirty_model.set_value("No project open")
            return
        self._dirty_model.set_value(
            f"{project.name} | "
            + ("● Unsaved changes" if self.controller.dirty else "Saved")
        )

    @staticmethod
    def _int(model, name: str) -> int:
        try:
            return int(model.as_string.strip())
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc

    @staticmethod
    def _float(model, name: str) -> float:
        try:
            return float(model.as_string.strip())
        except ValueError as exc:
            raise ValueError(f"{name} must be a number") from exc

    @staticmethod
    def _json(model, name: str) -> Dict[str, Any]:
        value = json.loads(model.as_string or "{}")
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be a JSON object")
        return value

    def _sync_project_header(self) -> None:
        project = self.controller.project
        if project is None:
            raise RuntimeError("create or open a project first")
        project_id = self._project_id_model.as_string.strip()
        name = self._project_name_model.as_string.strip()
        usd_path = self._validated_usd_reference()
        output_root = self._output_root_model.as_string.strip()
        if not project_id or not name:
            raise ValueError("Project ID and name must not be empty")
        if not output_root:
            raise ValueError("Output root must not be empty")
        changed = (
            project.project_id != project_id
            or project.name != name
            or project.stage.usd_path != usd_path
            or project.output.root_dir != output_root
        )
        project.project_id = project_id
        project.name = name
        project.stage.usd_path = usd_path
        project.output.root_dir = output_root
        if changed:
            self.controller.dirty = True

    def _validated_usd_reference(self, value: Optional[str] = None) -> str:
        usd_path = (
            self._usd_path_model.as_string.strip()
            if value is None
            else str(value).strip()
        )
        if not usd_path:
            raise ValueError("Choose a USD Stage before creating or saving a project")
        path_without_query = usd_path.split("?", 1)[0].split("#", 1)[0]
        if Path(path_without_query).suffix.casefold() not in {".usd", ".usda", ".usdc"}:
            raise ValueError("USD Stage must use a .usd, .usda, or .usdc file")
        if ProjectPathResolver.is_uri(usd_path):
            return usd_path
        base = self.controller.project_dir
        if base is None:
            raw_destination = self._project_dir_model.as_string.strip()
            base = Path(raw_destination) if raw_destination else Path.cwd()
        resolved = ProjectPathResolver.resolve(usd_path, base)
        if resolved is None or not Path(resolved).is_file():
            raise FileNotFoundError(f"USD Stage does not exist: {resolved or usd_path}")
        return usd_path

    def _project_destination(
        self,
        *,
        allow_existing_current: bool,
    ) -> Path:
        raw = self._project_dir_model.as_string.strip()
        if not raw:
            raise ValueError("Choose a project directory")
        destination = Path(raw).expanduser()
        if not destination.is_absolute():
            raise ValueError("Project directory must be an absolute cloud path")
        if destination.suffix.casefold() != ".swproject":
            raise ValueError("Project directory name must end with .swproject")
        if destination.exists() and not destination.is_dir():
            raise ValueError(f"Project destination is not a directory: {destination}")
        manifest = destination / "project.json"
        if manifest.is_file():
            current = self.controller.project_dir
            same_as_current = (
                current is not None
                and destination.resolve() == Path(current).resolve()
            )
            if not (allow_existing_current and same_as_current):
                raise FileExistsError(
                    f"Project already exists: {destination}; open it or choose a new name"
                )
        return destination

    def _prepare_project(self) -> None:
        self._sync_project_header()
        self.controller.set_render_profile(
            renderer=self._renderer_model.as_string.strip(),
            resolution_width=self._int(self._resolution_width_model, "width"),
            resolution_height=self._int(self._resolution_height_model, "height"),
            warmup_frames=self._int(self._warmup_frames_model, "warmup frames"),
            rt_subframes=self._int(self._rt_subframes_model, "RT subframes"),
            spp_per_frame=self._int(self._spp_per_frame_model, "SPP / frame"),
            total_spp=self._int(self._total_spp_model, "total SPP"),
            max_bounces=self._int(self._max_bounces_model, "max bounces"),
            denoiser=self._denoiser_model.as_bool,
            settings=self._json(self._render_settings_model, "render settings"),
        )
        self.controller.set_capture_schedule(
            physics_hz=self._int(self._physics_hz_model, "physics Hz"),
            capture_fps=self._int(self._capture_fps_model, "capture FPS"),
            start_frame=self._int(self._start_frame_model, "start frame"),
            frame_count=self._int(self._frame_count_model, "frame count"),
            capture_initial_frame=self._capture_initial_frame_model.as_bool,
            segment_frames=self._int(self._segment_frames_model, "segment frames"),
        )
        self.controller.set_execution_policy(
            segmentation_strategy=self._segmentation_strategy_model.as_string.strip(),
            heartbeat_timeout_seconds=self._float(
                self._heartbeat_timeout_model, "heartbeat timeout"
            ),
            no_progress_timeout_seconds=self._float(
                self._no_progress_timeout_model, "no-progress timeout"
            ),
            segment_start_timeout_seconds=self._float(
                self._segment_start_timeout_model, "segment start timeout"
            ),
            graceful_stop_timeout_seconds=self._float(
                self._graceful_stop_timeout_model, "graceful stop timeout"
            ),
            telemetry_interval_seconds=self._float(
                self._telemetry_interval_model, "telemetry interval"
            ),
        )
        self.controller.set_motion_spec(
            plugin=self._motion_plugin_model.as_string.strip(),
            source_path=self._motion_source_model.as_string.strip() or None,
            supports_absolute_seek=self._motion_absolute_seek_model.as_bool,
            options=self._json(self._motion_options_model, "motion options"),
        )
        self.controller.set_semantic_profile(
            mapping_path=self._semantic_mapping_model.as_string.strip() or None,
            label_attribute=self._semantic_label_model.as_string.strip(),
            background_id=self._int(
                self._semantic_background_model, "background ID"
            ),
            options=self._json(self._semantic_options_model, "semantic options"),
        )
        self._refresh_dirty_state()

    def _load_project_models(self) -> None:
        project = self.controller.project
        if project is None:
            return
        self._project_id_model.set_value(project.project_id)
        self._project_name_model.set_value(project.name)
        self._usd_path_model.set_value(project.stage.usd_path)
        self._output_root_model.set_value(project.output.root_dir)
        if self.controller.project_dir is not None:
            self._project_dir_model.set_value(str(self.controller.project_dir))
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
        self._render_settings_model.set_value(json.dumps(render.settings, ensure_ascii=False))
        capture = project.capture
        self._physics_hz_model.set_value(str(capture.physics_hz))
        self._capture_fps_model.set_value(str(capture.capture_fps))
        self._start_frame_model.set_value(str(capture.start_frame))
        self._frame_count_model.set_value(str(capture.frame_count))
        self._capture_initial_frame_model.set_value(capture.capture_initial_frame)
        self._segment_frames_model.set_value(str(capture.segment_frames))
        execution = project.execution
        self._segmentation_strategy_model.set_value(execution.segmentation_strategy)
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
        self._motion_absolute_seek_model.set_value(motion.supports_absolute_seek)
        self._motion_options_model.set_value(
            json.dumps(motion.options, ensure_ascii=False)
        )
        semantics = project.semantics
        self._semantic_mapping_model.set_value(semantics.mapping_path or "")
        self._semantic_label_model.set_value(semantics.label_attribute)
        self._semantic_background_model.set_value(str(semantics.background_id))
        self._semantic_options_model.set_value(
            json.dumps(semantics.options, ensure_ascii=False)
        )
        enabled_sensors = [item for item in project.sensors if item.enabled]
        if enabled_sensors:
            self._active_sensor_id = enabled_sensors[0].sensor_id
        self._refresh_summaries()

    def _refresh_summaries(self) -> None:
        project = self.controller.project
        if project is None:
            return
        self._project_state_model.set_value(
            f"Schema {project.schema_version} | "
            + ("unsaved" if self.controller.dirty else f"saved {self.controller.project_dir}")
        )
        self._variant_summary_model.set_value(
            "\n".join(
                f"{item.variant_id}: {item.strategy}, enabled={item.enabled}"
                for item in project.variants
            )
            or "No variants"
        )
        self._rig_summary_model.set_value(
            "\n".join(
                f"{item.rig_id}: {', '.join(item.sensor_ids)}"
                for item in project.rigs
            )
            or "No rigs"
        )
        self._refresh_dirty_state()

    def _record_recent(self) -> None:
        project = self.controller.project
        if project is None or self.controller.project_dir is None:
            return
        self.recent_projects.record(
            self.controller.project_dir,
            project_id=project.project_id,
            name=project.name,
            usd_path=project.stage.usd_path,
        )

    def _new_project(self) -> None:
        try:
            self._create_new_project()
        except Exception as exc:
            self._set_error("create project", exc)

    def _create_new_project(self) -> None:
        self._project_destination(allow_existing_current=False)
        usd_path = self._validated_usd_reference()
        project_id = self._project_id_model.as_string.strip()
        name = self._project_name_model.as_string.strip()
        output_root = self._output_root_model.as_string.strip()
        if not project_id or not name:
            raise ValueError("Project ID and name must not be empty")
        if not output_root:
            raise ValueError("Output root must not be empty")
        self.controller.new_project(
            project_id=project_id,
            name=name,
            usd_path=usd_path,
            output_root=output_root,
        )
        self._load_project_models()
        self._set_status(
            "New valid project created; USD is loading. Click Save Project to persist it."
        )
        self._open_stage()
        self._rebuild()

    def _open_project(self) -> None:
        try:
            path = self._normalize_project_path(
                Path(self._project_dir_model.as_string)
            )
            self.controller.open_project(path)
            self._load_project_models()
            self._record_recent()
            self._set_status(f"Opened {path}; loading USD Stage")
            self._open_stage()
            self._rebuild()
        except Exception as exc:
            self._set_error("open project", exc)

    def _open_recent(self, path: str) -> None:
        self._project_dir_model.set_value(path)
        self._open_project()

    def _save_project(self) -> None:
        try:
            if self.controller.project is None:
                self._create_new_project()
            self._prepare_project()
            destination = self._project_destination(
                allow_existing_current=True,
            )
            destination = self.controller.save_project(destination)
            self._project_dir_model.set_value(str(destination))
            self._record_recent()
            self._refresh_summaries()
            self._set_status(f"Saved {destination}")
        except Exception as exc:
            self._set_error("save project", exc)

    def _save_project_as(self) -> None:
        try:
            self._prepare_project()
            destination = self._project_destination(
                allow_existing_current=False,
            )
            destination = self.controller.save_project_as(destination)
            self._project_dir_model.set_value(str(destination))
            self._record_recent()
            self._refresh_summaries()
            self._set_status(f"Saved project as {destination}")
        except Exception as exc:
            self._set_error("save project as", exc)

    @staticmethod
    def _normalize_project_path(path: Path) -> Path:
        if path.is_file() and path.name == "project.json":
            path = path.parent
        if not (path / "project.json").is_file():
            raise FileNotFoundError(f"not a .swproject directory: {path}")
        return path

    def _browse_project(self) -> None:
        self.file_dialogs.choose_folder(
            title="Open Semantic Capture Project",
            current_path=self._project_dir_model.as_string,
            apply_label="Open .swproject",
            on_selected=self._project_folder_selected,
        )

    def _browse_new_project_parent(self) -> None:
        current = Path(self._project_dir_model.as_string or "/root/gpufree-data/semantic/projects")
        parent = current if current.is_dir() else current.parent
        self.file_dialogs.choose_folder(
            title="Choose Parent Folder for New Project",
            current_path=str(parent),
            apply_label="Use Parent Folder",
            on_selected=self._new_project_parent_selected,
        )

    def _new_project_parent_selected(self, path: Path) -> None:
        project_id = self._project_id_model.as_string.strip() or "semantic_capture"
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", project_id).strip("_")
        safe_name = safe_name or "semantic_capture"
        destination = path / f"{safe_name}.swproject"
        self._project_dir_model.set_value(str(destination))
        self._set_status(
            f"New project location selected: {destination}; choose a USD Stage next"
        )

    def _project_folder_selected(self, path: Path) -> None:
        try:
            project_path = self._normalize_project_path(path)
            self._project_dir_model.set_value(str(project_path))
            self._open_project()
        except Exception as exc:
            self._set_error("select project", exc)

    def _browse_usd(self) -> None:
        self.file_dialogs.choose_file(
            title="Select USD Stage",
            current_path=self._usd_path_model.as_string,
            extensions=("usd", "usda", "usdc"),
            apply_label="Use Stage",
            on_selected=self._usd_selected,
        )

    def _usd_selected(self, path: Path) -> None:
        try:
            value = self._validated_usd_reference(str(path))
            self._usd_path_model.set_value(value)
            if self.controller.project is None:
                self._set_status(
                    f"USD selected: {value}; click Create New Project"
                )
                return
            if self.controller.project.stage.usd_path != value:
                self.controller.project.stage.usd_path = value
                self.controller.dirty = True
            self._set_status(f"USD selected: {value}; loading Stage")
            self._open_stage()
        except Exception as exc:
            self._set_error("select USD Stage", exc)

    def _browse_output(self) -> None:
        self.file_dialogs.choose_folder(
            title="Select Output Root",
            current_path=self._output_root_model.as_string,
            on_selected=lambda path: self._output_root_model.set_value(str(path)),
        )

    def _browse_csv(self) -> None:
        self.file_dialogs.choose_file(
            title="Select Trajectory CSV",
            current_path=self._motion_source_model.as_string,
            extensions=("csv",),
            on_selected=lambda path: self._motion_source_model.set_value(str(path)),
        )

    def _browse_semantic_mapping(self) -> None:
        self.file_dialogs.choose_file(
            title="Select Semantic Mapping",
            current_path=self._semantic_mapping_model.as_string,
            extensions=("json", "yaml", "yml"),
            on_selected=lambda path: self._semantic_mapping_model.set_value(str(path)),
        )

    def _open_stage(self) -> None:
        self._spawn(self._open_stage_async())

    async def _open_stage_async(self) -> None:
        usd_path = self._validated_usd_reference()
        resolved_path = usd_path
        if not ProjectPathResolver.is_uri(usd_path):
            base = self.controller.project_dir or Path(
                self._project_dir_model.as_string
            )
            resolved_path = ProjectPathResolver.resolve(usd_path, base) or usd_path
        self._set_status(f"Opening Stage: {resolved_path}")
        index = await self.stage_service.open(resolved_path)
        self.controller.set_stage_index(index)
        self._visibility = SessionVisibilityController(self.stage_service.stage)
        candidates = self.controller.discover_sensor_candidates()
        self._stage_summary_model.set_value(
            f"{len(index)} prims | {len(candidates)} compatible sensor Prim(s)"
        )
        self._set_status("Stage loaded, indexed, and sensors discovered")
        self._rebuild()

    def _close_stage(self) -> None:
        try:
            if self._visibility is not None:
                self._visibility.clear()
            self._visibility = None
            self.stage_service.close()
            self.controller.set_stage_index(None)
            self._stage_summary_model.set_value("No Stage indexed")
            self._set_status("Stage closed")
        except Exception as exc:
            self._set_error("close Stage", exc)

    def _refresh_stage_index(self) -> None:
        try:
            index = self.stage_service.rebuild_index()
            self.controller.set_stage_index(index)
            self._stage_summary_model.set_value(
                f"{len(index)} prims | "
                f"{len(self.controller.discover_sensor_candidates())} sensor candidates"
            )
            self._set_status("Stage index refreshed")
        except Exception as exc:
            self._set_error("refresh Stage", exc)

    def _search_stage(self) -> None:
        try:
            if self.controller.stage_index is None:
                raise RuntimeError("open a Stage first")
            results = self.controller.stage_index.search(
                self._stage_search_model.as_string
            )[:100]
            self._stage_results_model.set_value(
                "\n".join(f"{item.path} [{item.type_name}]" for item in results)
                or "No search results"
            )
            if results:
                self._prim_path_model.set_value(results[0].path)
            self._set_status(f"Found {len(results)} Prim(s)")
        except Exception as exc:
            self._set_error("search Stage", exc)

    def _locate_prim(self) -> None:
        self._locate_path(self._prim_path_model.as_string)

    def _locate_path(self, path: str) -> None:
        try:
            if self.controller.stage_index is None:
                raise RuntimeError("open a Stage first")
            self.controller.stage_index.require(path)
            omni.usd.get_context().get_selection().set_selected_prim_paths(
                [path], True
            )
            self._prim_path_model.set_value(path)
            self._set_status(f"Selected {path} in Stage and Viewport")
        except Exception as exc:
            self._set_error("locate Prim", exc)

    def _toggle_sensor_candidate(self, item: Dict[str, Any], selected: bool) -> None:
        try:
            sensor = self.controller.set_stage_sensor_selected(
                item["prim_path"], selected, plugin_id=item["plugin_id"]
            )
            self._active_sensor_id = sensor.sensor_id
            self._set_status(
                f"Sensor {sensor.sensor_id} enabled={sensor.enabled}"
            )
            self._defer_rebuild()
        except Exception as exc:
            self._set_error("update sensor selection", exc)

    def _show_sensor_candidate(self, item: Dict[str, Any]) -> None:
        try:
            if item["sensor_ids"]:
                sensor_id = item["sensor_ids"][0]
                self._active_sensor_id = sensor_id
                value = self.controller.effective_sensor_preview(sensor_id)
            else:
                value = item
            self._sensor_details_model.set_value(
                json.dumps(value, ensure_ascii=False, indent=2)
            )
            self._set_status(f"Loaded details for {item['prim_path']}")
        except Exception as exc:
            self._set_error("show sensor details", exc)

    def _read_variant_selection(self) -> None:
        paths = omni.usd.get_context().get_selection().get_selected_prim_paths()
        paths = [path for path in paths if path and path != "/"]
        self._variant_selection_model.set_value(";".join(paths))
        self._set_status(f"Selected {len(paths)} Prim(s) for Variant creation")

    def _create_variant_from_selection(self) -> None:
        try:
            paths = [
                item.strip()
                for item in self._variant_selection_model.as_string.split(";")
                if item.strip()
            ]
            if not paths:
                self._read_variant_selection()
                paths = [
                    item.strip()
                    for item in self._variant_selection_model.as_string.split(";")
                    if item.strip()
                ]
            variant = self.controller.create_isolate_variant(
                paths,
                preserve_lights=self._variant_keep_lights_model.as_bool,
            )
            self._set_status(f"Created Variant {variant.variant_id}")
            self._refresh_summaries()
            self._rebuild()
        except Exception as exc:
            self._set_error("create Variant", exc)

    def _toggle_variant(self, variant_id: str, enabled: bool) -> None:
        try:
            self.controller.set_variant_enabled(variant_id, enabled)
            self._set_status(f"Variant {variant_id} enabled={enabled}")
        except Exception as exc:
            self._set_error("toggle Variant", exc)

    def _duplicate_variant(self, variant_id: str) -> None:
        try:
            duplicate = self.controller.duplicate_variant(variant_id)
            self._set_status(f"Duplicated Variant as {duplicate.variant_id}")
            self._rebuild()
        except Exception as exc:
            self._set_error("duplicate Variant", exc)

    def _delete_variant(self, variant_id: str) -> None:
        try:
            self.controller.delete_variant(variant_id)
            self._clear_variant_preview()
            self._set_status(f"Deleted Variant {variant_id}")
            self._rebuild()
        except Exception as exc:
            self._set_error("delete Variant", exc)

    def _preview_variant(self, variant_id: str) -> None:
        try:
            if self.controller.stage_index is None or self.stage_service.stage is None:
                raise RuntimeError("open a Stage first")
            variant = self.controller.get_variant(variant_id)
            plugin = self.controller.registry.variant(variant.strategy)
            sensor_paths = [
                item.prim_path
                for item in self.controller.project.sensors
                if item.enabled
            ]
            plan = plugin.visibility_plan(
                variant, self.controller.stage_index, sensor_paths
            )
            if self._visibility is None:
                self._visibility = SessionVisibilityController(
                    self.stage_service.stage
                )
            self._visibility.apply(plan)
            self._set_status(
                f"Previewing {variant_id}: {len(plan.hidden_roots)} hidden root(s)"
            )
        except Exception as exc:
            self._set_error("preview Variant", exc)

    def _clear_variant_preview(self) -> None:
        try:
            if self._visibility is not None:
                self._visibility.clear()
            self._set_status("Variant preview cleared")
        except Exception as exc:
            self._set_error("clear Variant preview", exc)

    def _select_capture_sensor(self, sensor_id: str) -> None:
        self._active_sensor_id = sensor_id
        self._rebuild()

    def _toggle_binding(self, variant_id: str, enabled: bool) -> None:
        try:
            self.controller.set_binding_enabled(
                variant_id, self._active_sensor_id, enabled
            )
            self._set_status(
                f"{self._active_sensor_id} × {variant_id} enabled={enabled}"
            )
            self._defer_rebuild()
        except Exception as exc:
            self._set_error("update capture binding", exc)

    def _toggle_modality(
        self, variant_id: str, modality_id: str, enabled: bool
    ) -> None:
        try:
            self.controller.set_modality_enabled(
                variant_id,
                self._active_sensor_id,
                modality_id,
                enabled,
            )
            self._set_status(
                f"{variant_id} / {self._active_sensor_id} / "
                f"{modality_id}={enabled}"
            )
            self._defer_rebuild()
        except Exception as exc:
            self._set_error("update output", exc)

    def _apply_capture_preset(self, preset_id: str) -> None:
        try:
            matrix = self.controller.capture_matrix(self._active_sensor_id)
            targets = [item for item in matrix["rows"] if item["binding_enabled"]]
            if not targets:
                raise ValueError("enable at least one scene Variant row first")
            for row in targets:
                self.controller.apply_modality_preset(
                    row["variant_id"], self._active_sensor_id, preset_id
                )
            self._set_status(
                f"Applied {preset_id} to {len(targets)} enabled row(s)"
            )
            self._rebuild()
        except Exception as exc:
            self._set_error("apply output preset", exc)

    def _apply_render_preset(self, preset_id: str) -> None:
        try:
            self.controller.apply_render_preset(preset_id)
            self._load_project_models()
            self._set_status(f"Applied render preset {preset_id}")
            self._rebuild()
        except Exception as exc:
            self._set_error("apply render preset", exc)

    def _refresh_review(self) -> None:
        project = self.controller.project
        summary = self.controller.capture_plan_summary()
        lines = [
            f"Project: {project.name} ({project.project_id})",
            f"Stage: {project.stage.usd_path}",
            f"Output root: {project.output.root_dir}",
            "",
            (
                f"Sensors: {summary['enabled_sensors']} | "
                f"Variants: {summary['enabled_variants']} | "
                f"Enabled capture bindings: {summary['enabled_bindings']}"
            ),
        ]
        for binding in summary["bindings"]:
            lines.append(
                f"- {binding['sensor_id']} × {binding['variant_id']}: "
                + ", ".join(binding["modalities"])
            )
        lines.extend(
            [
                "",
                (
                    f"Renderer: {project.render.renderer} | "
                    f"{project.render.resolution_width}×{project.render.resolution_height} | "
                    f"SPP {project.render.spp_per_frame}/{project.render.total_spp} | "
                    f"bounces {project.render.max_bounces} | "
                    f"denoiser={project.render.denoiser}"
                ),
                (
                    f"Frames: {project.capture.frame_count} from "
                    f"{project.capture.start_frame} | "
                    f"segment_frames={project.capture.segment_frames}"
                ),
            ]
        )
        self._review_model.set_value("\n".join(lines))

    def _validate(self) -> None:
        try:
            self._prepare_project()
            issues = self.controller.validate()
            self._preflight_model.set_value(
                "\n".join(str(item) for item in issues) if issues else "Validation passed"
            )
            self._set_status("Validation passed" if not issues else "Validation found issues")
        except Exception as exc:
            self._set_error("validate", exc)

    def _preflight(self) -> None:
        try:
            self._prepare_project()
            summary = self.controller.preflight_summary()
            estimate = summary["estimate"]
            lines = [
                "READY" if summary["can_run"] else "BLOCKED",
                (
                    f"{estimate['capture_groups']} capture groups | "
                    f"~{estimate['artifact_files']} files | "
                    f"~{estimate['estimated_gib']:.2f} GiB"
                ),
                f"Stage indexed: {summary['stage_indexed']}",
            ]
            lines.extend(
                f"[{item['severity']}] {item['path']}: {item['message']}"
                for item in summary["issues"]
            )
            self._preflight_model.set_value("\n".join(lines))
            self._set_status("Preflight ready" if summary["can_run"] else "Preflight blocked")
        except Exception as exc:
            self._set_error("preflight", exc)

    def _require_preflight(self) -> None:
        summary = self.controller.preflight_summary()
        if not summary["can_run"]:
            errors = "; ".join(
                f"{item['path']}: {item['message']}"
                for item in summary["issues"]
                if item["severity"] == "error"
            )
            raise RuntimeError(f"preflight blocked: {errors}")

    def _compile_job(self) -> None:
        try:
            self._prepare_project()
            if self.controller.dirty:
                self._save_project()
            job = self.controller.compile_job(self._job_id_model.as_string or None)
            self._job_id_model.set_value(job.job_id)
            self._set_status(f"Compiled {job.job_id} | {job.content_digest}")
        except ValidationFailed as exc:
            self._preflight_model.set_value("\n".join(str(item) for item in exc.issues))
        except Exception as exc:
            self._set_error("compile JobSpec", exc)

    def _run_headless_and_exit(self) -> None:
        try:
            self._prepare_project()
            self._require_preflight()
            if self.controller.dirty:
                self._save_project()
            status = self.controller.run_headless(
                self._job_id_model.as_string or None
            )
            self._job_id_model.set_value(status.job_id)
            self._set_status(f"Launched {status.job_id}; closing Studio")
            self._spawn(self._quit_after_launch())
        except Exception as exc:
            self._set_error("run headless", exc)

    async def _quit_after_launch(self) -> None:
        await omni.kit.app.get_app().next_update_async()
        omni.kit.app.get_app().post_quit(0)

    def _run_headless_monitor(self) -> None:
        try:
            self._prepare_project()
            self._require_preflight()
            if self.controller.dirty:
                self._save_project()
            status = self.controller.run_headless(
                self._job_id_model.as_string or None
            )
            self._job_id_model.set_value(status.job_id)
            self._set_status(f"Launched {status.job_id}; Studio remains open")
        except Exception as exc:
            self._set_error("run and monitor", exc)

    def _refresh_job_status(self) -> None:
        try:
            status = self.controller.job_status(self._job_id_model.as_string or None)
            self._job_history_model.set_value(json.dumps(status.to_dict(), indent=2))
            self._set_status(f"{status.job_id}: {status.state}")
        except Exception as exc:
            self._set_error("refresh job status", exc)

    def _stop_job(self) -> None:
        try:
            status = self.controller.stop_job(self._job_id_model.as_string or None)
            self._set_status(f"Stop requested: {status.job_id} {status.state}")
        except Exception as exc:
            self._set_error("stop job", exc)

    def _resume_job(self) -> None:
        try:
            status = self.controller.resume_job(self._job_id_model.as_string or None)
            self._set_status(f"Resume requested: {status.job_id} {status.state}")
        except Exception as exc:
            self._set_error("resume job", exc)

    def _tail_logs(self) -> None:
        try:
            lines = self.controller.tail_job_logs(
                self._job_id_model.as_string or None, lines=100
            )
            self._log_tail_model.set_value("".join(lines) or "No log output")
            self._set_status("Loaded Runtime log tail")
        except Exception as exc:
            self._set_error("tail logs", exc)

    def _refresh_job_history(self) -> None:
        try:
            jobs = self.controller.list_jobs()
            self._job_history_model.set_value(
                "\n".join(
                    f"{item['job_id']} | {item['state']} | {item.get('message', '')}"
                    for item in jobs
                )
                or "No jobs"
            )
            self._set_status(f"Loaded {len(jobs)} job(s)")
        except Exception as exc:
            self._set_error("load job history", exc)

    def _refresh_segments(self) -> None:
        try:
            segments = self.controller.list_segments(
                self._job_id_model.as_string or None
            )
            self._job_history_model.set_value(
                "\n".join(
                    f"{item.get('segment_id')} | {item.get('state')} | "
                    f"{item.get('capture_groups_current', 0)}/"
                    f"{item.get('capture_groups_total', 0)}"
                    for item in segments
                )
                or "No segments"
            )
            self._set_status(f"Loaded {len(segments)} segment(s)")
        except Exception as exc:
            self._set_error("load segments", exc)

    def _show_failure_report(self) -> None:
        try:
            report = self.controller.read_failure_report(
                self._job_id_model.as_string or None
            )
            self._log_tail_model.set_value(
                json.dumps(report, ensure_ascii=False, indent=2)
                if report
                else "No failure report"
            )
            self._set_status("Failure report loaded")
        except Exception as exc:
            self._set_error("load failure report", exc)

    def _select_advanced_sensor(self, sensor_id: str) -> None:
        self._active_sensor_id = sensor_id
        self._load_sensor_override()
        self._rebuild()

    def _load_sensor_override(self) -> None:
        try:
            if not self._active_sensor_id:
                raise ValueError("select a sensor")
            sensor = self.controller.get_sensor(self._active_sensor_id)
            overrides = {
                name: value
                for name, value in sensor.parameters.items()
                if sensor.parameter_sources.get(name) == "override"
            }
            self._sensor_override_model.set_value(
                json.dumps(overrides, ensure_ascii=False, indent=2)
            )
            self._sensor_advanced_model.set_value(
                json.dumps(
                    self.controller.effective_sensor_preview(sensor.sensor_id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            self._set_status(f"Loaded override for {sensor.sensor_id}")
        except Exception as exc:
            self._set_error("load sensor override", exc)

    def _save_sensor_override(self) -> None:
        try:
            values = self._json(self._sensor_override_model, "sensor overrides")
            sensor = self.controller.set_sensor_overrides(
                self._active_sensor_id, values
            )
            self._set_status(f"Saved override for {sensor.sensor_id}")
            self._load_sensor_override()
        except Exception as exc:
            self._set_error("save sensor override", exc)

    def _clear_sensor_override(self) -> None:
        try:
            sensor = self.controller.get_sensor(self._active_sensor_id)
            names = [
                name
                for name, source in sensor.parameter_sources.items()
                if source == "override"
            ]
            self.controller.clear_sensor_overrides(sensor.sensor_id, names)
            self._sensor_override_model.set_value("{}")
            self._load_sensor_override()
        except Exception as exc:
            self._set_error("clear sensor override", exc)

    def _delete_active_sensor(self) -> None:
        try:
            sensor_id = self._active_sensor_id
            self.controller.delete_sensor(sensor_id)
            enabled = [item for item in self.controller.project.sensors if item.enabled]
            self._active_sensor_id = enabled[0].sensor_id if enabled else ""
            self._set_status(f"Deleted sensor {sensor_id}")
            self._rebuild()
        except Exception as exc:
            self._set_error("delete sensor", exc)

    def _add_rig(self) -> None:
        try:
            sensor_ids = [
                item.strip()
                for item in self._rig_sensors_model.as_string.split(";")
                if item.strip()
            ]
            rig = self.controller.add_rig(
                self._rig_id_model.as_string.strip(),
                sensor_ids,
                reference_frame_prim_path=(
                    self._rig_reference_model.as_string.strip() or None
                ),
            )
            self._refresh_summaries()
            self._set_status(f"Added Rig {rig.rig_id}")
        except Exception as exc:
            self._set_error("add Rig", exc)

    def _delete_rig(self) -> None:
        try:
            rig_id = self._rig_id_model.as_string.strip()
            self.controller.delete_rig(rig_id)
            self._refresh_summaries()
            self._set_status(f"Deleted Rig {rig_id}")
        except Exception as exc:
            self._set_error("delete Rig", exc)

    def _load_plugin_catalog(self) -> None:
        try:
            lines = []
            for item in self.controller.sensor_plugin_catalog():
                manifest = item["manifest"]
                capabilities = item["capabilities"]
                lines.append(
                    f"{manifest['display_name']} ({manifest['plugin_id']})\n"
                    f"  modalities: {', '.join(manifest['supported_modalities'])}\n"
                    f"  time: {capabilities.get('time_model')} | "
                    f"continuous: {capabilities.get('requires_continuous_history')}"
                )
            self._plugin_details_model.set_value("\n".join(lines) or "No plugins")
            self._set_status(f"Loaded {len(lines)} sensor plugin(s)")
        except Exception as exc:
            self._set_error("load plugin catalog", exc)
