#!/usr/bin/env bash
set -euo pipefail
set +u
source /opt/ros/jazzy/setup.bash
set -u
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec /usr/bin/python3 run_viewer.py --capture latest --rviz "$@"
