#!/usr/bin/env python3
"""Pure, deterministic geometry contract for Competition Course V2."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


class CourseValidationError(ValueError):
    """The versioned course source violates its fail-closed contract."""


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class BoxObject:
    name: str
    object_id: int
    category: str
    center: Vec3
    size: Vec3
    yaw_rad: float
    vehicle_type: int
    collision: bool


ROOT_FIELDS = {
    "schema_version", "map_id", "coordinate_frame", "units", "base_scene",
    "object_id_range", "requirements", "wall", "vehicle_envelope",
    "takeoff_area", "spawns", "course", "static_obstacles",
    "dynamic_obstacle", "mission_target_slot", "landing", "terrain",
    "spec_sha256",
}


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CourseValidationError("{} must be a finite number".format(label))
    value = float(value)
    if not math.isfinite(value):
        raise CourseValidationError("{} must be finite".format(label))
    return value


def _vec(values: Sequence[Any], count: int, label: str) -> Tuple[float, ...]:
    if not isinstance(values, list) or len(values) != count:
        raise CourseValidationError("{} must contain {} values".format(label, count))
    return tuple(_number(value, label) for value in values)


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _inside(point: Sequence[float], bounds: Sequence[float]) -> bool:
    return bounds[0] <= point[0] <= bounds[1] and bounds[2] <= point[1] <= bounds[3]


def _positive_angle(value: float) -> float:
    while value < 0:
        value += 2 * math.pi
    while value >= 2 * math.pi:
        value -= 2 * math.pi
    return value


def _arc_angles(item: Dict[str, Any]) -> Tuple[float, float]:
    start = _vec(item["start"], 2, "arc start")
    end = _vec(item["end"], 2, "arc end")
    center = _vec(item["center"], 2, "arc center")
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if item["turn"] == "left":
        sweep = _positive_angle(a1 - a0)
    elif item["turn"] == "right":
        sweep = -_positive_angle(a0 - a1)
    else:
        raise CourseValidationError("arc turn must be left or right")
    if not 0 < abs(sweep) <= math.pi:
        raise CourseValidationError("arc sweep must be in (0, pi]")
    return a0, sweep


def validate_spec(spec: Dict[str, Any]) -> None:
    unknown = sorted(set(spec) - ROOT_FIELDS)
    if unknown:
        raise CourseValidationError("unknown root field: {}".format(unknown[0]))
    if spec.get("schema_version") != 2:
        raise CourseValidationError("schema_version must be 2")
    if spec.get("map_id") != "competition_course_v2":
        raise CourseValidationError("map_id must be competition_course_v2")
    if spec.get("coordinate_frame") != "ENU" or spec.get("units") != "m":
        raise CourseValidationError("coordinate contract must be ENU metres")
    if spec.get("base_scene") != "SLAMScene":
        raise CourseValidationError("base_scene must be SLAMScene")
    id_range = spec.get("object_id_range")
    if not isinstance(id_range, list) or len(id_range) != 2 or not all(isinstance(x, int) for x in id_range):
        raise CourseValidationError("object_id_range must contain two integers")
    if id_range != [15000, 15999]:
        raise CourseValidationError("object_id_range must be [15000, 15999]")

    wall = spec["wall"]
    for key in ("height", "thickness", "max_chord_error"):
        if _number(wall[key], "wall {}".format(key)) <= 0:
            raise CourseValidationError("wall {} must be positive".format(key))
    course = spec.get("course")
    if not isinstance(course, list) or [x.get("kind") for x in course] != ["line", "arc", "line", "arc", "line"]:
        raise CourseValidationError("course must contain line/arc/line/arc/line")
    prior_end = None
    for item in course:
        start, end = _vec(item["start"], 2, "course start"), _vec(item["end"], 2, "course end")
        width = _number(item["width"], "corridor width")
        if width <= 0 or width > 1.5:
            raise CourseValidationError("corridor width must be in (0, 1.5]")
        if prior_end is not None and _distance(prior_end, start) > 1e-6:
            raise CourseValidationError("course elements must be contiguous")
        if item["kind"] == "line" and _distance(start, end) <= 0:
            raise CourseValidationError("line length must be positive")
        if item["kind"] == "arc":
            radius = _number(item["radius"], "turn radius")
            if radius <= 0 or radius > 1.0:
                raise CourseValidationError("turn radius must be in (0, 1.0]")
            center = _vec(item["center"], 2, "arc center")
            if abs(_distance(center, start) - radius) > 1e-6 or abs(_distance(center, end) - radius) > 1e-6:
                raise CourseValidationError("arc endpoints must lie on radius")
            _arc_angles(item)
        prior_end = end

    takeoff = _vec(spec["takeoff_area"]["bounds"], 4, "takeoff bounds")
    spawns = spec.get("spawns", {})
    if set(spawns) != {"uav1", "uav2"}:
        raise CourseValidationError("spawns must contain uav1 and uav2")
    positions = [_vec(spawns[key], 3, "{} spawn".format(key)) for key in ("uav1", "uav2")]
    if not all(_inside(pos, takeoff) for pos in positions):
        raise CourseValidationError("spawn must be inside takeoff area")
    required_sep = _number(spec["vehicle_envelope"]["horizontal_diameter"], "vehicle diameter")
    if _distance(positions[0], positions[1]) <= required_sep:
        raise CourseValidationError("spawn separation must exceed vehicle diameter")

    explicit = list(spec["static_obstacles"]) + [spec["dynamic_obstacle"], spec["mission_target_slot"]]
    explicit += list(spec["landing"]["platforms"]) + list(spec["landing"]["markers"])
    ids = []
    for item in explicit:
        object_id = item.get("id")
        if not isinstance(object_id, int) or not id_range[0] <= object_id <= id_range[1]:
            raise CourseValidationError("object ID must be in owned range")
        ids.append(object_id)
    if len(ids) != len(set(ids)):
        raise CourseValidationError("duplicate object ID")

    for obstacle in spec["static_obstacles"]:
        size = _vec(obstacle["size"], 3, "static obstacle size")
        if any(value <= 0 for value in size):
            raise CourseValidationError("static obstacle size must be positive")
        if not obstacle.get("collision"):
            raise CourseValidationError("static obstacle collision must be true")
        # A horizontal obstacle extent equal to the minimum corridor width would seal it.
        if min(size[0], size[1]) >= min(item["width"] for item in course):
            raise CourseValidationError("static obstacle completely blocks corridor")

    dynamic = spec["dynamic_obstacle"]
    if dynamic.get("type") != "pendulum":
        raise CourseValidationError("dynamic obstacle type must be pendulum")
    for key in ("length_m", "period_sec", "update_hz"):
        if _number(dynamic[key], key) <= 0:
            raise CourseValidationError("{} must be positive".format(key))
    amplitude = _number(dynamic["amplitude_deg"], "amplitude_deg")
    if not 0 < amplitude < 90:
        raise CourseValidationError("amplitude_deg must be in (0, 90)")
    _vec(dynamic["pivot"], 3, "pendulum pivot")

    target = spec["mission_target_slot"]
    if target.get("asset") != "placeholder" or target.get("replaceable") is not True:
        raise CourseValidationError("mission target must remain a replaceable placeholder")

    landing = spec["landing"]
    bounds = _vec(landing["bounds"], 4, "landing bounds")
    platforms = landing["platforms"]
    if len(platforms) != 2:
        raise CourseValidationError("landing must have two platforms")
    centers = [_vec(item["center"], 3, "platform center") for item in platforms]
    if not all(_inside(center, bounds) for center in centers):
        raise CourseValidationError("platform must be inside landing bounds")
    min_spacing = float(spec["requirements"]["minimum_landing_spacing_m"]["value"])
    if _distance(centers[0], centers[1]) < min_spacing:
        raise CourseValidationError("platform spacing is below official minimum")
    markers = landing["markers"]
    if len(markers) != 2 or len({item["marker_id"] for item in markers}) != 2:
        raise CourseValidationError("two distinct ArUco markers are required")
    for marker in markers:
        if marker.get("dictionary") != "DICT_4X4_250" or not 0 <= int(marker["marker_id"]) < 250:
            raise CourseValidationError("marker must use a valid DICT_4X4_250 ID")
        if _number(marker["physical_size_m"], "physical_size_m") <= 0:
            raise CourseValidationError("physical_size_m must be positive")
        if _number(marker["white_border_size_m"], "white_border_size_m") < marker["physical_size_m"]:
            raise CourseValidationError("white_border_size_m must not be smaller than the marker")


def load_spec(path: Path) -> Dict[str, Any]:
    path = Path(path)
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CourseValidationError("invalid course JSON: {}".format(exc)) from exc
    if not isinstance(spec, dict):
        raise CourseValidationError("course JSON root must be an object")
    validate_spec(spec)
    spec["spec_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return spec


def _wall(name: str, object_id: int, center: Tuple[float, float], size: Tuple[float, float], yaw: float, spec: Dict[str, Any]) -> BoxObject:
    wall = spec["wall"]
    return BoxObject(name, object_id, "wall", Vec3(center[0], center[1], 0.0), Vec3(size[0], size[1], wall["height"]), yaw, int(wall["vehicle_type"]), True)


def build_wall_boxes(spec: Dict[str, Any]) -> List[BoxObject]:
    validate_spec(spec)
    wall, result, object_id = spec["wall"], [], spec["object_id_range"][0]
    for element in spec["course"]:
        width = float(element["width"])
        if element["kind"] == "line":
            start, end = element["start"], element["end"]
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy); ux, uy = dx / length, dy / length
            nx, ny = -uy, ux; offset = width / 2 + wall["thickness"] / 2
            center = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            for side, sign in (("left", 1), ("right", -1)):
                result.append(_wall("{}_{}".format(element["name"], side), object_id, (center[0] + sign * nx * offset, center[1] + sign * ny * offset), (length, wall["thickness"]), math.atan2(uy, ux), spec)); object_id += 1
        else:
            center, radius = element["center"], float(element["radius"])
            start_angle, sweep = _arc_angles(element)
            max_delta = 2 * math.acos(max(-1.0, 1.0 - wall["max_chord_error"] / radius))
            count = max(1, int(math.ceil(abs(sweep) / max_delta)))
            for index in range(count):
                a0, a1 = start_angle + sweep * index / count, start_angle + sweep * (index + 1) / count
                for label, arc_radius in (("inner", radius - width / 2 - wall["thickness"] / 2), ("outer", radius + width / 2 + wall["thickness"] / 2)):
                    if arc_radius <= 0:
                        raise CourseValidationError("wall thickness leaves no inner radius")
                    p0 = (center[0] + arc_radius * math.cos(a0), center[1] + arc_radius * math.sin(a0)); p1 = (center[0] + arc_radius * math.cos(a1), center[1] + arc_radius * math.sin(a1))
                    result.append(_wall("{}_{}_{}".format(element["name"], index, label), object_id, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), (_distance(p0, p1), wall["thickness"]), math.atan2(p1[1] - p0[1], p1[0] - p0[0]), spec)); object_id += 1
    return result


def _entity(item: Dict[str, Any], category: str) -> Dict[str, Any]:
    return {"name": item["name"], "id": item["id"], "category": category, "center": item.get("center", item.get("pivot")), "size": item.get("size"), "vehicle_type": item.get("vehicle_type", item.get("class_id")), "collision": bool(item.get("collision", False))}


def build_entity_manifest(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    walls = [{"name": item.name, "id": item.object_id, "category": item.category, "center": list(asdict(item.center).values()), "size": list(asdict(item.size).values()), "yaw_rad": item.yaw_rad, "vehicle_type": item.vehicle_type, "collision": item.collision} for item in build_wall_boxes(spec)]
    entities = walls + [_entity(item, "static_obstacle") for item in spec["static_obstacles"]]
    entities += [_entity(spec["dynamic_obstacle"], "dynamic_obstacle"), _entity(spec["mission_target_slot"], "mission_target_slot")]
    entities += [_entity(item, "landing_platform") for item in spec["landing"]["platforms"]]
    entities += [_entity(item, "aruco") for item in spec["landing"]["markers"]]
    ids = [item["id"] for item in entities]
    if len(ids) != len(set(ids)):
        raise CourseValidationError("duplicate object ID including generated walls")
    return sorted(entities, key=lambda item: item["id"])


def pendulum_pose(dynamic_spec: Dict[str, Any], elapsed_sec: float) -> Tuple[float, float, float]:
    elapsed = _number(elapsed_sec, "elapsed_sec")
    pivot = _vec(dynamic_spec["pivot"], 3, "pendulum pivot")
    angle = math.radians(float(dynamic_spec["amplitude_deg"])) * math.sin(2 * math.pi * elapsed / float(dynamic_spec["period_sec"]) + float(dynamic_spec["phase_rad"]))
    return (pivot[0], pivot[1] + float(dynamic_spec["length_m"]) * math.sin(angle), pivot[2] - float(dynamic_spec["length_m"]) * math.cos(angle))
