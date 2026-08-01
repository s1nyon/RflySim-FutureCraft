#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
REF_28COM_UAV_WSL_DIR="${REF_28COM_UAV_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav}"
CONFIG="$PROJECT_DIR/config/stage2_1_mavlink_link.json"
OUTPUT_DIR="$PROJECT_DIR/logs/stage2_1_live"
PX4_LOG="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/instance_1/out.log"
VERIFIER="$PROJECT_DIR/future_aircraft_ws/src/multi_uav_mission/scripts/mavlink_return_path_check.py"

if [[ "${1:-}" == "--dry-run" ]]; then
  temp_report="$(mktemp)"
  trap 'rm -f "$temp_report"' EXIT
  python3 "$VERIFIER" --config "$CONFIG" --backend dry-run --report "$temp_report"
  exit 0
fi

mkdir -p "$OUTPUT_DIR"
source /opt/ros/noetic/setup.bash
source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"

if [[ ! -f "$PX4_LOG" ]]; then
  echo "[ERROR] PX4 log is missing: $PX4_LOG" >&2
  exit 1
fi

(
  cd "$(dirname "$PX4_LOG")"
  px4-mavlink --instance 1 status
) >> "$PX4_LOG"

python3 "$VERIFIER" \
  --config "$CONFIG" \
  --backend ros \
  --px4-log "$PX4_LOG" \
  --report "$OUTPUT_DIR/mavlink_link_report.json"
