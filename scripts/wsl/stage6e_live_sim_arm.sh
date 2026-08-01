#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage6e_live"
PLAN="$OUTPUT_DIR/live_mission_plan.json"
SMOKE_REPORT="$OUTPUT_DIR/mavros_smoke_report.json"
EVENTS="$OUTPUT_DIR/mission_events.jsonl"
TRACE="$OUTPUT_DIR/executor_trace.json"
SCORE="$OUTPUT_DIR/score_summary.json"
TARGET_PROVIDER_SERVICE="${TARGET_PROVIDER_SERVICE:-/mission/target_provider/query}"
TARGET_PROVIDER_LOG="$OUTPUT_DIR/target_provider.log"

mkdir -p "$OUTPUT_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py" \
  --behavior-config "$PROJECT_DIR/config/stage5_behavior_tree.json" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --output "$PLAN"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --backend ros \
  --timeout-s 10 \
  --report "$SMOKE_REPORT"

if ! rosservice list 2>/dev/null | grep -Fxq "$TARGET_PROVIDER_SERVICE"; then
  nohup python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/sim_vision_target_provider.py" \
    --config "$PROJECT_DIR/config/stage6b_sim_vision.json" \
    --backend ros \
    --service "$TARGET_PROVIDER_SERVICE" > "$TARGET_PROVIDER_LOG" 2>&1 &
fi

for _ in $(seq 1 20); do
  if rosservice list 2>/dev/null | grep -Fxq "$TARGET_PROVIDER_SERVICE"; then
    break
  fi
  sleep 0.5
done

if ! rosservice list 2>/dev/null | grep -Fxq "$TARGET_PROVIDER_SERVICE"; then
  echo "[ERROR] target provider service not available: $TARGET_PROVIDER_SERVICE" >&2
  tail -n 40 "$TARGET_PROVIDER_LOG" >&2 || true
  exit 1
fi

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py" \
  --plan "$PLAN" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --backend ros \
  --allow-arm \
  --simulation-only \
  --events "$EVENTS" \
  --trace "$TRACE" \
  --score "$SCORE"
