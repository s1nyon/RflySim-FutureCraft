#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
LOG_DIR="$PROJECT_ROOT/logs/stage2_mavros"
ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
PX4_MAVLINK_BIN="${PX4_MAVLINK_BIN:-/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4-mavlink}"

cleanup() {
  local pids
  pids="$(jobs -pr || true)"
  if [[ -n "$pids" ]]; then
    kill $pids >/dev/null 2>&1 || true
  fi
}

start_one() {
  local ns="$1"
  local fcu_url="$2"
  local sysid="$3"
  local map_frame="${ns}_map"
  local odom_parent_frame="${ns}_odom"
  local odom_child_frame="${ns}_base_link"
  local log_file="$LOG_DIR/${ns}_mavros.log"
  nohup bash -lc "source /opt/ros/noetic/setup.bash; source '$REF_28COM_UAV_WSL_DIR/devel/setup.bash'; if [[ -f '$PROJECT_ROOT/future_aircraft_ws/devel/setup.bash' ]]; then source '$PROJECT_ROOT/future_aircraft_ws/devel/setup.bash'; else export ROS_PACKAGE_PATH='$PROJECT_ROOT/future_aircraft_ws/src':\${ROS_PACKAGE_PATH:-}; fi; export ROS_MASTER_URI='$ROS_MASTER_URI'; roslaunch multi_uav_mission rflysim_mavros_px4.launch uav_namespace:=$ns fcu_url:=$fcu_url tgt_system:=$sysid map_id_des:=$map_frame odom_parent_id_des:=$odom_parent_frame odom_child_id_des:=$odom_child_frame" >"$log_file" 2>&1 &
  echo "[INFO] Started MAVROS namespace=$ns pid=$! log=$log_file"
}

start_px4_mavros_link() {
  local sysid="$1"
  local px4_port="$2"
  local mavros_port="$3"
  local attempt

  if [[ ! -x "$PX4_MAVLINK_BIN" ]]; then
    echo "[ERROR] Missing PX4 MAVLink client: $PX4_MAVLINK_BIN" >&2
    exit 1
  fi

  for attempt in $(seq 1 30); do
    if [[ -S "/tmp/px4-sock-$sysid" ]]; then
      break
    fi
    sleep 1
  done
  if [[ ! -S "/tmp/px4-sock-$sysid" ]]; then
    echo "[ERROR] PX4 instance $sysid is unavailable after 30 seconds." >&2
    exit 1
  fi

  if ! "$PX4_MAVLINK_BIN" --instance "$sysid" start -u "$px4_port" -o "$mavros_port" -r 4000000; then
    echo "[WARN] PX4 instance=$sysid MAVROS link may already exist; continuing with stream setup." >&2
  fi
  "$PX4_MAVLINK_BIN" --instance "$sysid" stream -u "$px4_port" -s LOCAL_POSITION_NED -r 30
  "$PX4_MAVLINK_BIN" --instance "$sysid" stream -u "$px4_port" -s ODOMETRY -r 30
  "$PX4_MAVLINK_BIN" --instance "$sysid" boot_complete
  echo "[INFO] PX4 instance=$sysid MAVROS link: UDP $px4_port -> $mavros_port"
}

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[DRY-RUN] WSL Stage 2 dual-MAVROS headless launch script"
  echo "[DRY-RUN] roscore: $ROS_MASTER_URI"
  echo "[DRY-RUN] PX4 uav1: px4-mavlink --instance 1 start -u 14600 -o 14601 -r 4000000"
  echo "[DRY-RUN] PX4 uav2: px4-mavlink --instance 2 start -u 14610 -o 14611 -r 4000000"
  echo "[DRY-RUN] uav1: ROS_NAMESPACE=uav1, fcu_url:=udp://:14601@127.0.0.1:14600, tgt_system:=1"
  echo "[DRY-RUN] uav1 MAVROS odometry frames: map_id_des:=uav1_map, odom_parent_id_des:=uav1_odom, odom_child_id_des:=uav1_base_link"
  echo "[DRY-RUN] uav2: ROS_NAMESPACE=uav2, fcu_url:=udp://:14611@127.0.0.1:14610, tgt_system:=2"
  echo "[DRY-RUN] uav2 MAVROS odometry frames: map_id_des:=uav2_map, odom_parent_id_des:=uav2_odom, odom_child_id_des:=uav2_base_link"
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
export ROS_IP="${ROS_IP:-127.0.0.1}"
trap cleanup EXIT INT TERM

if ! timeout 3s rostopic list >/dev/null 2>&1; then
  nohup roscore >"$LOG_DIR/roscore.log" 2>&1 &
  echo "[INFO] Started roscore pid=$! log=$LOG_DIR/roscore.log"
  sleep 5
fi

if ! timeout 5s rostopic list >/dev/null 2>&1; then
  echo "[ERROR] ROS master is still unavailable at $ROS_MASTER_URI" >&2
  exit 1
fi

start_px4_mavros_link 1 14600 14601
start_px4_mavros_link 2 14610 14611

start_one uav1 udp://:14601@127.0.0.1:14600 1
sleep 3
start_one uav2 udp://:14611@127.0.0.1:14610 2
sleep 2

echo "[INFO] Stage 2 dual MAVROS headless launch started."
echo "[INFO] Keeping this WSL session alive. Close this window to stop roscore and MAVROS."
wait
