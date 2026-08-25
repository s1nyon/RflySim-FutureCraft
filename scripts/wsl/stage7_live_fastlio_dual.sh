#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lifecycle_common.sh"
PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage7_live"
CURRENT_RUN_FILE="$OUTPUT_DIR/current_run.env"
RUN_ID="stage7-$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$OUTPUT_DIR/$RUN_ID"
READINESS_REPORT="$RUN_DIR/sensor_readiness.json"
READINESS_LOG="$RUN_DIR/sensor_readiness.log"
FASTLIO_LOG="$RUN_DIR/fastlio_dual.log"
SENSOR_STARTUP_TIMEOUT_SEC="${STAGE7_SENSOR_STARTUP_TIMEOUT_SEC:-120}"
READINESS_TOPIC_TIMEOUT_SEC="${STAGE7_READINESS_TOPIC_TIMEOUT_SEC:-10}"
ODOM_INIT_TIMEOUT_SEC="${STAGE7_ODOM_INIT_TIMEOUT_SEC:-60}"
MAVROS_FEEDBACK_INIT_TIMEOUT_SEC="${STAGE7_MAVROS_FEEDBACK_INIT_TIMEOUT_SEC:-90}"
SENSOR_MODE="${STAGE7_SENSOR_MODE:-lidar_only}"

FASTLIO_SESSION_PGID="$(ps -o pgid= -p $$ | tr -d ' ')"
stack_register wsl "$$" "$FASTLIO_SESSION_PGID" "wsl:fastlio_session" \
  "stage7_live_fastlio_dual.sh" \
  "self-registered Stage 7 FAST-LIO launcher before creating child processes"

if ! [[ "$SENSOR_STARTUP_TIMEOUT_SEC" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERROR] STAGE7_SENSOR_STARTUP_TIMEOUT_SEC must be a positive integer" >&2
  exit 2
fi
if ! [[ "$READINESS_TOPIC_TIMEOUT_SEC" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERROR] STAGE7_READINESS_TOPIC_TIMEOUT_SEC must be a positive integer" >&2
  exit 2
fi
if ! [[ "$ODOM_INIT_TIMEOUT_SEC" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERROR] STAGE7_ODOM_INIT_TIMEOUT_SEC must be a positive integer" >&2
  exit 2
fi
if ! [[ "$MAVROS_FEEDBACK_INIT_TIMEOUT_SEC" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ERROR] STAGE7_MAVROS_FEEDBACK_INIT_TIMEOUT_SEC must be a positive integer" >&2
  exit 2
fi
case "$SENSOR_MODE" in
  lidar_only|full) ;;
  *) echo "[ERROR] STAGE7_SENSOR_MODE must be lidar_only or full" >&2; exit 2 ;;
esac

mkdir -p "$RUN_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" --extend
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

SIMULATION_INSTANCE_ID="$(stage7_current_simulation_instance_id)"

printf 'STAGE7_RUN_ID=%q\n' "$RUN_ID" >"$CURRENT_RUN_FILE"
printf 'STAGE7_SIMULATION_INSTANCE_ID=%q\n' "$SIMULATION_INSTANCE_ID" >>"$CURRENT_RUN_FILE"
printf 'STAGE7_READINESS_REPORT=%q\n' "$READINESS_REPORT" >>"$CURRENT_RUN_FILE"
printf 'STAGE7_RUN_DIR=%q\n' "$RUN_DIR" >>"$CURRENT_RUN_FILE"

topic_has_publisher() {
  local topic="$1"
  local info
  info="$(timeout 3s rostopic info "$topic" 2>/dev/null || true)"
  [[ "$info" == *"Publishers:"* && "$info" != *"Publishers: None"* ]]
}

SENSOR_PIDS=()
SENSOR_PGIDS=()

cleanup_sensor_bridges() {
  # Registered handles only: SIGTERM -> wait -> verified SIGKILL per owned PGID/PID.
  local idx pid pgid
  for idx in "${!SENSOR_PIDS[@]}"; do
    pid="${SENSOR_PIDS[$idx]}"
    pgid="${SENSOR_PGIDS[$idx]}"
    kill -TERM -- "-$pgid" >/dev/null 2>&1 || kill -TERM -- "$pid" >/dev/null 2>&1 || true
  done
  sleep 2
  for idx in "${!SENSOR_PIDS[@]}"; do
    pid="${SENSOR_PIDS[$idx]}"
    pgid="${SENSOR_PGIDS[$idx]}"
    if kill -0 -- "-$pgid" >/dev/null 2>&1 || kill -0 -- "$pid" >/dev/null 2>&1; then
      kill -KILL -- "-$pgid" >/dev/null 2>&1 || kill -KILL -- "$pid" >/dev/null 2>&1 || true
    fi
  done
  sleep 1
}

FASTLIO_PID=""
cleanup_stage7_run() {
  set +e
  if [[ -n "$FASTLIO_PID" ]] && kill -0 "$FASTLIO_PID" >/dev/null 2>&1; then
    kill -TERM -- "-$FASTLIO_PID" >/dev/null 2>&1 || kill -TERM "$FASTLIO_PID" >/dev/null 2>&1
    for _attempt in $(seq 1 5); do
      if ! kill -0 "$FASTLIO_PID" >/dev/null 2>&1 && ! kill -0 -- "-$FASTLIO_PID" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if kill -0 "$FASTLIO_PID" >/dev/null 2>&1; then
      kill -KILL -- "-$FASTLIO_PID" >/dev/null 2>&1 || kill -KILL "$FASTLIO_PID" >/dev/null 2>&1
    fi
    wait "$FASTLIO_PID" >/dev/null 2>&1
  fi
  cleanup_sensor_bridges
}

handle_shutdown() {
  exit 130
}

cleanup_sensor_bridges
trap cleanup_stage7_run EXIT
trap handle_shutdown INT TERM
setsid nohup env ROS_NAMESPACE=/uav1 python3 \
  "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py" \
  --psp-path "${PSP_PATH_LINUX:-/mnt/d/PX4PSP}" \
  --config "$PROJECT_DIR/config/rflysim_sensor_uav1.json" \
  --change-mode 1 \
  --copter-id 1 \
  --sensor-seq-id 0 \
  --udp-port 9999 \
  --raw-lidar-topic /rflysim/sensor0/mid360_lidar \
  --raw-imu-topic /uav1/rflysim/imu_raw \
  --identity-topic /uav1/rflysim/sensor_identity \
  --process-start-marker "$RUN_ID:uav1:bridge" \
  --sensor-mode "$SENSOR_MODE" \
  --imu-rate-hz 200 \
  --keepalive \
  __name:=rflysim_sensor_bridge \
  /uav1/rflysim/imu:=/uav1/rflysim/imu_raw >"$RUN_DIR/uav1_sensor_bridge.log" 2>&1 &
SENSOR_PIDS+=("$!")
SENSOR_PGIDS+=("$!")
stack_register wsl "$!" "$!" "wsl:sensor_bridge_uav1" \
  "python3 .../rflysim_sensor_bridge.py --copter-id 1 --sensor-mode $SENSOR_MODE" \
  "created by stage7_live_fastlio_dual.sh (setsid)"

setsid nohup env ROS_NAMESPACE=/uav2 python3 \
  "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py" \
  --psp-path "${PSP_PATH_LINUX:-/mnt/d/PX4PSP}" \
  --config "$PROJECT_DIR/config/rflysim_sensor_uav2.json" \
  --change-mode 1 \
  --copter-id 2 \
  --sensor-seq-id 10 \
  --udp-port 10009 \
  --raw-lidar-topic /rflysim/sensor10/mid360_lidar \
  --raw-imu-topic /uav2/rflysim/imu_raw \
  --identity-topic /uav2/rflysim/sensor_identity \
  --process-start-marker "$RUN_ID:uav2:bridge" \
  --sensor-mode "$SENSOR_MODE" \
  --imu-rate-hz 200 \
  --keepalive \
  __name:=rflysim_sensor_bridge \
  /uav2/rflysim/imu:=/uav2/rflysim/imu_raw >"$RUN_DIR/uav2_sensor_bridge.log" 2>&1 &
SENSOR_PIDS+=("$!")
SENSOR_PGIDS+=("$!")
stack_register wsl "$!" "$!" "wsl:sensor_bridge_uav2" \
  "python3 .../rflysim_sensor_bridge.py --copter-id 2 --sensor-mode $SENSOR_MODE" \
  "created by stage7_live_fastlio_dual.sh (setsid)"

RAW_TOPICS=(
  /uav1/rflysim/sensor_identity
  /rflysim/sensor0/mid360_lidar
  /uav1/rflysim/imu_raw
  /uav2/rflysim/sensor_identity
  /rflysim/sensor10/mid360_lidar
  /uav2/rflysim/imu_raw
)
SENSOR_STARTUP_DEADLINE=$((SECONDS + SENSOR_STARTUP_TIMEOUT_SEC))
while (( SECONDS < SENSOR_STARTUP_DEADLINE )); do
  all_ready=true
  for topic in "${RAW_TOPICS[@]}"; do
    if ! topic_has_publisher "$topic"; then
      all_ready=false
      break
    fi
  done
  if [ "$all_ready" = true ]; then
    break
  fi
  sleep 1
done
for topic in "${RAW_TOPICS[@]}"; do
  if ! topic_has_publisher "$topic"; then
    echo "[ERROR] Identified sensor topic has no publisher: $topic" >&2
    exit 1
  fi
done

setsid nohup roslaunch multi_uav_mission rflysim_fastlio_dual.launch rviz:=false \
  >"$FASTLIO_LOG" 2>&1 &
FASTLIO_PID=$!
stack_register wsl "$FASTLIO_PID" "$FASTLIO_PID" "wsl:fastlio" \
  "roslaunch multi_uav_mission rflysim_fastlio_dual.launch rviz:=false" \
  "created by stage7_live_fastlio_dual.sh (setsid)"

# Wait for the FAST-LIO odometry chain to come up before sampling readiness.
# This is a publisher-presence gate (initialization wait), intentionally
# separate from the per-topic message timeout used by the readiness sampler:
# on a cold start the relay only begins publishing after lidar bridge ->
# adapter -> FAST-LIO initialization, which can take longer than the
# readiness topic timeout.  Do not widen the message timeout to absorb this.
ODOM_INIT_DEADLINE=$((SECONDS + ODOM_INIT_TIMEOUT_SEC))
while (( SECONDS < ODOM_INIT_DEADLINE )); do
  odom_ready=true
  for topic in /uav1/mavros/odometry/out /uav2/mavros/odometry/out; do
    if ! topic_has_publisher "$topic"; then
      odom_ready=false
      break
    fi
  done
  if [ "$odom_ready" = true ]; then
    break
  fi
  sleep 1
done
for topic in /uav1/mavros/odometry/out /uav2/mavros/odometry/out; do
  if ! topic_has_publisher "$topic"; then
    echo "[ERROR] FAST-LIO odometry relay did not publish $topic within ${ODOM_INIT_TIMEOUT_SEC}s" >&2
    exit 1
  fi
done
echo "[INFO] FAST-LIO odometry relay publishers ready after $((SECONDS))s"

# PX4 needs several external-odometry samples before MAVROS emits local
# position.  Publisher presence alone is insufficient: wait for a real
# feedback message before the strict, run-scoped readiness sampler starts.
MAVROS_FEEDBACK_DEADLINE=$((SECONDS + MAVROS_FEEDBACK_INIT_TIMEOUT_SEC))
while (( SECONDS < MAVROS_FEEDBACK_DEADLINE )); do
  feedback_ready=true
  for topic in /uav1/mavros/local_position/odom /uav2/mavros/local_position/odom; do
    if ! timeout 2s rostopic echo -n 1 "$topic" >/dev/null 2>&1; then
      feedback_ready=false
      break
    fi
  done
  if [ "$feedback_ready" = true ]; then
    break
  fi
  sleep 1
done
for topic in /uav1/mavros/local_position/odom /uav2/mavros/local_position/odom; do
  if ! timeout 3s rostopic echo -n 1 "$topic" >/dev/null 2>&1; then
    echo "[ERROR] MAVROS local-position feedback did not publish $topic within ${MAVROS_FEEDBACK_INIT_TIMEOUT_SEC}s" >&2
    exit 1
  fi
done
echo "[INFO] MAVROS local-position feedback ready after $((SECONDS))s"

set +e
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --backend ros \
  --timeout-s "$READINESS_TOPIC_TIMEOUT_SEC" \
  --run-id "$RUN_ID" \
  --simulation-instance-id "$SIMULATION_INSTANCE_ID" \
  --report "$READINESS_REPORT" 2>&1 | tee "$READINESS_LOG"
READINESS_EXIT_CODE=${PIPESTATUS[0]}
set -e
if [ "$READINESS_EXIT_CODE" -ne 0 ]; then
  echo "[ERROR] Stage 7 no-arm readiness failed; inspect $READINESS_REPORT" >&2
  exit "$READINESS_EXIT_CODE"
fi

echo "[PASS] Stage 7 no-arm readiness accepted: $READINESS_REPORT"
wait "$FASTLIO_PID"
