from dataclasses import dataclass


@dataclass(frozen=True)
class PoseMetricsConfig:
    enabled: bool
    algorithm: str
    invalid_value: float
    write_angle: bool
