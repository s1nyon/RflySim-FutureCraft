#!/usr/bin/env python3
"""Focused offline contract checks for Competition Course V2 geometry."""

import argparse
import copy
import json
import math
import sys
import tempfile
from pathlib import Path


def expect_error(func, needle):
    try:
        func()
    except Exception as exc:  # contract test intentionally checks public exception text
        assert needle in str(exc), (needle, str(exc))
    else:
        raise AssertionError("expected error containing {!r}".format(needle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    script_dir = root / "future_aircraft_ws/src/multi_uav_mission/scripts"
    sys.path.insert(0, str(script_dir))
    from competition_course_geometry import (  # pylint: disable=import-error
        CourseValidationError,
        build_entity_manifest,
        build_wall_boxes,
        load_spec,
        pendulum_pose,
        route_geometry_report,
        validate_spec,
    )

    spec_path = root / "config/maps/competition_course_v2.json"
    model = load_spec(spec_path)
    assert model["map_id"] == "competition_course_v2"
    assert model["coordinate_frame"] == "ENU"
    assert model["base_scene"] == "SLAMScene"
    assert model["object_id_range"] == [15000, 15999]
    assert model["box_asset"] == {"vehicle_type": 1000813, "native_size_m": [1.0, 1.0, 3.0]}
    assert len(model["course"]) == 5
    assert [item["kind"] for item in model["course"]] == ["line", "arc", "line", "arc", "line"]
    assert [item["width"] for item in model["course"]] == [1.5, 1.5, 1.4, 1.4, 1.5]
    assert all(item.get("radius", 0.9) <= 1.0 for item in model["course"])
    assert len(model["static_obstacles"]) == 2
    assert len(model["landing"]["platforms"]) == 2
    assert len(model["landing"]["markers"]) == 2
    assert model["landing"]["markers"][0]["dictionary"] == "DICT_4X4_250"
    assert model["mission_target_slot"]["asset"] == "placeholder"

    walls = build_wall_boxes(model)
    assert walls
    assert all(wall.category == "wall" for wall in walls)
    assert all(wall.size.x > 0 and wall.size.y > 0 and wall.size.z == 2.5 for wall in walls)
    entity_manifest = build_entity_manifest(model)
    ids = [item["id"] for item in entity_manifest]
    assert len(ids) == len(set(ids))
    assert all(15000 <= item <= 15999 for item in ids)
    assert {item["name"] for item in entity_manifest} >= {
        "static_box_a", "static_pillar_b", "moving_pendulum", "mission_target_slot",
        "landing_platform_uav1", "landing_platform_uav2", "aruco_uav1", "aruco_uav2"
    }
    first_wall = next(item for item in entity_manifest if item["id"] == 15000)
    assert first_wall["size"] == [4.5, 0.15, 2.5]
    assert first_wall["scale"] == [4.5, 0.15, 2.5 / 3.0]
    static_box = next(item for item in entity_manifest if item["id"] == 15100)
    assert static_box["size"] == [0.35, 0.25, 0.9]
    assert static_box["scale"] == [0.35, 0.25, 0.3]

    route = route_geometry_report(model)
    assert route["passes"]
    assert route["self_intersections"] == []
    assert route["minimum_clear_width_m"] == 1.4
    assert route["required_envelope_width_m"] == 0.95
    assert route["sampling_max_chord_error_m"] <= model["wall"]["max_chord_error"]
    crossed = copy.deepcopy(model)
    crossed["course"][-1]["end"] = [19.0, -1.0]
    assert route_geometry_report(crossed)["self_intersections"]
    narrow = copy.deepcopy(model)
    narrow["course"][2]["width"] = 0.9
    assert not route_geometry_report(narrow)["passes"]

    p0 = pendulum_pose(model["dynamic_obstacle"], 0.0)
    pq = pendulum_pose(model["dynamic_obstacle"], 1.5)
    ph = pendulum_pose(model["dynamic_obstacle"], 3.0)
    assert model["dynamic_obstacle"]["segment"] == "section_a"
    assert model["dynamic_obstacle"]["pivot"][:2] == [22.0, 0.0]
    assert math.isclose(p0[1], model["dynamic_obstacle"]["pivot"][1], abs_tol=1e-9)
    assert pq[1] > p0[1]
    assert math.isclose(ph[1], p0[1], abs_tol=1e-9)
    assert all(math.isfinite(value) for pose in (p0, pq, ph) for value in pose)

    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    cases = []
    bad = copy.deepcopy(raw); bad["schema_version"] = 3; cases.append((bad, "schema_version"))
    bad = copy.deepcopy(raw); bad["unexpected"] = True; cases.append((bad, "unknown root field"))
    bad = copy.deepcopy(raw); bad["course"][0]["width"] = 0; cases.append((bad, "width"))
    bad = copy.deepcopy(raw); bad["course"][1]["radius"] = 1.1; cases.append((bad, "radius"))
    bad = copy.deepcopy(raw); bad["static_obstacles"][1]["id"] = bad["static_obstacles"][0]["id"]; cases.append((bad, "duplicate object ID"))
    bad = copy.deepcopy(raw); bad["dynamic_obstacle"]["period_sec"] = 0; cases.append((bad, "period_sec"))
    bad = copy.deepcopy(raw); bad["landing"]["markers"][0]["physical_size_m"] = 0; cases.append((bad, "physical_size_m"))
    bad = copy.deepcopy(raw); bad["landing"]["markers"][0]["white_border_size_m"] = 0.5; cases.append((bad, "white_border_size_m"))
    bad = copy.deepcopy(raw); bad["spawns"]["uav2"] = bad["spawns"]["uav1"]; cases.append((bad, "spawn separation"))
    bad = copy.deepcopy(raw); bad["landing"]["platforms"][1]["center"] = bad["landing"]["platforms"][0]["center"]; cases.append((bad, "platform spacing"))
    bad = copy.deepcopy(raw); bad["mission_target_slot"]["asset"] = "invented_target"; cases.append((bad, "placeholder"))

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "bad.json"
        for data, message in cases:
            path.write_text(json.dumps(data), encoding="utf-8")
            expect_error(lambda path=path: load_spec(path), message)

    validate_spec(model)
    try:
        raise CourseValidationError("sentinel")
    except CourseValidationError:
        pass
    print("competition_course_v2_geometry_check: PASS")


if __name__ == "__main__":
    main()
