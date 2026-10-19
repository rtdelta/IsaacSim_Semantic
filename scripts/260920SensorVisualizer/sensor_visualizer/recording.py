"""Run system ROS outside Isaac's Python/library environment."""

import json
import os
from pathlib import Path
import signal
import subprocess
from datetime import datetime, timezone
from uuid import uuid4
from .performance import timed


def ros_command(config, arguments):
    # Only the fixed shell fragment is interpreted; all paths/arguments use argv.
    return ["/bin/bash", "--noprofile", "--norc", "-c",
            'set -e; source "$1"; shift; exec "$@"', "lidar-ros", config["ros_setup"],
            *arguments]


def ros_environment(config):
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "LD_PRELOAD",
                "VIRTUAL_ENV", "CONDA_PREFIX", "AMENT_PREFIX_PATH",
                "CMAKE_PREFIX_PATH", "COLCON_PREFIX_PATH"):
        env.pop(key, None)
    env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    env["ROS_DOMAIN_ID"] = str(config["ros_domain_id"])
    env["ROS_DISTRO"] = "jazzy"
    env["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
    return env


class Recorder:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.session_dir = None
        self.log_file = None
        self.manifest = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, sensor_ids, output_directory, scene_metadata):
        if self.running:
            raise ValueError("A recording is already running.")
        sensors = [s for s in self.config["sensors"] if s["id"] in sensor_ids]
        if not sensors:
            raise ValueError("Select at least one sensor to record.")
        self.reap()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.session_dir = Path(output_directory).expanduser() / (stamp + "_" + uuid4().hex[:6])
        self.session_dir.mkdir(parents=True, exist_ok=False)
        topics = [s["topic"] for s in sensors] + ["/tf", "/tf_static", "/clock"]
        state = self.config.get('state_publication', {})
        if state.get('enabled') and self.config.get('robot_motion', {}).get('enabled'):
            topics.extend([state['joint_topic'], state['root_pose_topic']])
        qos_path = self.session_dir / "qos_overrides.yaml"
        qos_profiles = {s["topic"]: {"history": "keep_last", "depth": 20,
                        "reliability": "reliable", "durability": "volatile"} for s in sensors}
        qos_profiles.update({"/tf": {"history": "keep_last", "depth": 120,
                             "reliability": "reliable", "durability": "transient_local"},
                             "/clock": {"history": "keep_last", "depth": 1,
                             "reliability": "reliable", "durability": "transient_local"}})
        for topic in topics:
            if topic != '/tf_static':
                qos_profiles.setdefault(topic, {'history': 'keep_last', 'depth': 20,
                    'reliability': 'reliable', 'durability': 'volatile'})
        qos_path.write_text(json.dumps(qos_profiles, indent=2), encoding="utf-8")
        # rosbag creates bag/ itself. The surrounding session holds our metadata/log.
        args = ["ros2", "bag", "record", "--storage", "mcap",
                "--output", str(self.session_dir / "bag"),
                "--use-sim-time", "--disable-keyboard-controls",
                "--qos-profile-overrides-path", str(qos_path),
                "--node-name", "lidar_visualizer_recorder", "--topics", *topics]
        self.manifest = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "state": "starting", "sensors": sensors, "topics": topics,
            "world_frame": self.config["world_frame"],
            "root_frame": self.config.get("root_frame", self.config["world_frame"]),
            "robot_motion": self.config.get("robot_motion", {}),
            'control_mode': self.config.get('control_mode', 'scripted'),
            'robot_binding': self.config.get('robot_binding'),
            'state_publication': state,
            'state_conventions': {'joint_position_unit': 'rad', 'root_position_unit': 'm',
                'quaternion_order': 'xyzw', 'root_frame': self.config.get('root_frame'),
                'root_parent_frame': self.config['world_frame'],
                'joint_velocity_and_effort': 'unpublished', 'angle_conversion': 'none; native asset DOFs'},
            "simulation_pacing": scene_metadata.get("simulation_pacing"),
            "ros_domain_id": self.config["ros_domain_id"],
            "scene": scene_metadata,
        }
        self._write_manifest()
        self.log_file = (self.session_dir / "recorder.log").open("wb")
        try:
            self.process = subprocess.Popen(
                ros_command(self.config, args), env=ros_environment(self.config),
                stdin=subprocess.DEVNULL, stdout=self.log_file, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            self.log_file.close()
            self.log_file = None
            self.manifest["state"] = "start_failed"
            self._write_manifest()
            raise
        self.manifest.update(state="process_running", pid=self.process.pid)
        self._write_manifest()
        return self.session_dir

    @timed('recording.manifest_write')
    def _write_manifest(self):
        if self.session_dir and self.manifest:
            (self.session_dir / "session.json").write_text(
                json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def reap(self):
        if self.process is None or self.process.poll() is None:
            return None
        code = self.process.returncode
        self.process = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.manifest.update(state="finished" if code in (0, -signal.SIGINT) else "failed",
                             returncode=code, ended_utc=datetime.now(timezone.utc).isoformat(),
                             bag_metadata_exists=(self.session_dir / "bag/metadata.yaml").is_file())
        self._write_manifest()
        return code

    def stop(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired as exc:
                # Retain the handle; a second stop can retry without losing data.
                raise RuntimeError(f"Recorder is still finishing files. Retry Stop Recording shortly. Log: {self.session_dir}/recorder.log") from exc
        return self.reap()
