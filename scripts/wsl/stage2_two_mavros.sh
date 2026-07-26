#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"

start_one() {
  local ns="$1"
  local fcu_url="$2"
  local sysid="$3"
  xterm -hold -e "bash -lc 'source /opt/ros/noetic/setup.bash; source \"$REF_28COM_UAV_WSL_DIR/devel/setup.bash\"; ROS_NAMESPACE=$ns roslaunch mavros px4.launch fcu_url:=$fcu_url tgt_system:=$sysid; exec bash'" &
}

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[DRY-RUN] WSL Stage 2 dual-MAVROS launch script"
  echo "[DRY-RUN] uav1: ROS_NAMESPACE=uav1, fcu_url:=udp://:14541@127.0.0.1:14581, tgt_system:=1"
  echo "[DRY-RUN] uav2: ROS_NAMESPACE=uav2, fcu_url:=udp://:14542@127.0.0.1:14582, tgt_system:=2"
  exit 0
fi

if ! command -v xterm >/dev/null 2>&1; then
  echo "[ERROR] xterm is required for the Stage 2 MAVROS launch flow" >&2
  exit 1
fi

if [[ ! -f "$REF_28COM_UAV_WSL_DIR/devel/setup.bash" ]]; then
  echo "[ERROR] Missing ROS workspace setup: $REF_28COM_UAV_WSL_DIR/devel/setup.bash" >&2
  exit 1
fi

start_one uav1 udp://:14541@127.0.0.1:14581 1
sleep 3
start_one uav2 udp://:14542@127.0.0.1:14582 2
sleep 2

echo "[INFO] Stage 2 dual MAVROS launch started."
