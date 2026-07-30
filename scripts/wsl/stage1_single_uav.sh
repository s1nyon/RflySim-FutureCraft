#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
EGO_SWARM_WSL_DIR="${EGO_SWARM_WSL_DIR:-$PROJECT_ROOT/external/ego-planner-swarm}"
RFLYSIM_EGO_SWARM_LAUNCH="$PROJECT_ROOT/future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_single.launch"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[DRY-RUN] WSL Stage 1 single-UAV mission script"
  echo "[DRY-RUN] sensor_pkg: $REF_28COM_UAV_WSL_DIR/sensor_pkg/main.py"
  echo "[DRY-RUN] slam: roslaunch faster_lio mapping_mid360.launch rviz:=false"
  echo "[DRY-RUN] planner: roslaunch $RFLYSIM_EGO_SWARM_LAUNCH"
  echo "[DRY-RUN] detection: roslaunch object_det detection.launch"
  echo "[DRY-RUN] mission: roslaunch mission_pkg basic_test.launch enable_logging:=true"
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
if [[ ! -f "$EGO_SWARM_WSL_DIR/devel/setup.bash" ]]; then
  echo "[ERROR] Missing ego-swarm ROS workspace setup: $EGO_SWARM_WSL_DIR/devel/setup.bash" >&2
  echo "[ERROR] Build it in WSL first: cd \"$EGO_SWARM_WSL_DIR\" && catkin_make" >&2
  exit 1
fi
if [[ ! -f "$RFLYSIM_EGO_SWARM_LAUNCH" ]]; then
  echo "[ERROR] Missing RflySim ego-swarm launch wrapper: $RFLYSIM_EGO_SWARM_LAUNCH" >&2
  exit 1
fi

if ! command -v xterm >/dev/null 2>&1; then
  echo "[ERROR] xterm is required for the Stage 1 WSL launch flow" >&2
  exit 1
fi

source /opt/ros/noetic/setup.bash || true
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
source "$EGO_SWARM_WSL_DIR/devel/setup.bash"

xterm -hold -e "bash -lc 'cd \"$REF_28COM_UAV_WSL_DIR/sensor_pkg\" && python3 main.py; exec bash'" &
echo "[1/5] Sensor started, waiting 12s..."
sleep 12
xterm -hold -e "bash -lc 'source \"$REF_28COM_UAV_WSL_DIR/devel/setup.bash\" && roslaunch faster_lio mapping_mid360.launch rviz:=false; exec bash'" &
echo "[2/5] SLAM started, waiting 5s..."
sleep 5
xterm -hold -e "bash -lc 'source \"$REF_28COM_UAV_WSL_DIR/devel/setup.bash\" && source \"$EGO_SWARM_WSL_DIR/devel/setup.bash\" && roslaunch \"$RFLYSIM_EGO_SWARM_LAUNCH\"; exec bash'" &
echo "[3/5] Planner started, waiting 5s..."
sleep 5
xterm -hold -e "bash -lc 'source \"$REF_28COM_UAV_WSL_DIR/devel/setup.bash\" && roslaunch object_det detection.launch; exec bash'" &
echo "[4/5] Detection started, waiting 5s..."
sleep 5
xterm -hold -e "bash -lc 'source \"$REF_28COM_UAV_WSL_DIR/devel/setup.bash\" && roslaunch mission_pkg basic_test.launch enable_logging:=true; exec bash'" &
echo "[5/5] Mission started"
sleep 5

echo "[INFO] Stage 1 single-UAV ROS launch started."
