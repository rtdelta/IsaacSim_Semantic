"""Pure-Python preflight summaries and conservative output estimates."""

from dataclasses import dataclass
from typing import Dict

from semantic_world_v04.core.models import ProjectDefinition
from semantic_world_v04.core.progress import capture_group_count


@dataclass(frozen=True)
class OutputEstimate:
    capture_groups: int
    artifact_files: int
    estimated_bytes: int
    simulated_duration_seconds: float
    enabled_sensors: int
    enabled_variants: int

    @property
    def estimated_gib(self) -> float:
        return self.estimated_bytes / float(1024 ** 3)

    def to_dict(self) -> Dict[str, object]:
        return {
            "capture_groups": self.capture_groups,
            "artifact_files": self.artifact_files,
            "estimated_bytes": self.estimated_bytes,
            "estimated_gib": self.estimated_gib,
            "simulated_duration_seconds": self.simulated_duration_seconds,
            "enabled_sensors": self.enabled_sensors,
            "enabled_variants": self.enabled_variants,
        }


def estimate_output(project: ProjectDefinition) -> OutputEstimate:
    """Estimate uncompressed-equivalent output plus a 20% safety margin.

    PNG compression depends on scene content, so production preflight must not
    promise an exact disk size. Semantic ID is budgeted as uint32 and RGB/color
    as three bytes per pixel. Metadata is budgeted at 16 KiB per capture group.
    """

    sensors = {
        sensor.sensor_id: sensor for sensor in project.sensors if sensor.enabled
    }
    variants = [variant for variant in project.variants if variant.enabled]
    total_bytes = 0
    artifact_files = 0
    for variant in variants:
        for sensor_id, modality_ids in variant.modalities_by_sensor.items():
            sensor = sensors.get(sensor_id)
            if sensor is None or not modality_ids:
                continue
            resolution = sensor.parameters.get(
                "resolution",
                [project.render.resolution_width, project.render.resolution_height],
            )
            if not isinstance(resolution, (list, tuple)) or len(resolution) != 2:
                resolution = [
                    project.render.resolution_width,
                    project.render.resolution_height,
                ]
            pixels = max(1, int(resolution[0])) * max(1, int(resolution[1]))
            per_group = 16 * 1024
            for modality_id in modality_ids:
                if modality_id in {"semantic_id", "instance_id"}:
                    per_group += pixels * 4
                elif modality_id in {
                    "rgb",
                    "semantic_color",
                    "depth_color",
                    "surface_normal_color",
                    "instance_color",
                }:
                    per_group += pixels * 3
                elif modality_id == "surface_normal":
                    per_group += pixels * 12
                elif modality_id in {"point_cloud", "point_cloud_ply"}:
                    point_budget = int(
                        sensor.parameters.get("estimated_points_per_scan", 250000)
                    )
                    per_group += max(1, point_budget) * 24
                else:
                    per_group += pixels * 4
            total_bytes += per_group * project.capture.frame_count
            artifact_files += (len(modality_ids) + 1) * project.capture.frame_count

    # Job/status/log/palette/effective-parameter documents are small but count
    # them so the UI does not imply that modality files are the entire job.
    artifact_files += 5
    total_bytes = int(total_bytes * 1.2)
    duration = (
        project.capture.frame_count
        / float(project.capture.capture_fps)
        * len(variants)
        if project.capture.capture_fps > 0
        else 0.0
    )
    return OutputEstimate(
        capture_groups=capture_group_count(project),
        artifact_files=artifact_files,
        estimated_bytes=total_bytes,
        simulated_duration_seconds=duration,
        enabled_sensors=len(sensors),
        enabled_variants=len(variants),
    )
