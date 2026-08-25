#!/usr/bin/env bash
# Project-owned, lifecycle-registered RViz session. Keep this file LF-only.
set -eo pipefail

MODE="${1:-dual}"
case "$MODE" in
  uav1|uav2|dual) ;;
  *)
    echo "[ERROR] RViz mode must be uav1, uav2, or dual: $MODE" >&2
    exit 2
    ;;
esac

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_WS="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
EGO_WS="${EGO_SWARM_WSL_DIR:-$PROJECT_DIR/third_party/ego-planner-swarm}"

source /opt/ros/noetic/setup.bash
source "$REF_WS/devel/setup.bash"
source "$EGO_WS/devel/setup.bash"
source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash"
source "$PROJECT_DIR/scripts/wsl/lifecycle_common.sh"
set -u

export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"
export DISPLAY="${DISPLAY:-127.0.0.1:0.0}"
export LIBGL_ALWAYS_INDIRECT="${LIBGL_ALWAYS_INDIRECT:-0}"

if [[ -z "${STACK_MANIFEST:-}" || -z "${RFLY_STACK_ID:-}" ]]; then
  echo "[ERROR] STACK_MANIFEST and RFLY_STACK_ID are required for live RViz" >&2
  exit 3
fi
if [[ ! -f "$STACK_MANIFEST" ]]; then
  echo "[ERROR] Stack manifest not found: $STACK_MANIFEST" >&2
  exit 3
fi
if ! timeout 5s xdpyinfo >/dev/null 2>&1; then
  echo "[ERROR] VcXsrv display $DISPLAY is not ready" >&2
  exit 20
fi

PGID="$(ps -o pgid= -p $$ | tr -d ' ')"
stack_register wsl "$$" "$PGID" wsl:rviz_session \
  "rviz_live.sh -> roslaunch rflysim_rviz.launch mode=$MODE" \
  "created by rviz_live.sh before exec"

exec roslaunch multi_uav_mission rflysim_rviz.launch rviz_mode:="$MODE"
