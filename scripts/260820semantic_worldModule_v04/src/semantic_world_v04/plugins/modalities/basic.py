"""Built-in image modalities with delayed Runtime encoders."""

from typing import Any, Dict, Mapping, Sequence, Tuple

from semantic_world_v04.core.models import ValidationIssue
from semantic_world_v04.core.sensor_models import PluginManifest, TypedPayload


def _typed_value(value):
    return value.data if isinstance(value, TypedPayload) else value


class _BaseModality:
    plugin_id = ""
    output_extension = ""
    media_type = ""

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id,
            plugin_kind="modality",
            plugin_version="2.0.0",
            display_name=self.plugin_id.replace("_", " ").title(),
            definition_class=f"{self.__class__.__module__}:{self.__class__.__name__}",
        )

    def validate_options(self, options: Mapping[str, object]) -> Sequence[ValidationIssue]:
        return ()

    def encode_runtime(
        self, payload: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Tuple[bytes, Dict[str, Any]]:
        raise NotImplementedError


class RgbModality(_BaseModality):
    plugin_id = "rgb"
    output_extension = ".png"
    media_type = "image/png"

    def encode_runtime(self, payload, context):
        _ = context
        from semantic_world_v04.runtime.encoding import encode_png

        return encode_png(_typed_value(payload["rgb"])), {}


class SemanticIdModality(_BaseModality):
    plugin_id = "semantic_id"
    output_extension = ".npy"
    media_type = "application/x-npy"

    def encode_runtime(self, payload, context):
        from semantic_world_v04.runtime.encoding import encode_npy, jsonable

        semantic = payload.get("semantic_id", payload.get("semantic"))
        if isinstance(semantic, TypedPayload):
            data = semantic.data
            info = semantic.metadata.get("info", {})
        else:
            data = semantic["data"]
            info = semantic.get("info", {})
        context["semantic_palette"].update_from_info(info)
        return encode_npy(data), {"semantic_info": jsonable(info)}


class SemanticColorModality(_BaseModality):
    plugin_id = "semantic_color"
    output_extension = ".png"
    media_type = "image/png"

    def encode_runtime(self, payload, context):
        from semantic_world_v04.runtime.encoding import encode_png, jsonable

        semantic = payload.get("semantic_color", payload.get("semantic"))
        if isinstance(semantic, TypedPayload):
            data = semantic.data
            info = semantic.metadata.get("info", {})
        else:
            data = semantic["data"]
            info = semantic.get("info", {})
        palette = context["semantic_palette"]
        palette.update_from_info(info)
        return encode_png(palette.colorize(data)), {
            "semantic_info": jsonable(info)
        }


PLUGIN_CLASSES = (RgbModality, SemanticIdModality, SemanticColorModality)
