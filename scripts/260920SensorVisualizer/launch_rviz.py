"""Run using system Python in the remote graphical desktop terminal."""

import os
from pathlib import Path

from sensor_visualizer.config import load_rviz_config, write_rviz
from sensor_visualizer.recording import ros_command, ros_environment


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    try:
        config = load_rviz_config(root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    rviz = write_rviz(config, root / "rviz/lidars.rviz")
    args = ros_command(config, ["rviz2", "-d", str(rviz),
                                "--ros-args", "-p", "use_sim_time:=true"])
    os.execve(args[0], args, ros_environment(config))
