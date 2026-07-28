#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage6e_live"
PLAN="$OUTPUT_DIR/live_mission_plan.json"
EVENTS="$OUTPUT_DIR/mission_events.jsonl"
TRACE="$OUTPUT_DIR/executor_trace.json"
SCORE="$OUTPUT_DIR/score_summary.json"

mkdir -p "$OUTPUT_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py" \
  --behavior-config "$PROJECT_DIR/config/stage5_behavior_tree.json" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --output "$PLAN"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py" \
  --plan "$PLAN" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --backend ros \
  --allow-arm \
  --simulation-only \
  --events "$EVENTS" \
  --trace "$TRACE" \
  --score "$SCORE"

