from __future__ import annotations

import json
from pathlib import Path

import pytest

from joint_position_recorder.config import ConfigurationError, ProjectConfig, load_project_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_profile_has_expected_joint_contract() -> None:
    config = load_project_config(
        PROJECT_ROOT / "profiles" / "excavator_four_joint_default.json"
    )

    assert config.logical_joint_names == ("cab", "boom", "small_arm", "bucket")
    assert [joint.default_speed_degrees for joint in config.joints] == [8.0, 5.0, 5.0, 5.0]
    assert config.require_fixed_base is True


def test_profile_requires_exactly_four_joints() -> None:
    value = json.loads(
        (PROJECT_ROOT / "profiles" / "excavator_four_joint_default.json").read_text(
            encoding="utf-8"
        )
    )
    value["joints"] = value["joints"][:3]

    with pytest.raises(ConfigurationError, match="requires 4 joints"):
        ProjectConfig.from_dict(value)


def test_profile_rejects_non_positive_speed() -> None:
    value = json.loads(
        (PROJECT_ROOT / "profiles" / "excavator_four_joint_default.json").read_text(
            encoding="utf-8"
        )
    )
    value["joints"][0]["default_speed_degrees"] = 0

    with pytest.raises(ConfigurationError, match="speed must be positive"):
        ProjectConfig.from_dict(value)
