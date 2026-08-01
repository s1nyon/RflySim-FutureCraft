#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage7_live"
CURRENT_RUN_FILE="$OUTPUT_DIR/current_run.env"
RUN_ID="stage7-$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$OUTPUT_DIR/$RUN_ID"
READINESS_REPORT="$RUN_DIR/sensor_readiness.json"
READINESS_LOG="$RUN_DIR/sensor_readiness.log"
FASTLIO_LOG="$RUN_DIR/fastlio_dual.log"

mkdir -p "$RUN_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash"
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

pkill -f '[r]flysim_sensor_bridge.py' >/dev/null 2>&1 || true
sleep 1
nohup env ROS_NAMESPACE=/uav1 python3 \
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
  --imu-rate-hz 200 \
  --keepalive \
  __name:=rflysim_sensor_bridge \
  /rflysim/imu:=/uav1/rflysim/imu_raw >"$RUN_DIR/uav1_sensor_bridge.log" 2>&1 &

nohup env ROS_NAMESPACE=/uav2 python3 \
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
  --imu-rate-hz 200 \
  --keepalive \
  __name:=rflysim_sensor_bridge \
  /rflysim/imu:=/uav2/rflysim/imu_raw >"$RUN_DIR/uav2_sensor_bridge.log" 2>&1 &

RAW_TOPICS=(
  /uav1/rflysim/sensor_identity
  /rflysim/sensor0/mid360_lidar
  /uav1/rflysim/imu_raw
  /uav2/rflysim/sensor_identity
  /rflysim/sensor10/mid360_lidar
  /uav2/rflysim/imu_raw
)
for _attempt in $(seq 1 20); do
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

nohup roslaunch multi_uav_mission rflysim_fastlio_dual.launch rviz:=false \
  >"$FASTLIO_LOG" 2>&1 &
FASTLIO_PID=$!

set +e
python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py" \
  --config "$PROJECT_DIR/config/stage7_live_slam_ego_swarm.json" \
  --backend ros \
  --timeout-s 3 \
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
