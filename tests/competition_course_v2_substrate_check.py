#!/usr/bin/env python3
"""Contract for reusing the accepted predicted-course spatial substrate."""

import argparse
import json
from pathlib import Path


def by_name(items):
    return {item["name"]: item for item in items}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    predicted = json.loads((root / "config/maps/predicted_narrow_course_v1.json").read_text(encoding="utf-8"))
    v2 = json.loads((root / "config/maps/competition_course_v2.json").read_text(encoding="utf-8"))

    assert v2["takeoff_area"]["bounds"] == predicted["takeoff_zone"]["bounds"]
    assert v2["spawns"] == {"uav1": [16.0, -0.7, 0.0], "uav2": [16.0, 0.7, 0.0]}
    assert v2["spawn_yaw_deg"] == {"uav1": 0.0, "uav2": 0.0}
    assert v2["course"][0]["start"] == [18.5, 0.0]
    assert v2["course"][-1]["end"] == [29.3, 4.9]
    assert v2["landing"]["bounds"] == [29.3, 34.3, 2.9, 6.9]
    assert min(point[0] for point in v2["spawns"].values()) >= 13.5

    predicted_arena = by_name(predicted["arena_objects"])
    v2_arena = by_name(v2["arena_objects"])
    assert set(v2_arena) == set(predicted_arena)
    for name, expected in predicted_arena.items():
        assert v2_arena[name]["category"] == expected["category"]
        assert v2_arena[name]["center"] == expected["center"]
        assert v2_arena[name]["size"] == expected["size"]
        assert v2_arena[name]["id"] != expected["id"]

    predicted_surfaces = by_name(predicted["zone_surfaces"])
    v2_surfaces = by_name(v2["zone_surfaces"])
    assert set(v2_surfaces) == set(predicted_surfaces)
    for name, expected in predicted_surfaces.items():
        assert v2_surfaces[name]["center"] == expected["center"]
        assert v2_surfaces[name]["size"] == expected["size"]
        assert v2_surfaces[name]["id"] != expected["id"]

    policy = v2["clearance_policy"]
    assert policy == {
        "vehicle_diameter_m": 0.45,
        "lateral_margin_each_side_m": 0.25,
        "minimum_passable_gap_m": 1.0,
        "minimum_dynamic_safe_window_sec": 1.5,
        "sampling_hz": 120.0,
    }
    print("competition_course_v2_substrate_check: PASS")


if __name__ == "__main__":
    main()
