"""Omniverse extension lifecycle for the task-oriented v04.4 Studio."""

import carb
import omni.ext

from .window import StudioWindow

_ACTIVE_STUDIO = None


def get_active_studio():
    """Return the live Studio window for Kit integration probes."""

    return _ACTIVE_STUDIO


class Extension(omni.ext.IExt):
    def on_startup(self, ext_id: str) -> None:
        global _ACTIVE_STUDIO
        self._ext_id = ext_id
        self._studio = StudioWindow()
        _ACTIVE_STUDIO = self._studio
        carb.log_info("[semantic_world_v04] Studio v04.4 extension started")

    def on_shutdown(self) -> None:
        global _ACTIVE_STUDIO
        if getattr(self, "_studio", None) is not None:
            self._studio.shutdown()
        self._studio = None
        _ACTIVE_STUDIO = None
        carb.log_info("[semantic_world_v04] Studio v04.4 extension stopped")
