"""Capture progress calculations shared by Supervisor and Runtime."""

from typing import List, Tuple

from .models import ProjectDefinition


def groups_per_frame(project: ProjectDefinition) -> int:
    enabled_sensors = {
        sensor.sensor_id for sensor in project.sensors if sensor.enabled
    }
    return sum(
        1
        for variant in project.variants
        if variant.enabled
        for sensor_id, modalities in variant.modalities_by_sensor.items()
        if sensor_id in enabled_sensors and modalities
    )


def capture_group_count(project: ProjectDefinition) -> int:
    """Return atomic sensor/variant/frame commits expected for a project.

    One capture group is one enabled sensor in one enabled variant at one
    frame. A group may contain several modalities and is committed atomically.
    """

    return groups_per_frame(project) * project.capture.frame_count


def expected_capture_keys(
    project: ProjectDefinition, start_frame: int, frame_count: int
) -> List[Tuple[int, str, str]]:
    enabled_sensors = {
        sensor.sensor_id for sensor in project.sensors if sensor.enabled
    }
    keys = []
    for frame_index in range(start_frame, start_frame + frame_count):
        for variant in project.variants:
            if not variant.enabled:
                continue
            for sensor_id, modalities in variant.modalities_by_sensor.items():
                if sensor_id in enabled_sensors and modalities:
                    keys.append((frame_index, sensor_id, variant.variant_id))
    return keys
