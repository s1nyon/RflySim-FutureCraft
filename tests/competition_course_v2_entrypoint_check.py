#!/usr/bin/env python3
"""Static contracts for opt-in map selection and full-sensor diagnostics."""

import argparse
import json
import subprocess
import sys
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
    for expected in ("!MOTION!", "!SPEC!", "!MOTION_EVIDENCE!", "!MOTION_STOP!", "--pid-file", "Get-Process -Id"):
        assert expected in v2, "motion controller startup must preserve delayed values and prove child alive: {}".format(expected)
    assert "predicted_narrow_course" not in v2.lower()
    env_template = (root / "config/env_template.bat").read_text(encoding="utf-8")
    assert "COMPETITION_COURSE_V2_POS_X_STR" not in env_template
    assert "COMPETITION_COURSE_V2_POS_Y_STR" not in env_template
    assert "COMPETITION_COURSE_V2_YAW_STR" not in env_template
    assert "competition_course_spawn_args.py" in v2
    predicted_entry = (root / "scripts/start_predicted_course_two_uav.bat").read_text(encoding="utf-8")
    transition_entry = root / "scripts/transition_project_course_layer.bat"
    assert transition_entry.is_file()
    transition_text = transition_entry.read_text(encoding="utf-8")
    assert "course_layer_transition.py" in transition_text
    assert "--selected" in transition_text and "--receipt" in transition_text
    assert 'transition_project_course_layer.bat" competition_course_v2' in v2
    assert 'transition_project_course_layer.bat" predicted_narrow_course' in predicted_entry
    assert 'load_predicted_narrow_course.bat" --dry-run --no-clear' in predicted_entry
    assert 'load_predicted_narrow_course.bat" --no-clear' in predicted_entry
    assert "range(" not in transition_text
    spec = json.loads((root / "config/maps/competition_course_v2.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_spawn_args import spawn_environment
    assert spawn_environment(spec) == {
        "STAGE2_POS_X_STR": "-0.7,0.7",
        "STAGE2_POS_Y_STR": "16,16",
        "STAGE2_YAW_STR": "90,90",
    }
    output = subprocess.check_output([
        sys.executable,
        str(root / "future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_spawn_args.py"),
        "--spec", str(root / "config/maps/competition_course_v2.json"),
    ], text=True).splitlines()
    assert output == [
        "set STAGE2_POS_X_STR=-0.7,0.7",
        "set STAGE2_POS_Y_STR=16,16",
        "set STAGE2_YAW_STR=90,90",
    ]
    dry_run = subprocess.run(
        ["cmd", "/c", str(root / "scripts/start_competition_course_v2_two_uav.bat"), "--dry-run"],
        cwd=str(root), capture_output=True, text=True, check=False,
    )
    assert dry_run.returncode == 0, dry_run.stdout + dry_run.stderr
    assert "[DRY-RUN] NED PosX: -0.7,0.7" in dry_run.stdout
    assert "[DRY-RUN] NED PosY: 16,16" in dry_run.stdout
    assert "The system cannot find the path specified" not in dry_run.stderr
    predicted_dry_run = subprocess.run(
        ["cmd", "/c", str(root / "scripts/start_predicted_course_two_uav.bat"), "--dry-run"],
        cwd=str(root), capture_output=True, text=True, check=False,
    )
    assert predicted_dry_run.returncode == 0, predicted_dry_run.stdout + predicted_dry_run.stderr
    assert '"cleanup_policy": "exact_declared_ids"' in predicted_dry_run.stdout
    assert "[ERROR]" not in predicted_dry_run.stdout
    assert "[ERROR]" not in predicted_dry_run.stderr
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
    changed = subprocess.check_output(["git", "diff", "f23de934205b6776ef0531d46c26444bf9f7f65e", "--name-only"], cwd=str(root), text=True).splitlines()
    assert not set(protected) & set(changed)
    print("competition_course_v2_entrypoint_check: PASS")


if __name__ == "__main__": main()
