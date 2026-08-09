#!/usr/bin/env bash
# Build future_aircraft_ws (ROS1 Noetic) and export compile_commands.json
# for VS Code C/C++ IntelliSense.
#
# Usage:
#   bash scripts/wsl/build_future_aircraft_ws.sh [extra catkin_make args...]
#
# Sources ego-planner-swarm devel BEFORE the project workspace, mirroring the
# live flight chain, so quadrotor_msgs resolves to the planner's message
# definitions.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WS_DIR="${REPO_ROOT}/future_aircraft_ws"
EGO_DEVEL="${REPO_ROOT}/third_party/ego-planner-swarm/devel"

if [ ! -f "${EGO_DEVEL}/setup.bash" ]; then
  echo "[ERROR] ego-planner-swarm devel not found: ${EGO_DEVEL}" >&2
  echo "        run git submodule update --init --recursive and build the EGO workspace first." >&2
  exit 1
fi

# RflySim's bundled Noetic references $ROS_DISTRO during setup; export it first.
export ROS_DISTRO=noetic
export ROS_MASTER_URI=http://localhost:11311
source /opt/ros/noetic/setup.bash

# Keep the ROS prefix and append our overlay so find_package(quadrotor_msgs)
# resolves to the planner workspace (same ordering as the live flight chain).
export CMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH:+${CMAKE_PREFIX_PATH}:}${EGO_DEVEL}"

cd "${WS_DIR}"
echo "[build] workspace: ${WS_DIR}"
catkin_make -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "$@"

# Merge per-package compile_commands.json files into one file that VS Code
# reads from: build/compile_commands.json
export WS_DIR
python3 - <<'PY'
import glob
import json
import os

ws = os.environ["WS_DIR"]
out = os.path.join(ws, "build", "compile_commands.json")
entries = []
for path in glob.glob(os.path.join(ws, "build", "*", "compile_commands.json")):
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries.extend(json.load(f))
    except (OSError, ValueError):
        continue
with open(out, "w", encoding="utf-8") as f:
    json.dump(entries, f, indent=2)
print(f"[build] merged {len(entries)} compile entries -> {out}")
PY
