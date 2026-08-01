#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -Eeo pipefail

ALLOW_ARM=false
SIMULATION_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --allow-arm) ALLOW_ARM=true ;;
    --simulation-only) SIMULATION_ONLY=true ;;
  esac
done

if [ "$ALLOW_ARM" != true ] || [ "$SIMULATION_ONLY" != true ]; then
  echo "[ERROR] Stage 7 live flight requires --allow-arm --simulation-only." >&2
  exit 1
fi

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage7_live"
CURRENT_RUN_FILE="$OUTPUT_DIR/current_run.env"
READINESS_MAX_AGE_SEC="${STAGE7_READINESS_MAX_AGE_SEC:-120}"
PLAN="$OUTPUT_DIR/live_slam_ego_swarm_plan.json"
SMOKE_REPORT="$OUTPUT_DIR/slam_ego_swarm_smoke_report.json"
FLIGHT_REPORT="$OUTPUT_DIR/flight_report.json"
EVENTS="$OUTPUT_DIR/mission_events.jsonl"
TRACE="$OUTPUT_DIR/executor_trace.json"
SCORE="$OUTPUT_DIR/score_summary.json"
EXECUTOR_LOG="$OUTPUT_DIR/executor.log"
RUNNER_LOG="$OUTPUT_DIR/runner.log"

if [ ! -f "$CURRENT_RUN_FILE" ]; then
  echo "[ERROR] Stage 7 current run metadata is missing: $CURRENT_RUN_FILE" >&2
  exit 1
fi
source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
stage7_load_run_context "$PROJECT_DIR"
RUN_ID="$STAGE7_RUN_ID"

mkdir -p "$OUTPUT_DIR"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_run_artifacts.py" \
  --output-dir "$OUTPUT_DIR" \
  --run-id "$RUN_ID"
: >"$RUNNER_LOG"
exec > >(tee -a "$RUNNER_LOG") 2>&1

RUN_PHASE="environment"
record_early_failure() {
  local exit_code=$?
  trap - ERR
  set +e
  python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py" \
    --smoke-report "$SMOKE_REPORT" \
    --events "$EVENTS" \
    --trace "$TRACE" \
    --score "$SCORE" \
    --executor-log "$RUNNER_LOG" \
    --executor-exit-code "$exit_code" \
    --run-id "$RUN_ID" \
    --phase "$RUN_PHASE" \
    --report "$FLIGHT_REPORT" >/dev/null 2>&1
  exit "$exit_code"
}
trap record_early_failure ERR

source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash"
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

RUN_PHASE="sensor_readiness"
python3 $PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py --validate \
  --report "$STAGE7_READINESS_REPORT" \
  --run-id "$STAGE7_RUN_ID" \
  --simulation-instance-id "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" \
  --max-age-sec "$READINESS_MAX_AGE_SEC"

KEEPALIVE_PIDS=()
cleanup_keepalive() {
  for pid in "${KEEPALIVE_PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup_keepalive EXIT INT TERM

start_keepalive() {
  local topic="$1"
  local planner_topic="$2"
  local x="$3"
  local y="$4"
  local z="$5"
  nohup python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_setpoint_bridge.py" \
    --setpoint-topic "$topic" \
    --planner-topic "$planner_topic" \
    --initial-x "$x" \
    --initial-y "$y" \
    --initial-z "$z" \
    --yaw 0.0 \
    --rate-hz 20 >"$OUTPUT_DIR/$(basename "$topic" | tr '/' '_')_keepalive.log" 2>&1 &
  KEEPALIVE_PIDS+=("$!")
}

RUN_PHASE="smoke_check"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --backend ros \
  --timeout-s 10 \
  --report "$SMOKE_REPORT"

RUN_PHASE="setpoint_bridge"
start_keepalive "/uav1/mavros/setpoint_raw/local" "/uav1/planning/pos_cmd" 0.5 1.5 1.0
start_keepalive "/uav2/mavros/setpoint_raw/local" "/uav2/planning/pos_cmd" 1.5 1.5 1.0
sleep 2

RUN_PHASE="plan_generation"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --output "$PLAN"

RUN_PHASE="executor"
set +e
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py" \
  --plan "$PLAN" \
  --live-config "$PROJECT_DIR/config/stage5_live_mission.json" \
  --backend ros \
  --allow-arm \
  --simulation-only \
  --events "$EVENTS" \
  --trace "$TRACE" \
  --score "$SCORE" >"$EXECUTOR_LOG" 2>&1
EXECUTOR_EXIT_CODE=$?

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py" \
  --smoke-report "$SMOKE_REPORT" \
  --events "$EVENTS" \
  --trace "$TRACE" \
  --score "$SCORE" \
  --executor-log "$EXECUTOR_LOG" \
  --executor-exit-code "$EXECUTOR_EXIT_CODE" \
  --run-id "$RUN_ID" \
  --phase "complete" \
  --report "$FLIGHT_REPORT"
REPORT_EXIT_CODE=$?
set -e

if [ "$REPORT_EXIT_CODE" -ne 0 ]; then
  echo "[ERROR] Stage 7 flight failed; inspect $FLIGHT_REPORT and $EXECUTOR_LOG" >&2
  tail -n 40 "$EXECUTOR_LOG" >&2 || true
fi
exit "$REPORT_EXIT_CODE"
