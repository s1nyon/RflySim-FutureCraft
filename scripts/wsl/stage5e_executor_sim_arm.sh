#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "[DRY-RUN] WSL Stage 5E simulation-arm executor script"
  echo "[DRY-RUN] generate: live_mission_plan.json from stage5 configs"
  echo "[DRY-RUN] run: mission_executor.py --backend ros --allow-arm --simulation-only"
  exit 0
fi

if [[ ! -f "$REF_28COM_UAV_WSL_DIR/devel/setup.bash" ]]; then
  echo "[ERROR] Missing ROS workspace setup: $REF_28COM_UAV_WSL_DIR/devel/setup.bash" >&2
  exit 1
fi

if ! command -v xterm >/dev/null 2>&1; then
  echo "[ERROR] xterm is required for the Stage 5E live launch flow" >&2
  exit 1
fi

source /opt/ros/noetic/setup.bash || true
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"

RUN_DIR="$PROJECT_ROOT/logs/stage5e_live_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

python3 "$PROJECT_ROOT/future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py" \
  --behavior-config "$PROJECT_ROOT/config/stage5_behavior_tree.json" \
  --live-config "$PROJECT_ROOT/config/stage5_live_mission.json" \
  --output "$RUN_DIR/live_mission_plan.json"

python3 "$PROJECT_ROOT/future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py" \
  --plan "$RUN_DIR/live_mission_plan.json" \
  --live-config "$PROJECT_ROOT/config/stage5_live_mission.json" \
  --backend ros \
  --allow-arm \
  --simulation-only \
  --events "$RUN_DIR/mission_events.jsonl" \
  --trace "$RUN_DIR/executor_trace.json" \
  --score "$RUN_DIR/score_summary.json"

echo "[INFO] Stage 5E simulation-arm executor run started. Logs: $RUN_DIR"

