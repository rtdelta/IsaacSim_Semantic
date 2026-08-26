from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentFilterConfig:
    enabled: bool
    connectivity: int
    minimum_connected_component_pixels: int
