#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lifecycle_common.sh"
PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
EGO_SWARM_WSL_DIR="${EGO_SWARM_WSL_DIR:-$PROJECT_DIR/third_party/ego-planner-swarm}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage7_live"
CURRENT_RUN_FILE="$OUTPUT_DIR/current_run.env"
READINESS_MAX_AGE_SEC="${STAGE7_READINESS_MAX_AGE_SEC:-120}"

source /opt/ros/noetic/setup.bash
source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

stage7_load_run_context "$PROJECT_DIR"

python3 $PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py --validate \
  --report "$STAGE7_READINESS_REPORT" \
  --run-id "$STAGE7_RUN_ID" \
  --simulation-instance-id "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" \
  --max-age-sec "$READINESS_MAX_AGE_SEC"

if [ ! -f "$EGO_SWARM_WSL_DIR/devel/setup.bash" ]; then
  echo "[ERROR] ego-planner-swarm is not built: $EGO_SWARM_WSL_DIR/devel/setup.bash" >&2
  echo "[ERROR] Run git submodule update --init --recursive and build the EGO workspace, or set EGO_SWARM_WSL_DIR." >&2
  exit 1
fi
source "$EGO_SWARM_WSL_DIR/devel/setup.bash"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" --extend
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi

EGO_LOG="$STAGE7_RUN_DIR/ego_swarm_dual.log"
EGO_SESSION_PGID="$(ps -o pgid= -p $$ | tr -d ' ')"
stack_register wsl "$$" "$EGO_SESSION_PGID" "wsl:ego_swarm_session" \
  "stage7_live_ego_swarm_dual.sh -> roslaunch multi_uav_mission rflysim_ego_swarm_dual.launch" \
  "created by stage7_live_ego_swarm_dual.sh (self session registration before exec)"
exec roslaunch multi_uav_mission rflysim_ego_swarm_dual.launch 2>&1 | tee "$EGO_LOG"
