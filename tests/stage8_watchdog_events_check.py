#!/usr/bin/env python3
"""Watchdog decisions must be structured with an explicit reason for every land trigger."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--watchdog", required=True, type=Path)
    args = parser.parse_args()
    module = load_module(args.module, "course_geofence")
    watchdog = load_module(args.watchdog, "course_geofence_watchdog")
    fence = module.Geofence(
        min_x=-1.0, max_x=17.0, min_y=-2.0, max_y=7.0, min_z=0.0, max_z=2.0,
        max_speed_mps=2.0, max_odom_age_s=0.5,
    )

    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2
    )
    assert (decision, reason) == ("continue", "ok")
    assert module.watchdog_decision(
        (5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2
    ) == "continue", "legacy watchdog_decision must remain a plain decision string"

    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 0.0, 5.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2
    )
    assert (decision, reason) == ("land", "outside_z")
    decision, reason = module.watchdog_decision_with_reason(
        (-5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2
    )
    assert (decision, reason) == ("land", "outside_x")
    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 10.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2
    )
    assert (decision, reason) == ("land", "outside_y")
    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 0.0, 1.0), fence, armed=True, mode="ALTCTL", odom_age_s=0.1, speed_mps=0.2
    )
    assert (decision, reason) == ("land", "mode_loss")
    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=1.1, speed_mps=0.2
    )
    assert (decision, reason) == ("land", "stale_odom")
    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=4.0
    )
    assert (decision, reason) == ("land", "max_speed")
    decision, reason = module.watchdog_decision_with_reason(
        (5.0, 0.0, 1.0), fence, armed=False, mode="ALTCTL", odom_age_s=2.0, speed_mps=9.0
    )
    assert (decision, reason) == ("continue", "disarmed")

    event = watchdog.decision_event(
        position=(5.0, 0.0, 5.0),
        speed_mps=0.2,
        odom_age_s=0.1,
        armed=True,
        mode="OFFBOARD",
        mode_grace_active=False,
        decision="land",
        reason="outside_z",
        timestamp=123.0,
    )
    for field in (
        "timestamp",
        "position",
        "speed_mps",
        "odom_age_s",
        "armed",
        "mode",
        "mode_grace_active",
        "decision",
        "reason",
    ):
        assert field in event, f"decision event missing field: {field}"
    assert event["decision"] == "land"
    assert event["reason"] == "outside_z"
    assert tuple(event["position"]) == (5.0, 0.0, 5.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
