from __future__ import annotations

from typing import Tuple

from .models import DatasetContract, FramePlan


def build_frame_plans(
    contract: DatasetContract, filename_prefix: str
) -> Tuple[FramePlan, ...]:
    plans = []
    seen_names: set[str] = set()
    for frame in contract.frames:
        normalized = f"{frame.numeric_frame_id:0{contract.padding_width}d}"
        base_name = f"{filename_prefix}_{normalized}"
        rgb_name = base_name + frame.rgb_path.suffix
        tooth_name = base_name + frame.tooth_label_path.suffix
        collision_name = base_name + frame.collision_label_path.suffix
        key = base_name.casefold()
        if key in seen_names:
            raise ValueError(f"duplicate normalized output stem: {base_name}")
        seen_names.add(key)
        plans.append(
            FramePlan(
                source=frame,
                normalized_frame_id=normalized,
                rgb_name=rgb_name,
                tooth_label_name=tooth_name,
                collision_label_name=collision_name,
            )
        )
    return tuple(plans)
