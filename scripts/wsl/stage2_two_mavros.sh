#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
LOG_DIR="$PROJECT_ROOT/logs/stage2_mavros"
ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"

start_one() {
  local ns="$1"
  local fcu_url="$2"
  local sysid="$3"
  local log_file="$LOG_DIR/${ns}_mavros.log"
  nohup bash -lc "source /opt/ros/noetic/setup.bash; source '$REF_28COM_UAV_WSL_DIR/devel/setup.bash'; export ROS_MASTER_URI='$ROS_MASTER_URI'; export ROS_NAMESPACE=$ns; roslaunch mavros px4.launch fcu_url:=$fcu_url tgt_system:=$sysid" >"$log_file" 2>&1 &
  echo "[INFO] Started MAVROS namespace=$ns pid=$! log=$log_file"
}

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[DRY-RUN] WSL Stage 2 dual-MAVROS headless launch script"
  echo "[DRY-RUN] roscore: $ROS_MASTER_URI"
  echo "[DRY-RUN] uav1: ROS_NAMESPACE=uav1, fcu_url:=udp://:20101@127.0.0.1:20100, tgt_system:=1"
  echo "[DRY-RUN] uav2: ROS_NAMESPACE=uav2, fcu_url:=udp://:20103@127.0.0.1:20102, tgt_system:=2"
  echo "[DRY-RUN] logs: $LOG_DIR"
  exit 0
fi

if [[ ! -f "$REF_28COM_UAV_WSL_DIR/devel/setup.bash" ]]; then
  echo "[ERROR] Missing ROS workspace setup: $REF_28COM_UAV_WSL_DIR/devel/setup.bash" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
export ROS_MASTER_URI

if ! timeout 3s rostopic list >/dev/null 2>&1; then
  nohup roscore >"$LOG_DIR/roscore.log" 2>&1 &
  echo "[INFO] Started roscore pid=$! log=$LOG_DIR/roscore.log"
  sleep 5
fi

if ! timeout 5s rostopic list >/dev/null 2>&1; then
  echo "[ERROR] ROS master is still unavailable at $ROS_MASTER_URI" >&2
  exit 1
fi

start_one uav1 udp://:20101@127.0.0.1:20100 1
sleep 3
start_one uav2 udp://:20103@127.0.0.1:20102 2
sleep 2

echo "[INFO] Stage 2 dual MAVROS headless launch started."

