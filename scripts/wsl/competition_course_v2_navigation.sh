#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -Eeo pipefail

ALLOW_ARM=false
SIMULATION_ONLY=false
PROFILE="${V2_PROFILE:-}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --allow-arm) ALLOW_ARM=true; shift ;;
    --simulation-only) SIMULATION_ONLY=true; shift ;;
    *) echo "[ERROR] Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ "$PROFILE" != "short_smoke" ] && [ "$PROFILE" != "full_section_a" ]; then
  echo "[ERROR] --profile must be short_smoke or full_section_a." >&2
  exit 2
fi
if [ "$ALLOW_ARM" != true ] || [ "$SIMULATION_ONLY" != true ]; then
  echo "[ERROR] V2 navigation requires --allow-arm --simulation-only." >&2
  exit 1
fi
: "${STACK_ID:?STACK_ID is required}"
: "${STACK_MANIFEST:?STACK_MANIFEST is required}"
if [ ! -f "$STACK_MANIFEST" ]; then
  echo "[ERROR] Explicit stack manifest is missing: $STACK_MANIFEST" >&2
  exit 1
fi

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
EGO_SWARM_WSL_DIR="${EGO_SWARM_WSL_DIR:-$PROJECT_DIR/third_party/ego-planner-swarm}"
SCRIPTS="$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts"
MAP_SPEC="$PROJECT_DIR/config/maps/competition_course_v2.json"
NAV_CONFIG="$PROJECT_DIR/config/competition_course_v2_navigation.json"
LIVE_CONFIG="$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json"
EXECUTOR_CONFIG="$PROJECT_DIR/config/stage5_live_mission.json"
STACK_REGISTER="$PROJECT_DIR/scripts/lifecycle/stack_register.py"
READINESS_MAX_AGE_SEC="${STAGE7_READINESS_MAX_AGE_SEC:-120}"
export PYTHONPATH="$SCRIPTS:${PYTHONPATH:-}"

source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
if [ ! -f "$EGO_SWARM_WSL_DIR/devel/setup.bash" ]; then
  echo "[ERROR] ego-planner-swarm is not built: $EGO_SWARM_WSL_DIR/devel/setup.bash" >&2
  exit 1
fi
source "$EGO_SWARM_WSL_DIR/devel/setup.bash"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" --extend
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
stage7_load_run_context "$PROJECT_DIR"

SPEC_SHA256="$(python3 - "$STACK_MANIFEST" "$STACK_ID" "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" "$MAP_SPEC" "$PROJECT_DIR/generated/competition_course_v2/entity_manifest.json" "$PROJECT_DIR/logs/live_stack/$STACK_ID/competition_course_v2/load_receipt.json" <<'PY'
import json
import sys
from pathlib import Path
from competition_course_geometry import build_entity_manifest, load_spec
from competition_course_ue_loader import validated_runtime_entities

manifest_path, stack_id, simulation_id, spec_path, entity_path, receipt_path = sys.argv[1:]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
if manifest.get("stack_id") != stack_id:
    raise SystemExit("[ERROR] explicit stack ID does not match manifest")
if manifest.get("simulation_instance_id") != simulation_id:
    raise SystemExit("[ERROR] current PX4 simulation instance does not match manifest")
health_dir = Path(manifest_path).parent / "health"
required = ("GUI_READY", "ROSCORE_READY", "MAVROS_UAV1_CONNECTED", "MAVROS_UAV2_CONNECTED", "COURSE_READY")
for name in required:
    entry = json.loads((health_dir / (name + ".json")).read_text(encoding="utf-8"))
    if entry.get("stack_id") != stack_id or entry.get("status") != name or entry.get("ready") is not True:
        raise SystemExit("[ERROR] stack health status is not READY: " + name)
course = json.loads((health_dir / "COURSE_READY.json").read_text(encoding="utf-8"))
if "competition course v2" not in str(course.get("detail", "")).lower():
    raise SystemExit("[ERROR] COURSE_READY does not attest Competition Course V2")
spec = load_spec(Path(spec_path))
entity_manifest = json.loads(Path(entity_path).read_text(encoding="utf-8"))
expected = validated_runtime_entities(spec, entity_manifest)
receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
if receipt.get("map_id") != spec["map_id"] or receipt.get("spec_sha256") != spec["spec_sha256"]:
    raise SystemExit("[ERROR] live course receipt does not match authoritative spec")
if receipt.get("stack_id") != stack_id or receipt.get("simulation_instance_id") != simulation_id:
    raise SystemExit("[ERROR] live course receipt is not owned by this stack/instance")
if receipt.get("cleanup_policy") != "receipt_only":
    raise SystemExit("[ERROR] live course receipt cleanup policy mismatch")
if receipt.get("created_ids") != [item["id"] for item in expected]:
    raise SystemExit("[ERROR] live course receipt entity IDs do not match spec-derived manifest")
print(spec["spec_sha256"])
PY
)"

python3 "$SCRIPTS/stage7_sensor_readiness.py" --validate \
  --report "$STAGE7_READINESS_REPORT" \
  --run-id "$STAGE7_RUN_ID" \
  --simulation-instance-id "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" \
  --max-age-sec "$READINESS_MAX_AGE_SEC"

V2_RUN_ID="v2-nav-$(date -u +%Y%m%dT%H%M%SZ)-${PROFILE}"
OUTPUT_DIR="$PROJECT_DIR/logs/competition_course_v2_navigation/$STACK_ID/$V2_RUN_ID"
mkdir -p "$OUTPUT_DIR"
PLAN="$OUTPUT_DIR/navigation_plan.json"
EVENTS="$OUTPUT_DIR/mission_events.jsonl"
TRACE="$OUTPUT_DIR/executor_trace.json"
SCORE="$OUTPUT_DIR/score_summary.json"
EXECUTOR_LOG="$OUTPUT_DIR/executor.log"
RECORDER_EVENTS="$OUTPUT_DIR/navigation_recorder.jsonl"
RECORDER_LOG="$OUTPUT_DIR/navigation_recorder.log"
FLIGHT_EVENTS="$OUTPUT_DIR/flight_events.jsonl"
FLIGHT_RECORDER_LOG="$OUTPUT_DIR/flight_event_recorder.log"
CRASH_RAW_STATUS="$OUTPUT_DIR/crash_monitor_raw_status.json"
COLLISION_COVERAGE="$OUTPUT_DIR/collision_monitor_coverage.json"
WATCHDOG_EVENTS="$OUTPUT_DIR/uav1_watchdog_events.jsonl"
WATCHDOG_LOG="$OUTPUT_DIR/uav1_watchdog.log"
SMOKE_REPORT="$OUTPUT_DIR/no_arm_control_chain_smoke.json"
REPORT="$OUTPUT_DIR/section_a_report.json"
RUNNER_LOG="$OUTPUT_DIR/runner.log"
RUN_CONTRACT="$OUTPUT_DIR/run_contract.json"
: >"$RUNNER_LOG"
exec > >(tee -a "$RUNNER_LOG") 2>&1

python3 "$SCRIPTS/competition_course_navigation_plan.py" \
  --config "$LIVE_CONFIG" --map-spec "$MAP_SPEC" --navigation-config "$NAV_CONFIG" \
  --profile "$PROFILE" --output "$PLAN"
python3 "$SCRIPTS/mission_executor.py" \
  --plan "$PLAN" --live-config "$EXECUTOR_CONFIG" --backend dry-run \
  --events "$OUTPUT_DIR/dry_run_mission_events.jsonl" \
  --trace "$OUTPUT_DIR/dry_run_executor_trace.json" \
  --score "$OUTPUT_DIR/dry_run_score_summary.json"

eval "$(python3 - "$PLAN" <<'PY'
import json
import shlex
import sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
for key, value in {
    "GF_MIN_X": plan["geofence"]["min_x"], "GF_MAX_X": plan["geofence"]["max_x"],
    "GF_MIN_Y": plan["geofence"]["min_y"], "GF_MAX_Y": plan["geofence"]["max_y"],
    "GF_MIN_Z": plan["geofence"]["min_z"], "GF_MAX_Z": plan["geofence"]["max_z"],
    "GF_MAX_SPEED": plan["geofence"]["max_speed_mps"],
    "GF_MAX_ODOM_AGE": plan["geofence"]["max_odom_age_s"],
    "INITIAL_Z": plan["actions"][1]["goal"]["z"],
    "TERMINAL_X": plan["navigation_contract"]["terminal_local"][0],
    "TERMINAL_Y": plan["navigation_contract"]["terminal_local"][1],
    "TERMINAL_Z": plan["navigation_contract"]["terminal_local"][2],
    "TERMINAL_FRAME": next(
        item["goal"]["frame_id"] for item in plan["actions"]
        if item["action"] == "publish_planner_goal"
    ),
}.items():
    print(key + "=" + shlex.quote(str(value)))
PY
)"

python3 "$SCRIPTS/ego_swarm_flight_smoke_check.py" \
  --config "$LIVE_CONFIG" --backend ros --timeout-s 10 --report "$SMOKE_REPORT"
for uav in uav1 uav2; do
  state="$(timeout 5s rostopic echo -n 1 "/$uav/mavros/state" 2>/dev/null || true)"
  if ! grep -q '^connected: True$' <<<"$state" || ! grep -q '^armed: False$' <<<"$state"; then
    echo "[ERROR] $uav is not connected and disarmed at the no-arm gate" >&2
    exit 1
  fi
  if grep -q '^mode:.*OFFBOARD' <<<"$state"; then
    echo "[ERROR] $uav unexpectedly entered OFFBOARD before the active task" >&2
    exit 1
  fi
done

python3 - "$RUN_CONTRACT" "$V2_RUN_ID" "$STACK_ID" "$STAGE7_RUN_ID" "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" "$SPEC_SHA256" "$PROFILE" <<'PY'
import json
import sys
import time
from pathlib import Path
path, run_id, stack_id, readiness_run_id, simulation_id, spec_sha, profile = sys.argv[1:]
value = {
    "created_at_wall_time": time.time(), "run_id": run_id, "stack_id": stack_id,
    "readiness_run_id": readiness_run_id, "simulation_instance_id": simulation_id,
    "map_id": "competition_course_v2", "spec_sha256": spec_sha, "profile": profile,
    "runtime_decision_source": "lidar_driven", "evaluation_truth_used": True,
    "truth_must_not_feed_control": True,
}
Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

register_owned() {
  local pid="$1" pgid="$2" role="$3" cmdline="$4" reason="$5"
  if ! python3 "$STACK_REGISTER" register --manifest "$STACK_MANIFEST" --side wsl \
    --pid "$pid" --pgid "$pgid" --role "$role" --cmdline "$cmdline" --reason "$reason"; then
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
    echo "[ERROR] fail-closed: ownership registration failed for $role" >&2
    return 1
  fi
}

RUNNER_PGID="$(ps -o pgid= -p $$ | tr -d ' ')"
python3 "$STACK_REGISTER" register --manifest "$STACK_MANIFEST" --side wsl \
  --pid "$$" --pgid "$RUNNER_PGID" --role "wsl:v2_navigation_runner" \
  --cmdline "competition_course_v2_navigation.sh --profile $PROFILE" \
  --reason "self-registered V2 navigation runner before creating child processes"

OWNED_CHILD_PIDS=()
cleanup_owned_children() {
  local pid
  for pid in "${OWNED_CHILD_PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      wait "$pid" >/dev/null 2>&1 || true
    fi
  done
}
remove_owned_child() {
  local removed_pid="$1" pid
  local remaining=()
  for pid in "${OWNED_CHILD_PIDS[@]}"; do
    if [ "$pid" != "$removed_pid" ]; then
      remaining+=("$pid")
    fi
  done
  OWNED_CHILD_PIDS=("${remaining[@]}")
}
trap cleanup_owned_children EXIT

safe_land_uav1() {
  local state
  state="$(timeout 3s rostopic echo -n 1 /uav1/mavros/state 2>/dev/null || true)"
  if ! grep -q '^armed: True$' <<<"$state"; then
    return 0
  fi
  echo "[WARN] Requesting UAV1 AUTO.LAND after V2 runner failure" >&2
  rosservice call /uav1/mavros/set_mode 0 AUTO.LAND >/dev/null || return 1
  for _attempt in $(seq 1 40); do
    state="$(timeout 3s rostopic echo -n 1 /uav1/mavros/state 2>/dev/null || true)"
    if grep -q '^armed: False$' <<<"$state"; then
      echo "[INFO] UAV1 disarm confirmed after AUTO.LAND"
      return 0
    fi
    sleep 1
  done
  echo "[ERROR] UAV1 remained armed after AUTO.LAND timeout; no force-disarm attempted" >&2
  return 1
}

handle_flight_signal() {
  local exit_code="$1"
  safe_land_uav1 || true
  exit "$exit_code"
}
trap 'handle_flight_signal 130' INT
trap 'handle_flight_signal 143' TERM

setsid python3 "$SCRIPTS/competition_course_navigation_recorder.py" \
  --spec "$MAP_SPEC" --output "$RECORDER_EVENTS" --duration-s 300 --roi-margin-m 0.015 \
  >"$RECORDER_LOG" 2>&1 &
RECORDER_PID=$!
OWNED_CHILD_PIDS+=("$RECORDER_PID")
register_owned "$RECORDER_PID" "$RECORDER_PID" "wsl:v2_navigation_recorder" \
  "python3 competition_course_navigation_recorder.py --spec competition_course_v2.json" \
  "created by V2 runner at process creation (setsid)"

setsid python3 "$SCRIPTS/flight_event_recorder.py" --uav uav1 \
  --min-x "$GF_MIN_X" --max-x "$GF_MAX_X" --min-y "$GF_MIN_Y" --max-y "$GF_MAX_Y" \
  --min-z "$GF_MIN_Z" --max-z "$GF_MAX_Z" --max-speed-mps "$GF_MAX_SPEED" \
  --output "$FLIGHT_EVENTS" --crash-listen --crash-status "$CRASH_RAW_STATUS" \
  --rflysim-root /mnt/d/PX4PSP >"$FLIGHT_RECORDER_LOG" 2>&1 &
FLIGHT_RECORDER_PID=$!
OWNED_CHILD_PIDS+=("$FLIGHT_RECORDER_PID")
register_owned "$FLIGHT_RECORDER_PID" "$FLIGHT_RECORDER_PID" "wsl:v2_flight_event_recorder" \
  "python3 flight_event_recorder.py --uav uav1 --crash-listen --crash-status" \
  "created by V2 runner at process creation (setsid)"

for _attempt in $(seq 1 20); do
  if [ -f "$CRASH_RAW_STATUS" ] && python3 - "$CRASH_RAW_STATUS" <<'PY'
import json, sys, time
value = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if value.get("available") is True and time.time() - float(value["last_heartbeat_wall_time"]) < 2.0 else 1)
PY
  then break; fi
  sleep 0.5
done
if [ ! -f "$CRASH_RAW_STATUS" ] || ! python3 - "$CRASH_RAW_STATUS" <<'PY'
import json, sys, time
value = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if value.get("available") is True and time.time() - float(value["last_heartbeat_wall_time"]) < 2.0 else 1)
PY
then
  echo "[ERROR] fail-closed: authoritative RflySim crash listener is unavailable" >&2
  exit 1
fi

setsid python3 "$SCRIPTS/ego_swarm_setpoint_bridge.py" \
  --setpoint-topic /uav1/mavros/setpoint_raw/local --planner-topic /uav1/planning/pos_cmd \
  --initial-x 0.0 --initial-y 0.0 --initial-z "$INITIAL_Z" \
  --wait-for-matching-planner-goal --goal-topic /uav1/planning/goal \
  --expected-goal-frame "$TERMINAL_FRAME" \
  --expected-goal-x "$TERMINAL_X" --expected-goal-y "$TERMINAL_Y" --expected-goal-z "$TERMINAL_Z" \
  --min-x "$GF_MIN_X" --max-x "$GF_MAX_X" --min-y "$GF_MIN_Y" --max-y "$GF_MAX_Y" \
  --min-z "$GF_MIN_Z" --max-z "$GF_MAX_Z" --yaw 0.0 --rate-hz 20 \
  >"$OUTPUT_DIR/uav1_setpoint_bridge.log" 2>&1 &
BRIDGE_PID=$!
OWNED_CHILD_PIDS+=("$BRIDGE_PID")
register_owned "$BRIDGE_PID" "$BRIDGE_PID" "wsl:v2_uav1_setpoint_bridge" \
  "python3 ego_swarm_setpoint_bridge.py --setpoint-topic /uav1/mavros/setpoint_raw/local" \
  "created by V2 runner at process creation (setsid)"

setsid python3 "$SCRIPTS/course_geofence_watchdog.py" \
  --state-topic /uav1/mavros/state --odom-topic /uav1/mavros/local_position/odom \
  --set-mode-service /uav1/mavros/set_mode \
  --min-x "$GF_MIN_X" --max-x "$GF_MAX_X" --min-y "$GF_MIN_Y" --max-y "$GF_MAX_Y" \
  --min-z "$GF_MIN_Z" --max-z "$GF_MAX_Z" --max-speed-mps "$GF_MAX_SPEED" \
  --max-odom-age-s "$GF_MAX_ODOM_AGE" --output "$WATCHDOG_EVENTS" \
  >"$WATCHDOG_LOG" 2>&1 &
WATCHDOG_PID=$!
OWNED_CHILD_PIDS+=("$WATCHDOG_PID")
register_owned "$WATCHDOG_PID" "$WATCHDOG_PID" "wsl:v2_uav1_geofence_watchdog" \
  "python3 course_geofence_watchdog.py --state-topic /uav1/mavros/state" \
  "created by V2 runner at process creation (setsid)"

sleep 2
for pid in "$RECORDER_PID" "$FLIGHT_RECORDER_PID" "$BRIDGE_PID" "$WATCHDOG_PID"; do
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "[ERROR] fail-closed: owned V2 child process exited before arm" >&2
    exit 1
  fi
done

ACTIVE_START_WALL_TIME="$(python3 -c 'import time; print(time.time())')"
setsid python3 "$SCRIPTS/mission_executor.py" \
  --plan "$PLAN" --live-config "$EXECUTOR_CONFIG" --backend ros \
  --allow-arm --simulation-only --events "$EVENTS" --trace "$TRACE" --score "$SCORE" \
  >"$EXECUTOR_LOG" 2>&1 &
EXECUTOR_PID=$!
OWNED_CHILD_PIDS+=("$EXECUTOR_PID")
register_owned "$EXECUTOR_PID" "$EXECUTOR_PID" "wsl:v2_mission_executor" \
  "python3 mission_executor.py --plan $PLAN --allow-arm --simulation-only" \
  "created by V2 runner at process creation (setsid)"
set +e
wait "$EXECUTOR_PID"
EXECUTOR_EXIT_CODE=$?
set -e
remove_owned_child "$EXECUTOR_PID"
ACTIVE_END_WALL_TIME="$(python3 -c 'import time; print(time.time())')"

if [ "$EXECUTOR_EXIT_CODE" -ne 0 ]; then
  safe_land_uav1 || true
fi
sleep 1
cleanup_owned_children
OWNED_CHILD_PIDS=()
python3 - "$CRASH_RAW_STATUS" "$COLLISION_COVERAGE" "$ACTIVE_START_WALL_TIME" "$ACTIVE_END_WALL_TIME" <<'PY'
import json
import sys
from pathlib import Path
raw_path, output_path, active_start, active_end = sys.argv[1:]
try:
    value = json.loads(Path(raw_path).read_text(encoding="utf-8"))
except Exception as exc:
    value = {"available": False, "source": "rflysim_reqVeCrashData_udp_20006", "error": str(exc)}
value["active_start_wall_time"] = float(active_start)
value["active_end_wall_time"] = float(active_end)
Path(output_path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

set +e
python3 "$SCRIPTS/competition_course_navigation_report.py" \
  --plan "$PLAN" --spec "$MAP_SPEC" --mission-events "$EVENTS" \
  --recorder-events "$RECORDER_EVENTS" --flight-events "$FLIGHT_EVENTS" \
  --watchdog-events "$WATCHDOG_EVENTS" --collision-monitor "$COLLISION_COVERAGE" \
  --executor-exit-code "$EXECUTOR_EXIT_CODE" --output "$REPORT"
REPORT_EXIT_CODE=$?
set -e
if [ "$REPORT_EXIT_CODE" -ne 0 ]; then
  safe_land_uav1 || true
  echo "[ERROR] V2 Section A acceptance failed; inspect $REPORT" >&2
fi
exit "$REPORT_EXIT_CODE"
