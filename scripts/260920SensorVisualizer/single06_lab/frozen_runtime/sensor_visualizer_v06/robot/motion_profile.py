"""Root translation in simulation seconds and motion configuration validation."""
import math
import numpy as np


def sample_position(elapsed, initial_position, forward, speed):
    return np.asarray(initial_position, dtype=np.float64) + np.asarray(forward) * speed * max(0.0, float(elapsed))


def validate_motion(config):
    if not config or not config.get("enabled", False):
        return
    for key in ("robot_prim", "articulation_root"):
        if not isinstance(config.get(key), str) or not config[key].startswith("/"):
            raise ValueError(f"robot_motion.{key} must be an absolute prim path")
    speed = config.get("forward_speed_m_s")
    if not isinstance(speed, (float, int)) or not math.isfinite(speed) or speed < 0:
        raise ValueError("forward_speed_m_s must be finite and nonnegative")
    joints = config.get("joints", [])
    if not joints or any(not j.get("name") for j in joints) or len({j["name"] for j in joints}) != len(joints):
        raise ValueError("Configure distinct moving joints")
    if not config.get("fixed_joint") or config["fixed_joint"] in {j["name"] for j in joints}:
        raise ValueError("The fixed cab joint cannot also be a moving joint")
    for joint in joints:
        speed = joint.get("speed_deg_s", 5.0)
        if not isinstance(speed, (float, int)) or not math.isfinite(speed) or speed <= 0:
            raise ValueError("Joint speed_deg_s must be finite and positive")
