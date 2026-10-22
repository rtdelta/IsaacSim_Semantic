"""Small wrapper around the Kit file picker used by the v04.4 Studio."""

import asyncio
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Set


class FileDialogController:
    def __init__(self) -> None:
        self._dialog = None
        self._tasks: Set[asyncio.Task] = set()
        self._task_dialogs: Dict[asyncio.Task, object] = {}

    def close(self) -> None:
        """Hide now and destroy after the current Kit UI event completes."""

        dialog = self._take_dialog()
        if dialog is not None:
            self._defer_destroy(dialog)

    def shutdown(self) -> None:
        """Release current and deferred dialogs during extension shutdown."""

        dialog = self._take_dialog()
        if dialog is not None:
            self._destroy(dialog)
        for task in tuple(self._tasks):
            task.cancel()
            deferred_dialog = self._task_dialogs.pop(task, None)
            if deferred_dialog is not None:
                self._destroy(deferred_dialog)
        self._tasks.clear()

    def _take_dialog(self):
        dialog = self._dialog
        self._dialog = None
        if dialog is not None:
            try:
                dialog.hide()
            except Exception:
                pass
        return dialog

    @staticmethod
    def _destroy(dialog) -> None:
        try:
            dialog.destroy()
        except Exception:
            pass

    def _defer_destroy(self, dialog, callback: Optional[Callable[[], None]] = None) -> None:
        async def finish() -> None:
            import omni.kit.app

            await omni.kit.app.get_app().next_update_async()
            self._destroy(dialog)
            if callback is not None:
                callback()

        task = asyncio.ensure_future(finish())
        # Keep the dialog reachable if shutdown occurs before the next update.
        self._tasks.add(task)
        self._task_dialogs[task] = dialog

        def done(completed: asyncio.Task) -> None:
            self._tasks.discard(completed)
            self._task_dialogs.pop(completed, None)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                import carb

                carb.log_error(f"[semantic_world_v04] File dialog callback failed: {exc}")

        task.add_done_callback(done)

    def choose_file(
        self,
        *,
        title: str,
        current_path: str,
        extensions: Sequence[str],
        on_selected: Callable[[Path], None],
        apply_label: str = "Select",
    ) -> None:
        self._show(
            title=title,
            current_path=current_path,
            extensions=extensions,
            on_selected=on_selected,
            apply_label=apply_label,
            folder_mode=False,
        )

    def choose_folder(
        self,
        *,
        title: str,
        current_path: str,
        on_selected: Callable[[Path], None],
        apply_label: str = "Select Folder",
    ) -> None:
        self._show(
            title=title,
            current_path=current_path,
            extensions=(),
            on_selected=on_selected,
            apply_label=apply_label,
            folder_mode=True,
        )

    def _show(
        self,
        *,
        title: str,
        current_path: str,
        extensions: Sequence[str],
        on_selected: Callable[[Path], None],
        apply_label: str,
        folder_mode: bool,
    ) -> None:
        from omni.kit.window.filepicker import FilePickerDialog

        self.close()
        current = Path(current_path or "/root/gpufree-data/semantic")
        initial_directory = current if current.is_dir() else current.parent

        def selected(filename, directory) -> None:
            candidate = self._selected_path(filename, directory, folder_mode)
            if not folder_mode and extensions:
                allowed = {item.casefold().lstrip(".") for item in extensions}
                if candidate.suffix.casefold().lstrip(".") not in allowed:
                    raise ValueError(
                        f"Select one of: {', '.join(sorted(allowed))}"
                    )
            dialog = self._take_dialog()
            if dialog is not None:
                self._defer_destroy(
                    dialog,
                    callback=lambda: on_selected(candidate),
                )

        def cancelled(_filename, _directory) -> None:
            self.close()

        kwargs = {
            "allow_multi_selection": False,
            "apply_button_label": apply_label,
            "click_apply_handler": selected,
            "click_cancel_handler": cancelled,
            "current_directory": str(initial_directory),
        }
        if extensions:
            kwargs["file_extension_options"] = [
                (f"*.{item.lstrip('.')}", f"{item.upper()} files")
                for item in extensions
            ]
        self._dialog = FilePickerDialog(title, **kwargs)
        self._dialog.show()

    @staticmethod
    def _selected_path(filename, directory, folder_mode: bool) -> Path:
        base = Path(str(directory or "."))
        name = str(filename or "").strip()
        candidate = base / name if name and name not in {".", ".."} else base
        if folder_mode:
            if candidate.is_file():
                return candidate.parent
            return candidate
        return candidate
