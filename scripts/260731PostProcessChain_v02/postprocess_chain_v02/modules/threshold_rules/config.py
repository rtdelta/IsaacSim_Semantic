from dataclasses import dataclass


@dataclass(frozen=True)
class SingleToothRuleConfig:
    minimum_visible_ratio_a: float
    minimum_fill_ratio_c: float
    height_width_axis_mode: str
    minimum_height_width_ratio_d: float
    drop_all_single_boxes_if_bad_teeth_at_least: int


@dataclass(frozen=True)
class CollisionRuleConfig:
    minimum_visible_ratio_b: float
    drop_collision_box_if_bad_teeth_at_least: int


@dataclass(frozen=True)
class ThresholdRulesConfig:
    enabled: bool
    single_tooth: SingleToothRuleConfig
    collision_model: CollisionRuleConfig
