#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
#
# Waits for the stack health gate (logs/live_stack/<stack_id>/health.json) to
# become all-ready. Used by start_wsl_mavros_two.bat and the lifecycle wrappers.
set -euo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
HEALTH_DIR="${STACK_HEALTH_DIR:-}"
WAIT_SECONDS="${STAGE2_HEALTH_WAIT_SECONDS:-180}"

if [[ "${1:-}" == "--wait-seconds" ]]; then
  WAIT_SECONDS="${2:-180}"
fi

if [[ -z "$HEALTH_DIR" ]]; then
  echo "[ERROR] STACK_HEALTH_DIR is not set" >&2
  exit 2
fi

HEALTH_FILE="$HEALTH_DIR/health.json"
deadline=$((SECONDS + WAIT_SECONDS))
while (( SECONDS < deadline )); do
  if [[ -f "$HEALTH_FILE" ]] && python3 "$PROJECT_DIR/scripts/lifecycle/health_probe.py" check \
      --health-dir "$HEALTH_DIR" --wait-seconds 0 >/dev/null 2>&1; then
    echo "[PASS] stack health gate all ready"
    python3 "$PROJECT_DIR/scripts/lifecycle/health_probe.py" check --health-dir "$HEALTH_DIR" --wait-seconds 0
    exit 0
  fi
  sleep 5
done

echo "[ERROR] stack health gate not ready within ${WAIT_SECONDS}s" >&2
python3 "$PROJECT_DIR/scripts/lifecycle/health_probe.py" check --health-dir "$HEALTH_DIR" --wait-seconds 0 || true
exit 1
