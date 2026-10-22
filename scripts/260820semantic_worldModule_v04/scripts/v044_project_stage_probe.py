"""Validate the Project & Stage UI flow inside a real Kit process."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import omni.kit.app


async def _wait_for(predicate, app, *, updates: int = 1200) -> bool:
    for _ in range(updates):
        await app.next_update_async()
        if predicate():
            return True
    return False


async def _probe() -> None:
    app = omni.kit.app.get_app()
    temp_root = Path(tempfile.mkdtemp(prefix="v044_project_stage_"))
    try:
        for _ in range(8):
            await app.next_update_async()

        from semantic.capture.studio.extension import get_active_studio

        studio = get_active_studio()
        if studio is None:
            raise RuntimeError("active Studio window is missing")

        stage_path = os.environ.get("V044_PROBE_STAGE", "")
        if not stage_path or not Path(stage_path).is_file():
            raise RuntimeError(f"probe USD Stage is missing: {stage_path}")

        project_dir = temp_root / "project_stage_probe.swproject"
        studio._project_dir_model.set_value(str(project_dir))
        studio._project_id_model.set_value("project-stage-probe")
        studio._project_name_model.set_value("Project Stage Probe")
        studio._usd_path_model.set_value(stage_path)
        studio._output_root_model.set_value(str(temp_root / "output"))
        studio._new_project()

        loaded = await _wait_for(
            lambda: studio.controller.stage_index is not None,
            app,
        )
        if not loaded:
            raise RuntimeError(f"new project Stage did not load: {studio._status_model.as_string}")

        prim_count = len(studio.controller.stage_index)
        studio._save_project()
        for _ in range(8):
            await app.next_update_async()
        if not (project_dir / "project.json").is_file():
            raise RuntimeError(f"project manifest was not saved: {project_dir}")

        # Reset the editable state, then use the actual folder-picker callback
        # with project.json selected. The project callback must not run until
        # the file-picker event has completed and the dialog is destroyed.
        studio._close_stage()
        studio.controller.project = None
        studio.controller.project_dir = None
        studio.controller.set_stage_index(None)
        studio._project_dir_model.set_value(str(project_dir))
        studio.file_dialogs.choose_folder(
            title="Project & Stage Import Probe",
            current_path=str(project_dir),
            apply_label="Open .swproject",
            on_selected=studio._project_folder_selected,
        )
        await app.next_update_async()
        dialog = studio.file_dialogs._dialog
        dialog._widget._click_apply_handler(
            "project.json",
            str(project_dir) + "/",
        )
        if studio.controller.project is not None:
            raise RuntimeError("project import ran inside the file-picker event")

        imported = await _wait_for(
            lambda: (
                studio.controller.project is not None
                and studio.controller.stage_index is not None
            ),
            app,
        )
        if not imported:
            raise RuntimeError(f"saved project did not import: {studio._status_model.as_string}")
        if studio.controller.project_dir.resolve() != project_dir.resolve():
            raise RuntimeError(
                f"wrong project imported: {studio.controller.project_dir}"
            )
        if studio.controller.project.stage.usd_path != stage_path:
            raise RuntimeError(
                f"USD path changed during import: {studio.controller.project.stage.usd_path}"
            )

        print(
            "V044_PROJECT_STAGE_OK "
            f"saved=true imported=true callback_deferred=true prims={prim_count}",
            flush=True,
        )
        studio._close_stage()
        app.post_quit(0)
    except Exception as exc:
        print(
            f"V044_PROJECT_STAGE_FAIL {type(exc).__name__}: {exc}",
            flush=True,
        )
        app.post_quit(5)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


asyncio.ensure_future(_probe())
