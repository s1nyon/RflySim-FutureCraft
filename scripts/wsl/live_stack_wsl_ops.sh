#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
#
# Explicit-PID-only WSL process operations for the safe live-stack lifecycle.
# This helper NEVER kills by name/pattern and NEVER shuts down a WSL distro.
set -euo pipefail

PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"

usage() {
  cat <<'EOF'
usage: live_stack_wsl_ops.sh <command> [args]
  snapshot                          print ps table (pid ppid pgid lstart args)
  sim-id                            print current PX4 simulation instance id
  alive <pid>                       exit 0 if the explicit pid is alive
  signal <SIG> <pid>                send SIG (INT|TERM|KILL) to the explicit pid
EOF
  exit 2
}

case "${1:-}" in
  snapshot)
    ps -eo pid=,ppid=,pgid=,lstart=,args=
    ;;
  sim-id)
    source "$PROJECT_DIR/scripts/wsl/stage7_run_context.sh"
    stage7_current_simulation_instance_id
    ;;
  alive)
    pid="${2:-}"
    if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
      usage
    fi
    kill -0 -- "$pid" 2>/dev/null
    ;;
  signal)
    sig="${2:-}"
    pid="${3:-}"
    if [[ "$sig" != INT && "$sig" != TERM && "$sig" != KILL ]]; then
      usage
    fi
    if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
      usage
    fi
    kill -"$sig" -- "$pid"
    ;;
  *)
    usage
    ;;
esac
