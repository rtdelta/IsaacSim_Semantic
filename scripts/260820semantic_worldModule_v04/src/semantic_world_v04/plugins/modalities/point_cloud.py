"""Raw and exchange-format point-cloud modalities."""

from typing import Any, Mapping, Sequence

from semantic_world_v04.core.models import ValidationIssue
from semantic_world_v04.core.sensor_models import PluginManifest, TypedPayload


def _cloud(payload: Mapping[str, Any]) -> Any:
    value = payload["point_cloud"]
    return value.data if isinstance(value, TypedPayload) else value


class _PointCloudModality:
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


class PointCloudNpzModality(_PointCloudModality):
    plugin_id = "point_cloud"
    output_extension = ".npz"
    media_type = "application/x-npz"

    def encode_runtime(self, payload, context):
        _ = context
        import numpy as np

        from semantic_world_v04.runtime.encoding import encode_npz

        value = _cloud(payload)
        arrays = value if isinstance(value, Mapping) else {"points": np.asarray(value)}
        return encode_npz(arrays), {"point_cloud_fields": sorted(arrays)}


class PointCloudPlyModality(_PointCloudModality):
    plugin_id = "point_cloud_ply"
    output_extension = ".ply"
    media_type = "application/vnd.ply"

    def encode_runtime(self, payload, context):
        _ = context
        from semantic_world_v04.runtime.encoding import encode_point_cloud_ply

        return encode_point_cloud_ply(_cloud(payload)), {}


PLUGIN_CLASSES = (PointCloudNpzModality, PointCloudPlyModality)
