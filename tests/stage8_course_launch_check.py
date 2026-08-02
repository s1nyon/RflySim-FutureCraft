#!/usr/bin/env python3
"""Behavioral checks for Stage 8 Windows launch integration."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def run_batch(project_root: Path, relative_path: str, *arguments: str, env=None):
    return subprocess.run(
        ["cmd", "/c", str(project_root / relative_path), *arguments],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()

    course = run_batch(root, "scripts/start_predicted_course_two_uav.bat", "--dry-run")
    assert course.returncode == 0, course.stdout + course.stderr
    for expected in (
        "base map: SLAMScene",
        "NED PosX: -0.7,0.7",
        "NED PosY: 16,16",
        "generate_predicted_narrow_course.bat",
        "deploy_predicted_course_terrain.bat",
        "start_two_uav.bat",
        "wait 10 seconds before scene load",
        "load_predicted_narrow_course.bat",
    ):
        assert expected in course.stdout, (expected, course.stdout)
    ordered_steps = [
        "generate_predicted_narrow_course.bat",
        "deploy_predicted_course_terrain.bat",
        "start_two_uav.bat",
        "wait 10 seconds before scene load",
        "load_predicted_narrow_course.bat",
    ]
    positions = [course.stdout.index(step) for step in ordered_steps]
    assert positions == sorted(positions), (ordered_steps, positions, course.stdout)
    forbidden = ("RflySim3D.exe", "CopterSim.exe", "roslaunch", "--allow-arm")
    assert all(value not in course.stdout for value in forbidden), course.stdout

    env = dict(os.environ)
    env.update(
        {
            "RFLYSIM_UE4_MAP": "SLAMScene",
            "STAGE2_POS_X_STR": "-0.7,0.7",
            "STAGE2_POS_Y_STR": "16,16",
            "STAGE2_YAW_STR": "90,90",
        }
    )
    generated = run_batch(root, "scripts/start_rflysim_sitl_two.bat", "--generate-only", env=env)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    generated_path = Path(tempfile.gettempdir()) / "future_aircraft_stage2_uavsitl.bat"
    generated_text = generated_path.read_text(encoding="ascii", errors="replace")
    assert "SET UE4_MAP=SLAMScene" in generated_text
    assert "SET PosXStr=-0.7,0.7" in generated_text
    assert "SET PosYStr=16,16" in generated_text
    assert "SET YawStr=90,90" in generated_text

    with tempfile.TemporaryDirectory(prefix="stage8_terrain_deploy_") as temp_dir:
        temp_root = Path(temp_dir)
        generated_dir = temp_root / "generated"
        map_dir = temp_root / "map"
        backup_dir = temp_root / "backup"
        generated_dir.mkdir()
        map_dir.mkdir()
        (generated_dir / "SLAMScene.png").write_bytes(b"flat-png-v1")
        (generated_dir / "SLAMScene.txt").write_bytes(b"flat-txt-v1")
        (map_dir / "SLAMScene.png").write_bytes(b"official-png")
        (map_dir / "SLAMScene.txt").write_bytes(b"official-txt")
        terrain_env = dict(os.environ)
        terrain_env.update(
            {
                "PREDICTED_COURSE_BASE_MAP": "SLAMScene",
                "PREDICTED_COURSE_OUTPUT": str(generated_dir),
                "PREDICTED_COURSE_TERRAIN_BACKUP_DIR": str(backup_dir),
                "RFLYSIM_COPTERSIM_MAP_DIR": str(map_dir),
            }
        )

        deploy = run_batch(
            root, "scripts/deploy_predicted_course_terrain.bat", env=terrain_env
        )
        assert deploy.returncode == 0, deploy.stdout + deploy.stderr
        assert (map_dir / "SLAMScene.png").read_bytes() == b"flat-png-v1"
        assert (map_dir / "SLAMScene.txt").read_bytes() == b"flat-txt-v1"
        assert (backup_dir / "SLAMScene.png").read_bytes() == b"official-png"
        assert (backup_dir / "SLAMScene.txt").read_bytes() == b"official-txt"

        (generated_dir / "SLAMScene.png").write_bytes(b"flat-png-v2")
        redeploy = run_batch(
            root, "scripts/deploy_predicted_course_terrain.bat", env=terrain_env
        )
        assert redeploy.returncode == 0, redeploy.stdout + redeploy.stderr
        assert (map_dir / "SLAMScene.png").read_bytes() == b"flat-png-v2"
        assert (backup_dir / "SLAMScene.png").read_bytes() == b"official-png"

        restore = run_batch(
            root,
            "scripts/deploy_predicted_course_terrain.bat",
            "--restore",
            env=terrain_env,
        )
        assert restore.returncode == 0, restore.stdout + restore.stderr
        assert (map_dir / "SLAMScene.png").read_bytes() == b"official-png"
        assert (map_dir / "SLAMScene.txt").read_bytes() == b"official-txt"

    reference = Path(
        os.environ.get(
            "RFLYSIM_UAV_SITL_SCRIPT",
            r"D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\28com_sim\28com_SITL\UAVSITL.bat",
        )
    )
    reference_text = reference.read_text(encoding="ascii", errors="replace")
    assert "SET UE4_MAP=ChallengeMap" in reference_text
    assert "SET PosXStr=-0.1" in reference_text
    assert "SET PosYStr=-0.8" in reference_text

    print("stage8 course launch: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
