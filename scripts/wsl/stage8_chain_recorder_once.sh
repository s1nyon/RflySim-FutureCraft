#!/usr/bin/env bash
# Launch the Stage 8 read-only control-chain recorder for the current run,
# then run the per-goal EGO chain analyzer on its output. Read-only; never
# publishes or arms.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lifecycle_common.sh"
PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
EGO_SWARM_WSL_DIR="${EGO_SWARM_WSL_DIR:-$PROJECT_DIR/third_party/ego-planner-swarm}"
DURATION_SEC="${STAGE8_RECORDER_DURATION_SEC:-90}"

source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
source "$EGO_SWARM_WSL_DIR/devel/setup.bash"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash"
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi
source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
stage7_load_run_context "$PROJECT_DIR"

RECORDER_SESSION_PGID="$(ps -o pgid= -p $$ | tr -d ' ')"
stack_register wsl "$$" "$RECORDER_SESSION_PGID" "wsl:recorder_session" \
  "stage8_chain_recorder_once.sh (read-only control-chain recorder + analyzer)" \
  "created by stage8_chain_recorder_once.sh (self session registration before launch)"

OUTPUT="$STAGE7_RUN_DIR/stage8_control_chain.jsonl"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage8_control_chain_recorder.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --backend ros \
  --duration-s "$DURATION_SEC" \
  --run-id "$STAGE7_RUN_ID" \
  --simulation-instance-id "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" \
  --min-z=-0.5 \
  --max-z=2 \
  --output "$OUTPUT" \
  --watchdog-dir "$PROJECT_DIR/logs/stage7_live"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage8_ego_chain_analyzer.py" \
  --input "$OUTPUT" \
  --report "$STAGE7_RUN_DIR/stage8_ego_chain_report.json"
echo "[OK] stage8 chain recorder + analyzer finished for $STAGE7_RUN_ID"
