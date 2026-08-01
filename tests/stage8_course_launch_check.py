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
        "base map: VisionRingBlank",
        "NED PosX: -0.7,0.7",
        "NED PosY: 0,0",
        "generate_predicted_narrow_course.bat",
        "start_two_uav.bat",
        "load_predicted_narrow_course.bat",
    ):
        assert expected in course.stdout, (expected, course.stdout)
    forbidden = ("RflySim3D.exe", "CopterSim.exe", "roslaunch", "--allow-arm")
    assert all(value not in course.stdout for value in forbidden), course.stdout

    env = dict(os.environ)
    env.update(
        {
            "RFLYSIM_UE4_MAP": "VisionRingBlank",
            "STAGE2_POS_X_STR": "-0.7,0.7",
            "STAGE2_POS_Y_STR": "0,0",
            "STAGE2_YAW_STR": "90,90",
        }
    )
    generated = run_batch(root, "scripts/start_rflysim_sitl_two.bat", "--generate-only", env=env)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    generated_path = Path(tempfile.gettempdir()) / "future_aircraft_stage2_uavsitl.bat"
    generated_text = generated_path.read_text(encoding="ascii", errors="replace")
    assert "SET UE4_MAP=VisionRingBlank" in generated_text
    assert "SET PosXStr=-0.7,0.7" in generated_text
    assert "SET PosYStr=0,0" in generated_text
    assert "SET YawStr=90,90" in generated_text

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
