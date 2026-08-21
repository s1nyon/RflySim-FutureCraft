#!/usr/bin/env python3
"""Contract checks for the Stage 8 predicted narrow-course geometry."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import sys
import tempfile
from pathlib import Path


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("narrow_course_geometry", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from {}".format(module_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_invalid(module, source: dict, mutate, message_fragment: str) -> None:
    candidate = copy.deepcopy(source)
    mutate(candidate)
    with tempfile.TemporaryDirectory(prefix="stage8_geometry_invalid_") as temp_dir:
        path = Path(temp_dir) / "course.json"
        path.write_text(json.dumps(candidate, allow_nan=True), encoding="utf-8")
        try:
            module.load_course(path)
        except module.CourseValidationError as exc:
            assert message_fragment in str(exc), str(exc)
        else:
            raise AssertionError(
                "expected CourseValidationError containing {!r}".format(message_fragment)
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()

    module = load_module(args.module)
    model = module.load_course(args.spec)
    report = module.course_report(model)

    assert model.course_name == "predicted_narrow_course_v1"
    assert model.base_map == "SLAMScene"
    assert model.owned_id_range == (12000, 12999)
    assert math.isclose(report["centreline_length_m"], 14.927433, abs_tol=1e-6)
    assert report["minimum_clear_width_m"] == 1.4
    assert report["maximum_turn_radius_m"] == 0.9
    assert math.isclose(report["takeoff_separation_m"], 1.4, abs_tol=1e-9)
    assert math.isclose(report["platform_spacing_m"], 2.0, abs_tol=1e-9)
    assert report["object_count"] == len(model.scene_objects)
    assert report["object_count"] == 34
    assert len(model.wall_boxes) >= 10
    assert len(model.arena_objects) == 8
    arena_floor = next(obj for obj in model.arena_objects if obj.category == "arena_floor")
    # The floor collision slab is lowered below the CopterSim spawn plane
    # (z=0) so vehicles cannot spawn inside it (stuck-in-floor / lidar-occluded
    # failures observed with collision enabled).
    assert arena_floor.center == module.Vec3(23.9, 2.2, -0.10)
    assert arena_floor.size == module.Vec3(30.8, 19.4, 0.05)
    ceilings = [obj for obj in model.arena_objects if obj.category == "ceiling"]
    assert len(ceilings) == 3
    # UE4 renders sendUE4PosScale z ~0.43 m low; 2.93 compensates so the
    # ceiling top meets the 2.5 m boundary wall top in the rendered scene.
    assert all(ceiling.center.z == 2.93 for ceiling in ceilings)
    assert all(ceiling.size.z == 0.2 for ceiling in ceilings)
    assert [ceiling.copter_id for ceiling in ceilings] == [12785, 12786, 12787]
    boundary_walls = [obj for obj in model.arena_objects if obj.category == "boundary_wall"]
    assert len(boundary_walls) == 4
    assert all(obj.size.z == 2.5 for obj in boundary_walls)
    assert all(obj.center.z == 0.0 for obj in boundary_walls)
    assert [surface.copter_id for surface in model.zone_surfaces] == [12790, 12791]
    assert [platform.copter_id for platform in model.landing_platforms] == [12800, 12801]
    assert max(wall.copter_id for wall in model.wall_boxes) < 12790
    assert all(wall.size.z == 2.5 for wall in model.wall_boxes)
    assert all(wall.size.y == 0.15 for wall in model.wall_boxes)
    assert all(wall.center.z == 0.0 for wall in model.wall_boxes)
    assert all(surface.center.z == 0.0 for surface in model.zone_surfaces)
    assert all(platform.center.z == 0.0 for platform in model.landing_platforms)
    assert [pose.position for pose in model.takeoff_poses] == [
        module.Vec3(16.0, -0.7, 0.0),
        module.Vec3(16.0, 0.7, 0.0),
    ]
    assert model.raw["centreline"][0]["start"] == [18.5, 0.0]
    assert model.raw["centreline"][-1]["end"] == [29.3, 4.9]
    assert [platform.center.x for platform in model.landing_platforms] == [32.0, 32.0]
    assert model.raw["terrain"]["bounds"] == [-25.0, 55.0, -25.0, 25.0]
    assert model.raw["terrain"]["pixels"] == [801, 501]

    ned = module.enu_to_ned(module.Vec3(3.0, 4.0, 2.0))
    assert ned == module.Vec3(4.0, 3.0, -2.0)
    assert math.isclose(module.yaw_enu_to_ned(0.0), math.pi / 2.0)

    raw = json.loads(args.spec.read_text(encoding="utf-8"))
    expect_invalid(
        module,
        raw,
        lambda data: data["centreline"][0].__setitem__("width", 1.51),
        "clear width",
    )
    expect_invalid(
        module,
        raw,
        lambda data: data["centreline"][1].__setitem__("radius", 1.01),
        "turn radius",
    )
    expect_invalid(
        module,
        raw,
        lambda data: data["landing_platforms"][1].__setitem__(
            "center", [32.0, 5.4, 0.05]
        ),
        "platform spacing",
    )
    expect_invalid(
        module,
        raw,
        lambda data: data["landing_platforms"][1].__setitem__("id", 12800),
        "duplicate object ID",
    )
    expect_invalid(
        module,
        raw,
        lambda data: data["takeoff_poses"][0].__setitem__(
            "position", [float("nan"), -0.7, 0.0]
        ),
        "finite",
    )
    expect_invalid(
        module,
        raw,
        lambda data: data["takeoff_poses"][0].__setitem__(
            "position", [18.5, 0.75, 0.0]
        ),
        "takeoff clearance",
    )
    expect_invalid(
        module,
        raw,
        lambda data: data.__setitem__("schema_version", 2),
        "schema version",
    )

    print("stage8 course geometry: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
