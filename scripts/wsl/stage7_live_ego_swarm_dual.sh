#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
EGO_SWARM_WSL_DIR="${EGO_SWARM_WSL_DIR:-$PROJECT_DIR/external/ego-planner-swarm}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage7_live"
EGO_LOG="$OUTPUT_DIR/ego_swarm_dual.log"

mkdir -p "$OUTPUT_DIR"
source /opt/ros/noetic/setup.bash
if [ ! -f "$EGO_SWARM_WSL_DIR/devel/setup.bash" ]; then
  echo "[ERROR] ego-planner-swarm is not built: $EGO_SWARM_WSL_DIR/devel/setup.bash" >&2
  echo "[ERROR] Run scripts/clone_ego_swarm.bat, build it in WSL, or set EGO_SWARM_WSL_DIR." >&2
  exit 1
fi
source "$EGO_SWARM_WSL_DIR/devel/setup.bash"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash"
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

exec roslaunch multi_uav_mission rflysim_ego_swarm_dual.launch 2>&1 | tee "$EGO_LOG"
