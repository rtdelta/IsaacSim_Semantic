"""Depth, normal, and instance modalities."""

from typing import Any, Mapping, Sequence

from semantic_world_v04.core.models import ValidationIssue
from semantic_world_v04.core.sensor_models import PluginManifest, TypedPayload


def _value(payload: Mapping[str, Any], name: str) -> Any:
    value = payload[name]
    return value.data if isinstance(value, TypedPayload) else value


class _GeometryModality:
    plugin_id = ""
    output_extension = ""
    media_type = ""

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id,
            plugin_kind="modality",
            plugin_version="1.0.0",
            display_name=self.plugin_id.replace("_", " ").title(),
            definition_class=f"{self.__class__.__module__}:{self.__class__.__name__}",
        )

    def validate_options(self, options: Mapping[str, Any]) -> Sequence[ValidationIssue]:
        return ()


class DepthLinearModality(_GeometryModality):
    plugin_id = "depth_linear"
    output_extension = ".npy"
    media_type = "application/x-npy"

    def encode_runtime(self, payload, context):
        _ = context
        from semantic_world_v04.runtime.encoding import encode_npy

        return encode_npy(_value(payload, "depth_linear")), {"depth_unit": "meter"}


class DepthColorModality(_GeometryModality):
    plugin_id = "depth_color"
    output_extension = ".png"
    media_type = "image/png"

    def validate_options(self, options):
        issues = []
        for name in ("minimum", "maximum"):
            value = options.get(name, 0.0)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                issues.append(
                    ValidationIssue(
                        "modality.depth_range",
                        f"{name} must be numeric",
                        f"modalities.{self.plugin_id}.options.{name}",
                    )
                )
        return issues

    def encode_runtime(self, payload, context):
        from semantic_world_v04.runtime.encoding import colorize_depth, encode_png

        options = context.get("modality_options", {})
        color = colorize_depth(
            _value(payload, "depth_linear"),
            minimum=float(options.get("minimum", 0.0)),
            maximum=float(options.get("maximum", 0.0)),
        )
        return encode_png(color), {"depth_visualization": dict(options)}


class SurfaceNormalModality(_GeometryModality):
    plugin_id = "surface_normal"
    output_extension = ".npy"
    media_type = "application/x-npy"

    def encode_runtime(self, payload, context):
        _ = context
        from semantic_world_v04.runtime.encoding import encode_npy

        return encode_npy(_value(payload, "surface_normal")), {
            "normal_coordinate_frame": "camera"
        }


class SurfaceNormalColorModality(_GeometryModality):
    plugin_id = "surface_normal_color"
    output_extension = ".png"
    media_type = "image/png"

    def encode_runtime(self, payload, context):
        _ = context
        from semantic_world_v04.runtime.encoding import colorize_normals, encode_png

        return encode_png(colorize_normals(_value(payload, "surface_normal"))), {}


class InstanceIdModality(_GeometryModality):
    plugin_id = "instance_id"
    output_extension = ".npy"
    media_type = "application/x-npy"

    def encode_runtime(self, payload, context):
        _ = context
        from semantic_world_v04.runtime.encoding import encode_npy, jsonable

        instance = payload.get("instance_id", payload.get("instance"))
        if isinstance(instance, TypedPayload):
            return encode_npy(instance.data), {
                "instance_info": jsonable(instance.metadata.get("info", {}))
            }
        return encode_npy(instance["data"]), {
            "instance_info": jsonable(instance.get("info", {}))
        }


class InstanceColorModality(_GeometryModality):
    plugin_id = "instance_color"
    output_extension = ".png"
    media_type = "image/png"

    def encode_runtime(self, payload, context):
        from semantic_world_v04.runtime.encoding import encode_png, jsonable

        instance = payload.get("instance_color", payload.get("instance"))
        if isinstance(instance, TypedPayload):
            data = instance.data
            info = instance.metadata.get("info", {})
        else:
            data = instance["data"]
            info = instance.get("info", {})
        return encode_png(context["semantic_palette"].colorize(data)), {
            "instance_info": jsonable(info)
        }


PLUGIN_CLASSES = (
    DepthLinearModality,
    DepthColorModality,
    SurfaceNormalModality,
    SurfaceNormalColorModality,
    InstanceIdModality,
    InstanceColorModality,
)
