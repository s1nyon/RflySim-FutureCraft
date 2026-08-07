#!/usr/bin/env python3
"""Guard the ROS overlay order for quadrotor_msgs/PositionCommand consumers.

The ego-planner-swarm build and the 28com_uav build each ship their own
quadrotor_msgs package with a different PositionCommand message (the 28com
devel adds goal_pos).  The planner publisher runs from the ego-planner-swarm
devel workspace, so every project process that subscribes to
/uav*/planning/pos_cmd must source ego-planner-swarm's devel after 28com_uav
and before the project overlay.  Otherwise ROS drops the connection with
"datatype/md5sum ... Dropping connection" and the mission sees
planner_commands=0.

This check verifies the entry-point source order statically; the live md5
resolution is verified separately in WSL (see docs/d435i_sensor_parity...md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SH_28COM_SOURCE = 'source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"'
BAT_28COM_SOURCE = "source '%REF_28COM_UAV_WSL_DIR%/devel/setup.bash'"
SH_EGO_SOURCE = 'source "$EGO_SWARM_WSL_DIR/devel/setup.bash"'
BAT_EGO_SOURCE = "source '%EGO_SWARM_WSL_DIR%/devel/setup.bash'"
PROJECT_OVERLAY_MARKERS = ('future_aircraft_ws/devel/setup.bash', '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash')


def check_order(text: str, label: str, path: Path, errors: list[str]) -> None:
    is_bat = path.suffix == ".bat"
    source_28 = BAT_28COM_SOURCE if is_bat else SH_28COM_SOURCE
    source_ego = BAT_EGO_SOURCE if is_bat else SH_EGO_SOURCE
    has_28 = source_28 in text
    has_ego = source_ego in text
    project_markers = [marker for marker in PROJECT_OVERLAY_MARKERS if marker in text]
    if not has_28:
        errors.append(f"{label}: missing 28com_uav devel source")
        return
    if not has_ego:
        errors.append(f"{label}: missing ego-planner-swarm devel source")
        return
    if not project_markers:
        errors.append(f"{label}: missing project overlay marker")
        return
    idx_28 = text.index(source_28)
    idx_ego = text.index(source_ego)
    idx_project = min(text.index(marker) for marker in project_markers)
    if not (idx_28 < idx_ego < idx_project):
        errors.append(
            f"{label}: source order must be 28com_uav -> ego-planner-swarm -> project overlay "
            f"(indices 28com={idx_28}, ego={idx_ego}, project={idx_project})"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flight-runner", required=True, type=Path)
    parser.add_argument("--recorder-bat", required=True, type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    check_order(args.flight_runner.read_text(encoding="utf-8"), "flight runner", args.flight_runner, errors)
    check_order(args.recorder_bat.read_text(encoding="utf-8"), "stage8 recorder", args.recorder_bat, errors)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] quadrotor_msgs overlay source order is 28com_uav -> ego-planner-swarm -> project")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
