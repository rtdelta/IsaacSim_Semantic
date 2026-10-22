"""Configuration and RViz generation; no Isaac or ROS imports required."""

import json
import math
import re
from pathlib import Path
from .motion_profile import validate_motion
from .simulation_pacing import pacing_config


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    config.setdefault('auto_bind_robot', False)
    config.setdefault('control_mode', 'scripted')
    config.setdefault('root_frame', 'swing_coordinate')
    config.setdefault('horizontal_frame', 'swing_horizontal_coordinate')
    if config['control_mode'] not in ('scripted', 'observe'):
        raise ValueError('control_mode must be scripted or observe')
    state = config.setdefault('state_publication', {})
    for key, value in {'enabled': True, 'rate_hz': 60., 'joint_topic': '/joint_states',
                       'root_pose_topic': '/excavator/root_pose'}.items():
        state.setdefault(key, value)
    if not math.isfinite(float(state['rate_hz'])) or float(state['rate_hz']) <= 0:
        raise ValueError('state_publication.rate_hz must be finite and positive')
    for field in ('joint_topic', 'root_pose_topic'):
        if not re.fullmatch(r'(/[A-Za-z_][A-Za-z0-9_]*)+', state[field]):
            raise ValueError(f'Invalid absolute ROS topic: {state[field]}')
    if state['joint_topic'] == state['root_pose_topic'] or any(
            state[f] in ('/tf', '/tf_static', '/clock') for f in ('joint_topic', 'root_pose_topic')):
        raise ValueError('State topics must be distinct and cannot replace TF or clock')
    config.setdefault("auto_discover", not bool(config.get("sensors")))
    if type(config["auto_discover"]) is not bool:
        raise ValueError("auto_discover must be true or false.")
    frame_pattern = r"[A-Za-z_][A-Za-z0-9_/]*"
    if not re.fullmatch(frame_pattern, config["world_frame"]):
        raise ValueError("world_frame must be a valid frame name without a leading slash.")
    pacing_config(config)
    if not config['auto_bind_robot']:
        validate_motion(config.get("robot_motion"))
    if config.get("robot_motion", {}).get("enabled", False):
        if not re.fullmatch(frame_pattern, config.get("root_frame", "")) or config["root_frame"] == config["world_frame"]:
            raise ValueError("Configure a valid root_frame distinct from world_frame")
        if not re.fullmatch(frame_pattern, config['horizontal_frame']) or config['horizontal_frame'] in (
                config['world_frame'], config['root_frame']):
            raise ValueError('horizontal_frame must be valid and distinct from world_frame and root_frame')
    domain = config["ros_domain_id"]
    if type(domain) is not int or not 0 <= domain <= 232:
        raise ValueError("ros_domain_id must be an integer from 0 to 232.")
    if config["auto_discover"]:
        # A persisted/manual list must not override what the current stage contains.
        config["sensors"] = []
    else:
        validate_sensors(config)
    return config


def validate_sensors(config):
    sensors = config.get("sensors", [])
    if not sensors:
        raise ValueError("Configure at least one LiDAR sensor.")
    frame_pattern = r"[A-Za-z_][A-Za-z0-9_/]*"
    for sensor in sensors:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", sensor["id"]):
            raise ValueError(f"Invalid sensor ID: {sensor['id']}")
        if not re.fullmatch(r"(/[A-Za-z_][A-Za-z0-9_]*)+", sensor["topic"]):
            raise ValueError(f"Use a valid absolute ROS topic name: {sensor['topic']}")
        if not re.fullmatch(frame_pattern, sensor["frame_id"]):
            raise ValueError(f"Invalid frame name: {sensor['frame_id']}")
        if sensor["frame_id"] == config["world_frame"]:
            raise ValueError("A sensor frame_id must differ from world_frame.")
        if config.get("robot_motion", {}).get("enabled", False) and sensor["frame_id"] == config.get("root_frame"):
            raise ValueError("A sensor frame_id must differ from root_frame.")
        if config.get('robot_motion', {}).get('enabled', False) and sensor['frame_id'] == config.get('horizontal_frame'):
            raise ValueError('A sensor frame_id must differ from horizontal_frame.')
        if not sensor["prim_path"].startswith("/"):
            raise ValueError("prim_path must be the absolute path of the OmniLidar sensing prim.")
    for field in ("id", "topic", "frame_id", "prim_path"):
        values = [s[field] for s in sensors]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate sensor configuration field: {field}")
    return config


def _write_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
    pending.replace(path)
    return path


def write_resolved_config(config, stage_identifier, project_dir):
    return _write_json(Path(project_dir) / "generated/sensors.json",
                       {"stage": stage_identifier, "config": config})


def load_rviz_config(project_dir):
    """External ROS processes use the same resolved list/domain as the Isaac publishers."""
    root = Path(project_dir)
    config = load_config(root / "config/sensors.json")
    if config["auto_discover"]:
        path = root / "generated/sensors.json"
        if not path.is_file():
            raise ValueError("Run run_in_isaac.py in Isaac Sim first to discover sensors and generate the RViz configuration.")
        config = json.loads(path.read_text(encoding="utf-8"))["config"]
        validate_sensors(config)
    return config


def write_rviz(config, path):
    # JSON is a YAML subset understood by RViz's yaml-cpp loader.
    colors = ["80; 220; 255", "255; 180; 70", "140; 255; 120", "240; 120; 220"]
    displays = []
    for i, sensor in enumerate(config["sensors"]):
        displays.append({
            "Class": "rviz_default_plugins/PointCloud2",
            "Name": sensor["id"], "Enabled": True,
            "Topic": {"Value": sensor["topic"], "Depth": 5,
                      "History Policy": "Keep Last", "Reliability Policy": "Best Effort",
                      "Durability Policy": "Volatile"},
            "Position Transformer": "XYZ", "Color Transformer": "FlatColor",
            "Color": colors[i % len(colors)], "Style": "Points",
            "Size (Pixels)": 2, "Size (m)": 0.02, "Alpha": 1,
            "Decay Time": 0, "Queue Size": 20,
        })
    document = {
        "Panels": [{"Class": "rviz_common/Displays", "Name": "Displays"},
                   {"Class": "rviz_common/Time", "Name": "Time"}],
        "Visualization Manager": {
            "Class": "", "Enabled": True,
            "Global Options": {"Fixed Frame": config.get('horizontal_frame', config.get("root_frame", config["world_frame"])) if config.get("robot_motion", {}).get("enabled", False) else config["world_frame"],
                               "Background Color": "25; 25; 30", "Frame Rate": 30},
            "Displays": displays,
            "Tools": [{"Class": "rviz_default_plugins/Interact"},
                      {"Class": "rviz_default_plugins/MoveCamera"}],
            "Views": {"Current": {"Class": "rviz_default_plugins/Orbit",
                                  "Distance": 15, "Pitch": 0.5, "Yaw": 0.8,
                                  "Focal Point": {"X": 0, "Y": 0, "Z": 1}}},
        },
        "Window Geometry": {"Width": 1200, "Height": 800},
    }
    return _write_json(path, document)
