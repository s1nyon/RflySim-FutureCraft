#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[DRY-RUN] WSL Stage 1 single-UAV mission script"
  echo "[DRY-RUN] sensor_pkg: $REF_28COM_UAV_WSL_DIR/sensor_pkg/main.py"
  echo "[DRY-RUN] mission: mission_pkg basic_test.launch enable_logging:=true"
  exit 0
fi

if [[ ! -f "$REF_28COM_UAV_WSL_DIR/sensor_pkg/main.py" ]]; then
  echo "[ERROR] Missing sensor_pkg/main.py at $REF_28COM_UAV_WSL_DIR" >&2
  exit 1
fi
if [[ ! -f "$REF_28COM_UAV_WSL_DIR/devel/setup.bash" ]]; then
  echo "[ERROR] Missing ROS workspace setup: $REF_28COM_UAV_WSL_DIR/devel/setup.bash" >&2
  exit 1
fi

if ! command -v xterm >/dev/null 2>&1; then
  echo "[ERROR] xterm is required for the Stage 1 WSL launch flow" >&2
  exit 1
fi

source /opt/ros/noetic/setup.bash || true
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"

xterm -hold -e "bash -lc 'cd \"$REF_28COM_UAV_WSL_DIR/sensor_pkg\" && python3 main.py; exec bash'" &
sleep 8
xterm -hold -e "bash -lc 'source \"$REF_28COM_UAV_WSL_DIR/devel/setup.bash\" && roslaunch mission_pkg basic_test.launch enable_logging:=true; exec bash'" &
sleep 2

echo "[INFO] Stage 1 single-UAV ROS launch started."
