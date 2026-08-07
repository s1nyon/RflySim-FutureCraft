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
CURRENT_RUN_FILE="$PROJECT_DIR/logs/stage7_live/current_run.env"
READINESS_MAX_AGE_SEC="${STAGE7_READINESS_MAX_AGE_SEC:-120}"

if [ ! -f "$CURRENT_RUN_FILE" ]; then
  echo "[ERROR] Stage 7 current run metadata is missing: $CURRENT_RUN_FILE" >&2
  exit 1
fi
source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
stage7_load_run_context "$PROJECT_DIR"
RUN_ID="$STAGE7_RUN_ID"

OUTPUT_DIR="$STAGE7_RUN_DIR"
PLAN="$OUTPUT_DIR/live_slam_ego_swarm_plan.json"
SMOKE_REPORT="$OUTPUT_DIR/slam_ego_swarm_smoke_report.json"
FLIGHT_REPORT="$OUTPUT_DIR/flight_report.json"
EVENTS="$OUTPUT_DIR/mission_events.jsonl"
TRACE="$OUTPUT_DIR/executor_trace.json"
SCORE="$OUTPUT_DIR/score_summary.json"
EXECUTOR_LOG="$OUTPUT_DIR/executor.log"
RUNNER_LOG="$OUTPUT_DIR/runner.log"

mkdir -p "$OUTPUT_DIR"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_run_artifacts.py" \
  --output-dir "$OUTPUT_DIR" \
  --run-id "$RUN_ID" \
  --course-spec "$PROJECT_DIR/config/maps/predicted_narrow_course_v1.json" \
  --simulation-instance-id "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" \
  --ros-master-uri "$ROS_MASTER_URI"
: >"$RUNNER_LOG"
exec > >(tee -a "$RUNNER_LOG") 2>&1

RUN_PHASE="environment"
record_early_failure() {
  local exit_code=$?
  trap - ERR
  set +e
  if declare -F safe_land_disarm >/dev/null 2>&1; then
    safe_land_disarm || true
  fi
  python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py" \
    --smoke-report "$SMOKE_REPORT" \
    --events "$EVENTS" \
    --trace "$TRACE" \
    --score "$SCORE" \
    --executor-log "$RUNNER_LOG" \
    --executor-exit-code "$exit_code" \
    --run-id "$RUN_ID" \
    --phase "$RUN_PHASE" \
    --provenance "$OUTPUT_DIR/provenance.json" \
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

safe_land_disarm() {
  set +e
  if ! command -v rosservice >/dev/null 2>&1; then
    echo "[ERROR] rosservice unavailable; cannot run safe landing cleanup" >&2
    return 1
  fi

  local uav state all_disarmed
  for uav in uav1 uav2; do
    state="$(timeout 3s rostopic echo -n 1 "/$uav/mavros/state" 2>/dev/null || true)"
    if grep -q '^armed: True$' <<<"$state"; then
      echo "[WARN] Requesting AUTO.LAND for $uav after flight-path failure"
      rosservice call "/$uav/mavros/set_mode" 0 AUTO.LAND || true
    fi
  done

  for _attempt in $(seq 1 30); do
    all_disarmed=true
    for uav in uav1 uav2; do
      state="$(timeout 3s rostopic echo -n 1 "/$uav/mavros/state" 2>/dev/null || true)"
      if ! grep -q '^armed: False$' <<<"$state"; then
        all_disarmed=false
      fi
    done
    if [ "$all_disarmed" = true ]; then
      echo "[INFO] Both simulated vehicles are disarmed"
      return 0
    fi
    sleep 1
  done

  local MAV_CMD_COMPONENT_ARM_DISARM=400
  for uav in uav1 uav2; do
    state="$(timeout 3s rostopic echo -n 1 "/$uav/mavros/state" 2>/dev/null || true)"
    if grep -q '^armed: True$' <<<"$state"; then
      echo "[WARN] Force-disarming $uav PX4 SITL after AUTO.LAND timeout"
      rosservice call "/$uav/mavros/cmd/command" \
        "{broadcast: false, command: $MAV_CMD_COMPONENT_ARM_DISARM, confirmation: 0, param1: 0.0, param2: 21196.0, param3: 0.0, param4: 0.0, param5: 0.0, param6: 0.0, param7: 0.0}" || true
    fi
  done
  sleep 2

  all_disarmed=true
  for uav in uav1 uav2; do
    state="$(timeout 3s rostopic echo -n 1 "/$uav/mavros/state" 2>/dev/null || true)"
    if ! grep -q '^armed: False$' <<<"$state"; then
      all_disarmed=false
    fi
  done
  [ "$all_disarmed" = true ]
}

RUN_PHASE="sensor_readiness"
python3 $PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py --validate \
  --report "$STAGE7_READINESS_REPORT" \
  --run-id "$STAGE7_RUN_ID" \
  --simulation-instance-id "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" \
  --max-age-sec "$READINESS_MAX_AGE_SEC"

KEEPALIVE_PIDS=()
WATCHDOG_PIDS=()
cleanup_keepalive() {
  for pid in "${KEEPALIVE_PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  for pid in "${WATCHDOG_PIDS[@]}"; do
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
    --min-x -1 --max-x 17 --min-y -2 --max-y 7 --min-z -0.5 --max-z 2 \
    --yaw 0.0 \
    --rate-hz 20 >"$OUTPUT_DIR/$(basename "$topic" | tr '/' '_')_keepalive.log" 2>&1 &
  KEEPALIVE_PIDS+=("$!")
}

start_watchdog() {
  local uav="$1"
  nohup python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/course_geofence_watchdog.py" \
    --state-topic "/$uav/mavros/state" --odom-topic "/$uav/mavros/local_position/odom" \
    --set-mode-service "/$uav/mavros/set_mode" \
    --min-x -1 --max-x 17 --min-y -2 --max-y 7 --min-z -0.5 --max-z 2 \
    --max-speed-mps 2 --max-odom-age-s 2 \
    --output "$OUTPUT_DIR/${uav}_watchdog_events.jsonl" \
    >"$OUTPUT_DIR/${uav}_geofence_watchdog.log" 2>&1 &
  WATCHDOG_PIDS+=("$!")
}

RUN_PHASE="smoke_check"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --backend ros \
  --timeout-s 10 \
  --report "$SMOKE_REPORT"

RUN_PHASE="setpoint_bridge"
start_keepalive "/uav1/mavros/setpoint_raw/local" "/uav1/planning/pos_cmd" 0.0 0.0 1.0
start_keepalive "/uav2/mavros/setpoint_raw/local" "/uav2/planning/pos_cmd" 0.0 0.0 1.0
start_watchdog uav1
start_watchdog uav2
sleep 2

RUN_PHASE="plan_generation"
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --course-spec "$PROJECT_DIR/config/maps/predicted_narrow_course_v1.json" \
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

if [ "$EXECUTOR_EXIT_CODE" -ne 0 ]; then
  safe_land_disarm || true
fi

python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py" \
  --smoke-report "$SMOKE_REPORT" \
  --events "$EVENTS" \
  --trace "$TRACE" \
  --score "$SCORE" \
  --executor-log "$EXECUTOR_LOG" \
  --executor-exit-code "$EXECUTOR_EXIT_CODE" \
  --run-id "$RUN_ID" \
  --phase "complete" \
  --provenance "$OUTPUT_DIR/provenance.json" \
  --report "$FLIGHT_REPORT"
REPORT_EXIT_CODE=$?
set -e

if [ "$REPORT_EXIT_CODE" -ne 0 ]; then
  safe_land_disarm || true
  echo "[ERROR] Stage 7 flight failed; inspect $FLIGHT_REPORT and $EXECUTOR_LOG" >&2
  tail -n 40 "$EXECUTOR_LOG" >&2 || true
fi
exit "$REPORT_EXIT_CODE"
