from dataclasses import dataclass


@dataclass(frozen=True)
class VisibilityRatioConfig:
    enabled: bool
    zero_reference_value: float
    ratio_over_one: str
