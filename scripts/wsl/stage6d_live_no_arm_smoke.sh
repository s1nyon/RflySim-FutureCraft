#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage6d_live"
PLAN="$OUTPUT_DIR/live_mission_plan.json"
SMOKE_REPORT="$OUTPUT_DIR/mavros_smoke_report.json"
EVENTS="$OUTPUT_DIR/mission_events_no_arm.jsonl"
TRACE="$OUTPUT_DIR/executor_trace_no_arm.json"
SCORE="$OUTPUT_DIR/score_summary_no_arm.json"

mkdir -p "$OUTPUT_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py" \
  --behavior-config "$PROJECT_DIR/config/stage5_behavior_tree.json" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --output "$PLAN"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --backend ros \
  --timeout-s 10 \
  --report "$SMOKE_REPORT"

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py" \
  --plan "$PLAN" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --backend ros \
  --events "$EVENTS" \
  --trace "$TRACE" \
  --score "$SCORE"

