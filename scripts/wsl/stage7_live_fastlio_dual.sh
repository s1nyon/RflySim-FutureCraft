#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
OUTPUT_DIR="$PROJECT_DIR/logs/stage7_live"
SENSOR_LOG="$OUTPUT_DIR/sensor_bridge.log"
FASTLIO_LOG="$OUTPUT_DIR/fastlio_dual.log"
LIDAR_TOPIC="${STAGE7_LIDAR_TOPIC:-/rflysim/sensor0/mid360_lidar}"
IMU_TOPIC="${STAGE7_IMU_TOPIC:-/rflysim/imu}"

mkdir -p "$OUTPUT_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"
if [ -f "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash" ]; then
  source "$PROJECT_DIR/future_aircraft_ws/devel/setup.bash"
else
  export ROS_PACKAGE_PATH="$PROJECT_DIR/future_aircraft_ws/src:${ROS_PACKAGE_PATH:-}"
fi
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

topic_has_publisher() {
  local topic="$1"
  local info
  info="$(timeout 3s rostopic info "$topic" 2>/dev/null || true)"
  [[ "$info" == *"Publishers:"* && "$info" != *"Publishers: None"* ]]
}

if ! topic_has_publisher "$IMU_TOPIC" || ! topic_has_publisher "$LIDAR_TOPIC"; then
  pkill -f "[r]flysim_sensor_bridge.py" >/dev/null 2>&1 || true
  sleep 1
  nohup python3 "$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py" \
    --psp-path "${PSP_PATH_LINUX:-/mnt/d/PX4PSP}" \
    --config "$REF_28COM_UAV_WSL_DIR/sensor_pkg/Config.json" \
    --change-mode 1 \
    --copter-id 1 \
    --imu-rate-hz 200 \
    --keepalive > "$SENSOR_LOG" 2>&1 &
fi

for _attempt in $(seq 1 10); do
  if topic_has_publisher "$IMU_TOPIC" && topic_has_publisher "$LIDAR_TOPIC"; then
    break
  fi
  sleep 1
done

exec roslaunch multi_uav_mission rflysim_fastlio_dual.launch rviz:=false 2>&1 | tee "$FASTLIO_LOG"
