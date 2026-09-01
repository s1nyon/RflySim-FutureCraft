#!/usr/bin/env python3
"""Contract checks for the opt-in V2 Section A live entrypoint."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run(command, root):
    return subprocess.run(command, cwd=str(root), text=True, capture_output=True, check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    wrapper = root / "scripts/run_competition_course_v2_navigation.bat"
    runner = root / "scripts/wsl/competition_course_v2_navigation.sh"
    validator = root / "scripts/validate_competition_course_v2_navigation.ps1"
    assert wrapper.is_file(), "V2 navigation Windows wrapper is missing"
    assert runner.is_file(), "V2 navigation WSL runner is missing"
    assert validator.is_file(), "V2 navigation validator is missing"

    dry = run([
        "cmd", "/d", "/c", str(wrapper),
        "--dry-run", "--profile", "short_smoke",
        "--stack-id", "stack-dry-run", "--manifest", "C:\\dry\\stack_manifest.json",
    ], root)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    expected = [
        "profile=short_smoke",
        "validate explicit stack manifest and simulation instance identity",
        "validate current run-scoped no-arm sensor readiness",
        "run no-arm EGO control-chain smoke",
        "start UAV1-only setpoint bridge and geofence watchdog",
        "start read-only V2 recorder and RflySim crash recorder",
        "generate the plan from competition_course_v2.json",
        "execute UAV1 mission with explicit simulation arm gates",
        "build provenance-labelled Section A report",
        "no process, OFFBOARD request, or arm request is executed",
    ]
    offsets = [dry.stdout.index(text) for text in expected]
    assert offsets == sorted(offsets), dry.stdout

    missing_arm = run([
        "cmd", "/d", "/c", str(wrapper),
        "--profile", "short_smoke", "--stack-id", "stack-test",
        "--manifest", "C:\\does-not-matter\\stack_manifest.json",
    ], root)
    assert missing_arm.returncode != 0
    assert "--allow-arm --simulation-only" in (missing_arm.stdout + missing_arm.stderr)
    assert "wsl" not in (missing_arm.stdout + missing_arm.stderr).lower()

    data = runner.read_bytes()
    assert b"\r\n" not in data, "WSL runner must remain LF-only"
    source = data.decode("utf-8")
    for forbidden in (
        "pkill", "killall", "taskkill", "wsl --shutdown", "reset --hard",
        "MAV_CMD_COMPONENT_ARM_DISARM", "min_uav_distance", "pendulum_pose",
        "/uav2/planning", "/uav2/mavros/setpoint_raw/local",
    ):
        assert forbidden not in source, forbidden
    for required in (
        "competition_course_navigation_plan.py",
        "competition_course_navigation_recorder.py",
        "competition_course_navigation_report.py",
        "flight_event_recorder.py",
        "--crash-listen",
        "--crash-status",
        "stage7_sensor_readiness.py",
        "ego_swarm_flight_smoke_check.py",
        "ego_swarm_setpoint_bridge.py",
        "course_geofence_watchdog.py",
        "mission_executor.py",
        "stack_register.py",
        "simulation_instance_id",
        "spec_sha256",
        "safe_land_uav1",
        "--wait-for-matching-planner-goal",
        "--expected-goal-frame",
        '"wsl:v2_mission_executor"',
        'wait "$EXECUTOR_PID"',
    ):
        assert required in source, required
    executor_start = source.index('setsid python3 "$SCRIPTS/mission_executor.py"')
    executor_register = source.index('"wsl:v2_mission_executor"', executor_start)
    executor_wait = source.index('wait "$EXECUTOR_PID"', executor_register)
    assert executor_start < executor_register < executor_wait
    executor_remove = source.index('remove_owned_child "$EXECUTOR_PID"', executor_wait)
    assert executor_wait < executor_remove
    print("competition_course_v2_navigation_entrypoint_check: PASS")


if __name__ == "__main__":
    main()
