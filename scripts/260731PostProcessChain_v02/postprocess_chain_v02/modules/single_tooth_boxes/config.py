from dataclasses import dataclass


@dataclass(frozen=True)
class SingleToothBoxesConfig:
    enabled: bool
    minimum_pixels: int
