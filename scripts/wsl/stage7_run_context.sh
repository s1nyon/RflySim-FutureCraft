#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.

stage7_current_simulation_instance_id() {
  local px4_process_state
  px4_process_state="$(ps -eo pid=,lstart=,args= | grep '[p]x4' | sort || true)"
  if [ -z "$px4_process_state" ]; then
    echo "[ERROR] No PX4 process was found for the Stage 7 simulation instance." >&2
    return 1
  fi
  printf 'px4-%s\n' "$(printf '%s\n' "$px4_process_state" | sha256sum | cut -c1-16)"
}

stage7_load_run_context() {
  local project_dir="$1"
  local current_run_file="$project_dir/logs/stage7_live/current_run.env"
  if [ ! -f "$current_run_file" ]; then
    echo "[ERROR] Stage 7 current run metadata is missing: $current_run_file" >&2
    return 1
  fi
  source "$current_run_file"
  : "${STAGE7_RUN_ID:?missing STAGE7_RUN_ID}"
  : "${STAGE7_SIMULATION_INSTANCE_ID:?missing STAGE7_SIMULATION_INSTANCE_ID}"
  : "${STAGE7_READINESS_REPORT:?missing STAGE7_READINESS_REPORT}"
  : "${STAGE7_RUN_DIR:?missing STAGE7_RUN_DIR}"
  STAGE7_CURRENT_SIMULATION_INSTANCE_ID="$(stage7_current_simulation_instance_id)"
  if [ "$STAGE7_CURRENT_SIMULATION_INSTANCE_ID" != "$STAGE7_SIMULATION_INSTANCE_ID" ]; then
    echo "[ERROR] PX4 simulation instance changed after Stage 7 readiness collection." >&2
    return 1
  fi
  export STAGE7_RUN_ID STAGE7_SIMULATION_INSTANCE_ID STAGE7_CURRENT_SIMULATION_INSTANCE_ID
  export STAGE7_READINESS_REPORT STAGE7_RUN_DIR
}
