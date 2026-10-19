"""Exercise every v04.4 Studio page inside a real Kit process."""

import asyncio
import os

import omni.kit.app


async def _probe() -> None:
    app = omni.kit.app.get_app()
    for _ in range(8):
        await app.next_update_async()

    from semantic.capture.studio.extension import get_active_studio

    studio = get_active_studio()
    if studio is None:
        print("V044_STUDIO_WORKFLOW_FAIL active_studio_missing", flush=True)
        app.post_quit(2)
        return

    stage_path = os.environ.get("V044_PROBE_STAGE", "")
    if not stage_path:
        print("V044_STUDIO_WORKFLOW_FAIL stage_env_missing", flush=True)
        app.post_quit(3)
        return

    try:
        studio._project_id_model.set_value("v044-ui-probe")
        studio._project_name_model.set_value("v04.4 UI Probe")
        studio._project_dir_model.set_value("/tmp/v044-ui-probe.swproject")
        studio._usd_path_model.set_value(stage_path)
        studio._output_root_model.set_value("/tmp/v044_ui_probe_output")
        studio._new_project()
        for _ in range(1200):
            await app.next_update_async()
            if studio.controller.stage_index is not None:
                break
        if studio.controller.stage_index is None:
            raise RuntimeError("Stage did not finish indexing")

        candidates = studio.controller.discover_sensor_candidates()
        camera = next(
            item
            for item in candidates
            if item["prim_path"]
            == "/Excavator_Fangshan_03/boom_prim/Camera"
        )
        sensor = studio.controller.set_stage_sensor_selected(
            camera["prim_path"], True, plugin_id=camera["plugin_id"]
        )
        studio._active_sensor_id = sensor.sensor_id
        variant = studio.controller.create_isolate_variant(
            ["/Excavator_Fangshan_03"], preserve_lights=True
        )
        studio.controller.apply_modality_preset(
            "full_scene", sensor.sensor_id, "common_all"
        )
        studio.controller.apply_modality_preset(
            variant.variant_id, sensor.sensor_id, "common_all"
        )

        for page_index in range(7):
            studio._set_page(page_index)
            for _ in range(3):
                await app.next_update_async()

        page_height = float(studio._page_scroll.computed_height)
        if page_height < 200:
            raise RuntimeError(
                f"Studio page area collapsed: computed_height={page_height}"
            )

        # Exercise the real FilePicker apply callback. Selection delivery and
        # dialog destruction must be deferred beyond the current UI event.
        selected_files = []
        studio.file_dialogs.choose_file(
            title="v04.4 File Picker Probe",
            current_path=stage_path,
            extensions=("usd", "usda", "usdc"),
            on_selected=selected_files.append,
        )
        await app.next_update_async()
        file_dialog = studio.file_dialogs._dialog
        file_dialog._widget._click_apply_handler(
            os.path.basename(stage_path),
            os.path.dirname(stage_path) + "/",
        )
        if selected_files:
            raise RuntimeError("file selection callback ran inside the apply event")
        for _ in range(8):
            await app.next_update_async()
        if [str(item) for item in selected_files] != [stage_path]:
            raise RuntimeError(f"file picker selection mismatch: {selected_files}")

        selected_folders = []
        studio.file_dialogs.choose_folder(
            title="v04.4 Folder Picker Probe",
            current_path="/root/gpufree-data/semantic/projects",
            on_selected=selected_folders.append,
        )
        await app.next_update_async()
        folder_dialog = studio.file_dialogs._dialog
        folder_dialog._widget._click_apply_handler(
            "",
            "/root/gpufree-data/semantic/projects",
        )
        if selected_folders:
            raise RuntimeError("folder selection callback ran inside the apply event")
        for _ in range(12):
            await app.next_update_async()
        if [str(item) for item in selected_folders] != [
            "/root/gpufree-data/semantic/projects"
        ]:
            raise RuntimeError(f"folder picker selection mismatch: {selected_folders}")

        matrix = studio.controller.capture_matrix(sensor.sensor_id)
        summary = studio.controller.capture_plan_summary()
        if studio.controller.current_render_preset_id() != "pathtracing_production":
            raise RuntimeError("new project did not keep production preset")
        if summary["enabled_bindings"] != 2:
            raise RuntimeError(f"unexpected binding count: {summary}")
        if not all(
            set(row["selected_modalities"])
            >= {
                "rgb",
                "depth_linear",
                "depth_color",
                "semantic_id",
                "semantic_color",
            }
            for row in matrix["rows"]
        ):
            raise RuntimeError(f"flat modality matrix mismatch: {matrix}")

        print(
            "V044_STUDIO_WORKFLOW_OK "
            f"pages=7 page_height={page_height:.1f} pickers=2 "
            f"candidates={len(candidates)} "
            f"sensor={sensor.sensor_id} variants=2 bindings=2 "
            "preset=pathtracing_production",
            flush=True,
        )
        app.post_quit(0)
    except Exception as exc:
        print(f"V044_STUDIO_WORKFLOW_FAIL {type(exc).__name__}: {exc}", flush=True)
        app.post_quit(4)


asyncio.ensure_future(_probe())
