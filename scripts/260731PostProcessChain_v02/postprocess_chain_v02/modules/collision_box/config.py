from dataclasses import dataclass


@dataclass(frozen=True)
class CollisionBoxConfig:
    enabled: bool
    length_axis: str
    length_source: str
    width_source: str
    union_scope: str
