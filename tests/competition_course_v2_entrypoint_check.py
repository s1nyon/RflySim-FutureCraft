#!/usr/bin/env python3
"""Static contracts for opt-in map selection and full-sensor diagnostics."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", default="."); args = parser.parse_args(); root = Path(args.project_root).resolve()
    lifecycle = (root / "scripts/live_stack_start.ps1").read_text(encoding="utf-8")
    assert "[ValidateSet('predicted_narrow_course', 'competition_course_v2')]" in lifecycle
    assert "[string]$Course = 'predicted_narrow_course'" in lifecycle
    assert "start_predicted_course_two_uav.bat" in lifecycle
    assert "start_competition_course_v2_two_uav.bat" in lifecycle
    assert "$Course" in lifecycle and '"COURSE=$Course"' in lifecycle
    v2 = (root / "scripts/start_competition_course_v2_two_uav.bat").read_text(encoding="utf-8")
    for expected in ("generate_competition_course_v2.bat", "deploy_competition_course_v2_terrain.bat", "load_competition_course_v2.bat", "register_launcher.py", "windows:competition_course_v2_motion", "COURSE_READY"):
        assert expected in v2
    assert "predicted_narrow_course" not in v2.lower()
    batch = (root / "scripts/run_live_fastlio_dual.bat").read_text(encoding="utf-8")
    shell = (root / "scripts/wsl/stage7_live_fastlio_dual.sh").read_text(encoding="utf-8")
    assert "SENSOR_MODE=lidar_only" in batch
    assert "--sensor-mode" in batch
    assert 'SENSOR_MODE="${STAGE7_SENSOR_MODE:-lidar_only}"' in shell
    assert shell.count('--sensor-mode "$SENSOR_MODE"') == 2
    assert "lidar_only|full" in shell
    protected = [
        "future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch",
        "future_aircraft_ws/src/multi_uav_mission/launch/rflysim_mavros_px4.launch",
        "future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch",
        "future_aircraft_ws/src/multi_uav_mission/scripts/odom_frame_relay.py",
        "future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py",
    ]
    import subprocess
    changed = subprocess.check_output(["git", "diff", "f23de934205b6776ef0531d46c26444bf9f7f65e", "--name-only"], cwd=str(root), text=True).splitlines()
    assert not set(protected) & set(changed)
    print("competition_course_v2_entrypoint_check: PASS")


if __name__ == "__main__": main()
