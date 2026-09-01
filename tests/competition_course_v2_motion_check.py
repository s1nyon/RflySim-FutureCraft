#!/usr/bin/env python3
"""Deterministic pendulum controller checks without RflySim."""

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path


class FakeApi:
    def __init__(self):
        self.poses = []
        self.unscaled_poses = []

    def sendUE4PosScale(self, **kwargs):
        self.poses.append(kwargs)

    def sendUE4PosNew(self, **kwargs):
        self.unscaled_poses.append(kwargs)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", default="."); args = parser.parse_args()
    root = Path(args.project_root).resolve(); sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_geometry import build_entity_manifest, load_spec, pendulum_pose
    from competition_course_motion import run_samples
    spec = load_spec(root / "config/maps/competition_course_v2.json")
    dynamic = spec["dynamic_obstacle"]
    dynamic_entity = next(entity for entity in build_entity_manifest(spec) if entity["id"] == dynamic["id"])
    samples = [pendulum_pose(dynamic, value) for value in (0, 1.5, 3, 4.5, 6)]
    assert math.isclose(samples[0][1], samples[2][1], abs_tol=1e-9)
    assert samples[1][1] > samples[0][1] > samples[3][1]
    assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(samples[0], samples[4]))
    api = FakeApi()
    with tempfile.TemporaryDirectory() as temp:
        evidence = Path(temp) / "motion.json"
        result = run_samples(api, dynamic, dynamic_entity["scale"], [0, 1, 2], evidence, window_id=-1)
        assert len(api.poses) == 3
        assert api.unscaled_poses == []
        assert all(pose["Scale"] == dynamic_entity["scale"] for pose in api.poses)
        assert result["object_id"] == 15120
        recorded = json.loads(evidence.read_text(encoding="utf-8"))
        assert recorded["scale"] == dynamic_entity["scale"]
        assert [sample["elapsed_sec"] for sample in recorded["samples"]] == [0.0, 1.0, 2.0]
        assert recorded["configured_period_sec"] == 6.0
    print("competition_course_v2_motion_check: PASS")


if __name__ == "__main__": main()
