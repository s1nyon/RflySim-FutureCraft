#!/usr/bin/env python3
"""Pure geometry and validation for the predicted narrow-course map."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple


TOLERANCE = 1e-6
WALL_ID_START = 12000
ZONE_ID_START = 12790


class CourseValidationError(ValueError):
    """Raised when a course specification violates its public contract."""


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y, self.z))


@dataclass(frozen=True)
class Pose:
    name: str
    position: Vec3
    yaw_rad: float


@dataclass(frozen=True)
class BoxObject:
    name: str
    copter_id: int
    category: str
    center: Vec3
    size: Vec3
    yaw_rad: float = 0.0


@dataclass(frozen=True)
class CourseModel:
    course_name: str
    base_map: str
    owned_id_range: Tuple[int, int]
    spec_sha256: str
    raw: Dict[str, Any]
    takeoff_poses: Tuple[Pose, ...]
    wall_boxes: Tuple[BoxObject, ...]
    arena_objects: Tuple[BoxObject, ...]
    zone_surfaces: Tuple[BoxObject, ...]
    landing_platforms: Tuple[BoxObject, ...]

    @property
    def scene_objects(self) -> Tuple[BoxObject, ...]:
        return self.wall_boxes + self.arena_objects + self.zone_surfaces + self.landing_platforms


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CourseValidationError("{} must be a finite number".format(label))
    result = float(value)
    if not math.isfinite(result):
        raise CourseValidationError("{} must be finite".format(label))
    return result


def _vec3(values: Sequence[Any], label: str) -> Vec3:
    if not isinstance(values, list) or len(values) != 3:
        raise CourseValidationError("{} must contain three finite values".format(label))
    return Vec3(*(_finite_number(value, label) for value in values))


def _vec2(values: Sequence[Any], label: str) -> Tuple[float, float]:
    if not isinstance(values, list) or len(values) != 2:
        raise CourseValidationError("{} must contain two finite values".format(label))
    return (_finite_number(values[0], label), _finite_number(values[1], label))


def _distance2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _positive_angle(value: float) -> float:
    while value < 0.0:
        value += 2.0 * math.pi
    while value >= 2.0 * math.pi:
        value -= 2.0 * math.pi
    return value


def _arc_sweep(element: Dict[str, Any]) -> Tuple[float, float]:
    start = _vec2(element["start"], "arc start")
    end = _vec2(element["end"], "arc end")
    center = _vec2(element["center"], "arc center")
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    turn = element.get("turn")
    if turn == "left":
        sweep = _positive_angle(end_angle - start_angle)
    elif turn == "right":
        sweep = -_positive_angle(start_angle - end_angle)
    else:
        raise CourseValidationError("arc turn must be left or right")
    if abs(sweep) <= TOLERANCE or abs(sweep) > math.pi + TOLERANCE:
        raise CourseValidationError("arc sweep must be between zero and pi")
    return start_angle, sweep


def _line_wall_boxes(
    element: Dict[str, Any], wall: Dict[str, float], next_id: int
) -> Tuple[List[BoxObject], int]:
    start = _vec2(element["start"], "line start")
    end = _vec2(element["end"], "line end")
    width = float(element["width"])
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= TOLERANCE:
        raise CourseValidationError("line length must be positive")
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    offset = width / 2.0 + wall["thickness"] / 2.0
    center_x, center_y = (start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0
    yaw = math.atan2(uy, ux)
    boxes = []
    for side_name, sign in (("left", 1.0), ("right", -1.0)):
        boxes.append(
            BoxObject(
                name="wall_{:03d}_{}".format(next_id - WALL_ID_START, side_name),
                copter_id=next_id,
                category="wall",
                center=Vec3(
                    center_x + sign * nx * offset,
                    center_y + sign * ny * offset,
                    0.0,
                ),
                size=Vec3(length, wall["thickness"], wall["height"]),
                yaw_rad=yaw,
            )
        )
        next_id += 1
    return boxes, next_id


def _arc_wall_boxes(
    element: Dict[str, Any], wall: Dict[str, float], next_id: int
) -> Tuple[List[BoxObject], int]:
    center = _vec2(element["center"], "arc center")
    radius = float(element["radius"])
    width = float(element["width"])
    start_angle, sweep = _arc_sweep(element)
    max_delta = 2.0 * math.acos(max(-1.0, 1.0 - wall["max_chord_error"] / radius))
    segment_count = max(1, int(math.ceil(abs(sweep) / max_delta)))
    delta = sweep / segment_count
    inner_radius = radius - width / 2.0 - wall["thickness"] / 2.0
    outer_radius = radius + width / 2.0 + wall["thickness"] / 2.0
    if inner_radius <= 0.0:
        raise CourseValidationError("wall thickness leaves no inner turn radius")

    boxes: List[BoxObject] = []
    for index in range(segment_count):
        angle0 = start_angle + index * delta
        angle1 = start_angle + (index + 1) * delta
        for radius_name, wall_radius in (("inner", inner_radius), ("outer", outer_radius)):
            p0 = (
                center[0] + wall_radius * math.cos(angle0),
                center[1] + wall_radius * math.sin(angle0),
            )
            p1 = (
                center[0] + wall_radius * math.cos(angle1),
                center[1] + wall_radius * math.sin(angle1),
            )
            boxes.append(
                BoxObject(
                    name="wall_{:03d}_{}".format(next_id - WALL_ID_START, radius_name),
                    copter_id=next_id,
                    category="wall",
                    center=Vec3(
                        (p0[0] + p1[0]) / 2.0,
                        (p0[1] + p1[1]) / 2.0,
                        0.0,
                    ),
                    size=Vec3(
                        _distance2(p0, p1), wall["thickness"], wall["height"]
                    ),
                    yaw_rad=math.atan2(p1[1] - p0[1], p1[0] - p0[0]),
                )
            )
            next_id += 1
    return boxes, next_id


def _box_from_json(item: Dict[str, Any], category: str) -> BoxObject:
    return BoxObject(
        name=str(item["name"]),
        copter_id=int(item["id"]),
        category=category,
        center=_vec3(item["center"], "{} center".format(category)),
        size=_vec3(item["size"], "{} size".format(category)),
    )


def _point_to_box_xy(point: Vec3, box: BoxObject) -> float:
    dx, dy = point.x - box.center.x, point.y - box.center.y
    cosine, sine = math.cos(box.yaw_rad), math.sin(box.yaw_rad)
    local_x = cosine * dx + sine * dy
    local_y = -sine * dx + cosine * dy
    outside_x = max(abs(local_x) - box.size.x / 2.0, 0.0)
    outside_y = max(abs(local_y) - box.size.y / 2.0, 0.0)
    return math.hypot(outside_x, outside_y)


def _inside_bounds(point: Vec3, bounds: Sequence[float]) -> bool:
    return bounds[0] <= point.x <= bounds[1] and bounds[2] <= point.y <= bounds[3]


def _validate_source(data: Dict[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise CourseValidationError("unsupported schema version")
    if data.get("frame") != "ENU" or data.get("units") != "m":
        raise CourseValidationError("course frame must be ENU metres")
    for element in data.get("centreline", []):
        width = _finite_number(element.get("width"), "clear width")
        if width <= 0.0 or width > 1.5:
            raise CourseValidationError("clear width must be positive and no greater than 1.5 m")
        if element.get("kind") == "arc":
            radius = _finite_number(element.get("radius"), "turn radius")
            if radius <= 0.0 or radius > 1.0:
                raise CourseValidationError("turn radius must be positive and no greater than 1 m")
        elif element.get("kind") != "line":
            raise CourseValidationError("centreline kind must be line or arc")


def load_course(path: Path) -> CourseModel:
    path = Path(path)
    source_bytes = path.read_bytes()
    try:
        data = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CourseValidationError("invalid course JSON: {}".format(exc)) from exc
    if not isinstance(data, dict):
        raise CourseValidationError("course JSON root must be an object")
    _validate_source(data)

    owned = data.get("owned_id_range")
    if not isinstance(owned, list) or len(owned) != 2:
        raise CourseValidationError("owned ID range must contain two integers")
    owned_range = (int(owned[0]), int(owned[1]))
    if owned_range[0] > owned_range[1]:
        raise CourseValidationError("owned ID range is reversed")

    wall_config = data["wall"]
    wall = {
        "height": _finite_number(wall_config["height"], "wall height"),
        "thickness": _finite_number(wall_config["thickness"], "wall thickness"),
        "max_chord_error": _finite_number(
            wall_config["max_chord_error"], "maximum chord error"
        ),
    }
    if min(wall.values()) <= 0.0:
        raise CourseValidationError("wall dimensions must be positive")

    centreline = data["centreline"]
    if not isinstance(centreline, list) or not centreline:
        raise CourseValidationError("centreline must not be empty")
    for index, element in enumerate(centreline):
        start = _vec2(element["start"], "centreline start")
        end = _vec2(element["end"], "centreline end")
        if index and _distance2(_vec2(centreline[index - 1]["end"], "previous end"), start) > TOLERANCE:
            raise CourseValidationError("centreline elements must be adjacent")
        if element["kind"] == "arc":
            center = _vec2(element["center"], "arc center")
            radius = float(element["radius"])
            if abs(_distance2(start, center) - radius) > TOLERANCE or abs(
                _distance2(end, center) - radius
            ) > TOLERANCE:
                raise CourseValidationError("arc endpoints must match turn radius")
            _arc_sweep(element)

    wall_boxes: List[BoxObject] = []
    next_id = WALL_ID_START
    for element in centreline:
        if element["kind"] == "line":
            new_boxes, next_id = _line_wall_boxes(element, wall, next_id)
        else:
            new_boxes, next_id = _arc_wall_boxes(element, wall, next_id)
        wall_boxes.extend(new_boxes)
    if next_id > ZONE_ID_START:
        raise CourseValidationError("wall object IDs overlap reserved zone IDs")

    zone_surfaces = tuple(
        _box_from_json(item, "zone_surface") for item in data["zone_surfaces"]
    )
    arena_objects = tuple(
        _box_from_json(item, str(item["category"])) for item in data["arena_objects"]
    )
    platforms = tuple(
        _box_from_json(item, "landing_platform") for item in data["landing_platforms"]
    )
    poses = tuple(
        Pose(
            name=str(item["name"]),
            position=_vec3(item["position"], "takeoff position"),
            yaw_rad=_finite_number(item["yaw"], "takeoff yaw"),
        )
        for item in data["takeoff_poses"]
    )

    all_objects = tuple(wall_boxes) + arena_objects + zone_surfaces + platforms
    object_ids = [obj.copter_id for obj in all_objects]
    if len(set(object_ids)) != len(object_ids):
        raise CourseValidationError("duplicate object ID")
    if any(value < owned_range[0] or value > owned_range[1] for value in object_ids):
        raise CourseValidationError("object ID is outside the owned range")
    if any(min(obj.size) <= 0.0 for obj in all_objects):
        raise CourseValidationError("object sizes must be positive")

    takeoff_bounds = data["takeoff_zone"]["bounds"]
    if any(not _inside_bounds(pose.position, takeoff_bounds) for pose in poses):
        raise CourseValidationError("takeoff position is outside takeoff zone")
    landing_bounds = data["landing_zone"]["bounds"]
    if any(not _inside_bounds(platform.center, landing_bounds) for platform in platforms):
        raise CourseValidationError("landing platform is outside landing zone")
    if len(platforms) < len(poses):
        raise CourseValidationError("landing platform count is smaller than UAV count")
    platform_spacing = min(
        _distance2(
            (platforms[i].center.x, platforms[i].center.y),
            (platforms[j].center.x, platforms[j].center.y),
        )
        for i in range(len(platforms))
        for j in range(i + 1, len(platforms))
    )
    if platform_spacing <= 1.5 + TOLERANCE:
        raise CourseValidationError("platform spacing must be greater than 1.5 m")

    envelope_radius = _finite_number(
        data["vehicle_envelope"]["horizontal_diameter"], "vehicle envelope"
    ) / 2.0
    for pose in poses:
        if any(_point_to_box_xy(pose.position, wall_box) < envelope_radius for wall_box in wall_boxes):
            raise CourseValidationError("takeoff clearance intersects a wall")

    return CourseModel(
        course_name=str(data["course_name"]),
        base_map=str(data["base_map"]),
        owned_id_range=owned_range,
        spec_sha256=hashlib.sha256(source_bytes).hexdigest(),
        raw=data,
        takeoff_poses=poses,
        wall_boxes=tuple(wall_boxes),
        arena_objects=arena_objects,
        zone_surfaces=zone_surfaces,
        landing_platforms=platforms,
    )


def enu_to_ned(position: Vec3) -> Vec3:
    return Vec3(position.y, position.x, -position.z)


def yaw_enu_to_ned(yaw_rad: float) -> float:
    return math.pi / 2.0 - yaw_rad


def course_report(model: CourseModel) -> Dict[str, Any]:
    elements = model.raw["centreline"]
    length = 0.0
    turn_radii: List[float] = []
    for element in elements:
        if element["kind"] == "line":
            length += _distance2(tuple(element["start"]), tuple(element["end"]))
        else:
            _, sweep = _arc_sweep(element)
            radius = float(element["radius"])
            length += radius * abs(sweep)
            turn_radii.append(radius)
    takeoff_separation = _distance2(
        (model.takeoff_poses[0].position.x, model.takeoff_poses[0].position.y),
        (model.takeoff_poses[1].position.x, model.takeoff_poses[1].position.y),
    )
    platform_spacing = _distance2(
        (model.landing_platforms[0].center.x, model.landing_platforms[0].center.y),
        (model.landing_platforms[1].center.x, model.landing_platforms[1].center.y),
    )
    return {
        "spec_sha256": model.spec_sha256,
        "centreline_length_m": round(length, 6),
        "minimum_clear_width_m": min(float(item["width"]) for item in elements),
        "maximum_turn_radius_m": max(turn_radii),
        "takeoff_separation_m": round(takeoff_separation, 6),
        "platform_spacing_m": round(platform_spacing, 6),
        "object_count": len(model.scene_objects),
    }
