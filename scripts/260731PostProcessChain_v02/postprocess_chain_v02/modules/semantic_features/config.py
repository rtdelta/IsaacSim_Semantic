from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticFeaturesConfig:
    enabled: bool
    target_extraction: str
