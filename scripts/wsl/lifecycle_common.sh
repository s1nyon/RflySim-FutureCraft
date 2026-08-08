#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
#
# Shared lifecycle helpers for WSL launchers. Ownership is granted ONLY at
# creation time: each launcher registers the PID/PGID it obtained when it
# created the process. Scanning/name/regex claiming is forbidden.
set -euo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
STACK_MANIFEST="${STACK_MANIFEST:-}"
STACK_REGISTER="$PROJECT_DIR/scripts/lifecycle/stack_register.py"

stack_register() {
  local side="$1" pid="$2" pgid="$3" role="$4" cmdline="$5" reason="$6"
  if [[ -z "$STACK_MANIFEST" ]]; then
    echo "[lifecycle] WARN: STACK_MANIFEST unset; pid $pid ($role) will be unknown to lifecycle" >&2
    return 0
  fi
  local args=(--manifest "$STACK_MANIFEST" --side "$side" --pid "$pid" --role "$role" --cmdline "$cmdline" --reason "$reason")
  if [[ -n "$pgid" ]]; then
    args+=(--pgid "$pgid")
  fi
  python3 "$STACK_REGISTER" register "${args[@]}" >/dev/null 2>&1 || \
    echo "[lifecycle] WARN: registration failed for $role pid=$pid" >&2
}
