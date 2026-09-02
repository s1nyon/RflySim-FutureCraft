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
    "box_asset",
    "clearance_policy", "takeoff_area", "spawns", "spawn_yaw_deg",
    "arena_objects", "zone_surfaces", "course", "static_obstacles",
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


def _line_basis(item: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    start = _vec(item["start"], 2, "line start")
    end = _vec(item["end"], 2, "line end")
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        raise CourseValidationError("line length must be positive")
    ux, uy = dx / length, dy / length
    return ux, uy, -uy, ux, length


def _named_course(spec: Dict[str, Any], name: str) -> Dict[str, Any]:
    matches = [item for item in spec["course"] if item.get("name") == name]
    if len(matches) != 1:
        raise CourseValidationError("segment {} must name exactly one course element".format(name))
    return matches[0]


def static_clearance_reports(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    required = float(spec["clearance_policy"]["minimum_passable_gap_m"])
    reports: List[Dict[str, Any]] = []
    for obstacle in spec["static_obstacles"]:
        element = _named_course(spec, obstacle.get("segment", ""))
        if element.get("kind") != "line":
            raise CourseValidationError("{} segment must be a line".format(obstacle["name"]))
        ux, uy, nx, ny, length = _line_basis(element)
        center = _vec(obstacle["center"], 3, "{} center".format(obstacle["name"]))
        size = _vec(obstacle["size"], 3, "{} size".format(obstacle["name"]))
        rel_x, rel_y = center[0] - element["start"][0], center[1] - element["start"][1]
        along = rel_x * ux + rel_y * uy
        offset = rel_x * nx + rel_y * ny
        half_lateral = abs(nx) * size[0] / 2.0 + abs(ny) * size[1] / 2.0
        half_longitudinal = abs(ux) * size[0] / 2.0 + abs(uy) * size[1] / 2.0
        half_width = float(element["width"]) / 2.0
        left_gap = half_width - (offset + half_lateral)
        right_gap = (offset - half_lateral) + half_width
        passable = max(left_gap, right_gap)
        contained = half_longitudinal <= along <= length - half_longitudinal
        reports.append({
            "name": obstacle["name"], "segment": element["name"],
            "left_gap_m": left_gap, "right_gap_m": right_gap,
            "passable_gap_m": passable, "required_gap_m": required,
            "longitudinally_contained": contained,
            "passes": contained and passable + 1e-12 >= required,
        })
    return reports


def turn_clearance_reports(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    diameter = float(spec["clearance_policy"]["vehicle_diameter_m"])
    required = float(spec["clearance_policy"]["lateral_margin_each_side_m"])
    chord_error = float(spec["wall"]["max_chord_error"])
    reports: List[Dict[str, Any]] = []
    for item in spec["course"]:
        if item["kind"] != "arc":
            continue
        margin = (float(item["width"]) - diameter) / 2.0 - chord_error
        reports.append({
            "name": item["name"], "center_margin_m": margin,
            "required_margin_m": required, "passes": margin + 1e-12 >= required,
        })
    return reports


def spawn_clearance_report(spec: Dict[str, Any]) -> Dict[str, Any]:
    diameter = float(spec["clearance_policy"]["vehicle_diameter_m"])
    margin = float(spec["clearance_policy"]["lateral_margin_each_side_m"])
    radius = diameter / 2.0 + margin
    bounds = _vec(spec["takeoff_area"]["bounds"], 4, "takeoff bounds")
    entry = _vec(spec["course"][0]["start"], 2, "course entry")
    boundary_clearances: Dict[str, float] = {}
    headings: Dict[str, bool] = {}
    positions: Dict[str, Tuple[float, ...]] = {}
    for name in ("uav1", "uav2"):
        position = _vec(spec["spawns"][name], 3, "{} spawn".format(name))
        positions[name] = position
        boundary_clearances[name] = min(
            position[0] - bounds[0], bounds[1] - position[0],
            position[1] - bounds[2], bounds[3] - position[1],
        ) - radius
        yaw = math.radians(float(spec["spawn_yaw_deg"][name]))
        to_entry = (entry[0] - position[0], entry[1] - position[1])
        headings[name] = math.cos(yaw) * to_entry[0] + math.sin(yaw) * to_entry[1] > 0.0
    surface_gap = _distance(positions["uav1"], positions["uav2"]) - diameter
    required_surface_gap = 2.0 * margin
    passes = (min(boundary_clearances.values()) >= -1e-12 and
              surface_gap + 1e-12 >= required_surface_gap and all(headings.values()))
    return {
        "boundary_clearance_m": boundary_clearances,
        "inter_uav_surface_gap_m": surface_gap,
        "required_inter_uav_surface_gap_m": required_surface_gap,
        "headings_toward_entry": headings,
        "passes": passes,
    }


def pendulum_clearance_report(spec: Dict[str, Any]) -> Dict[str, Any]:
    dynamic = spec["dynamic_obstacle"]
    element = _named_course(spec, dynamic.get("segment", ""))
    if element.get("kind") != "line":
        raise CourseValidationError("{} segment must be a line".format(dynamic["name"]))
    _, _, nx, ny, _ = _line_basis(element)
    size = _vec(dynamic["size"], 3, "pendulum size")
    half_lateral = abs(nx) * size[0] / 2.0 + abs(ny) * size[1] / 2.0
    required_gap = float(spec["clearance_policy"]["minimum_passable_gap_m"])
    required_window = float(spec["clearance_policy"]["minimum_dynamic_safe_window_sec"])
    sample_hz = float(spec["clearance_policy"]["sampling_hz"])
    period = float(dynamic["period_sec"])
    sample_count = max(1, int(round(period * sample_hz)))
    safe: List[bool] = []
    maximum_gap = -math.inf
    start = element["start"]
    half_width = float(element["width"]) / 2.0
    for index in range(sample_count):
        position = pendulum_pose(dynamic, index / sample_hz)
        offset = (position[0] - start[0]) * nx + (position[1] - start[1]) * ny
        left_gap = half_width - (offset + half_lateral)
        right_gap = (offset - half_lateral) + half_width
        open_gap = max(left_gap, right_gap)
        maximum_gap = max(maximum_gap, open_gap)
        safe.append(open_gap + 1e-12 >= required_gap)
    longest = current = 0
    for value in safe + safe:
        current = current + 1 if value else 0
        longest = max(longest, current)
    longest = min(longest, sample_count)
    longest_sec = longest / sample_hz
    safe_windows: List[Dict[str, float]] = []
    run_start = None
    for index, value in enumerate(safe + [False]):
        if value and run_start is None:
            run_start = index
        elif not value and run_start is not None:
            safe_windows.append({
                "start_sec": run_start / sample_hz,
                "end_sec": index / sample_hz,
                "duration_sec": (index - run_start) / sample_hz,
            })
            run_start = None
    return {
        "name": dynamic["name"], "segment": element["name"],
        "maximum_open_side_gap_m": maximum_gap,
        "required_gap_m": required_gap,
        "longest_safe_window_sec": longest_sec,
        "safe_windows_sec": safe_windows,
        "required_safe_window_sec": required_window,
        "sampling_hz": sample_hz,
        "passes": maximum_gap + 1e-12 >= required_gap and longest_sec + 1e-12 >= required_window,
    }


def _route_polyline(spec: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Approximate the centreline with the same chord-error bound as the walls."""
    points: List[Tuple[float, float]] = []
    chord_error = float(spec["wall"]["max_chord_error"])
    for item in spec["course"]:
        if item["kind"] == "line":
            candidates = [tuple(float(value) for value in item["start"]),
                          tuple(float(value) for value in item["end"])]
        else:
            radius = float(item["radius"])
            start_angle, sweep = _arc_angles(item)
            max_delta = 2.0 * math.acos(max(-1.0, 1.0 - chord_error / radius))
            count = max(1, int(math.ceil(abs(sweep) / max_delta)))
            center = item["center"]
            candidates = [
                (center[0] + radius * math.cos(start_angle + sweep * index / count),
                 center[1] + radius * math.sin(start_angle + sweep * index / count))
                for index in range(count + 1)
            ]
        for point in candidates:
            if not points or _distance(points[-1], point) > 1e-12:
                points.append(point)
    return points


def _proper_segment_intersection(a: Tuple[float, float], b: Tuple[float, float],
                                 c: Tuple[float, float], d: Tuple[float, float]) -> bool:
    """Return true only for a non-endpoint crossing of two line segments."""
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    ab_c, ab_d = cross(a, b, c), cross(a, b, d)
    cd_a, cd_b = cross(c, d, a), cross(c, d, b)
    tolerance = 1e-10
    return ((ab_c > tolerance and ab_d < -tolerance) or
            (ab_c < -tolerance and ab_d > tolerance)) and ((cd_a > tolerance and cd_b < -tolerance) or
                                                            (cd_a < -tolerance and cd_b > tolerance))


def route_geometry_report(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Conservatively check route envelope width and approximate self-crossings."""
    points = _route_polyline(spec)
    intersections: List[Dict[str, int]] = []
    for first in range(len(points) - 1):
        for second in range(first + 2, len(points) - 1):
            if _proper_segment_intersection(points[first], points[first + 1],
                                            points[second], points[second + 1]):
                intersections.append({"first_segment": first, "second_segment": second})
    minimum_width = min(float(item["width"]) for item in spec["course"])
    required_width = (float(spec["clearance_policy"]["vehicle_diameter_m"]) +
                      2.0 * float(spec["clearance_policy"]["lateral_margin_each_side_m"]))
    return {
        "method": "centreline chord sampling plus proper segment intersections",
        "sample_count": len(points),
        "sampling_max_chord_error_m": float(spec["wall"]["max_chord_error"]),
        "self_intersections": intersections,
        "minimum_clear_width_m": minimum_width,
        "required_envelope_width_m": required_width,
        "passes": not intersections and minimum_width + 1e-12 >= required_width,
    }


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
    box_asset = spec.get("box_asset", {})
    if box_asset.get("vehicle_type") != wall.get("vehicle_type"):
        raise CourseValidationError("box asset vehicle_type must match wall vehicle_type")
    native_size = _vec(box_asset.get("native_size_m"), 3, "box asset native_size_m")
    if any(value <= 0 for value in native_size):
        raise CourseValidationError("box asset native_size_m must be positive")
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
    yaw_by_uav = spec.get("spawn_yaw_deg", {})
    if set(yaw_by_uav) != {"uav1", "uav2"}:
        raise CourseValidationError("spawn_yaw_deg must contain uav1 and uav2")
    for name in ("uav1", "uav2"):
        _number(yaw_by_uav[name], "{} spawn yaw".format(name))

    policy = spec.get("clearance_policy", {})
    required_policy = {
        "vehicle_diameter_m", "lateral_margin_each_side_m",
        "minimum_passable_gap_m", "minimum_dynamic_safe_window_sec",
        "sampling_hz",
    }
    if set(policy) != required_policy:
        raise CourseValidationError("clearance_policy fields do not match contract")
    for key in required_policy:
        if _number(policy[key], "clearance policy {}".format(key)) <= 0:
            raise CourseValidationError("clearance policy {} must be positive".format(key))
    if abs(float(policy["vehicle_diameter_m"]) - required_sep) > 1e-9:
        raise CourseValidationError("clearance vehicle diameter must match vehicle envelope")

    route_report = route_geometry_report(spec)
    if not route_report["passes"]:
        if route_report["self_intersections"]:
            raise CourseValidationError("course centreline has an approximate self-intersection")
        raise CourseValidationError(
            "minimum corridor width {:.6f} m is below vehicle safety envelope {:.6f} m".format(
                route_report["minimum_clear_width_m"], route_report["required_envelope_width_m"]
            )
        )

    arena = list(spec.get("arena_objects", []))
    surfaces = list(spec.get("zone_surfaces", []))
    if len(arena) != 8 or len(surfaces) != 2:
        raise CourseValidationError("accepted substrate requires eight arena objects and two zone surfaces")
    for item in arena + surfaces:
        size = _vec(item["size"], 3, "{} size".format(item["name"]))
        _vec(item["center"], 3, "{} center".format(item["name"]))
        if any(value <= 0 for value in size):
            raise CourseValidationError("{} size must be positive".format(item["name"]))

    explicit = arena + surfaces + list(spec["static_obstacles"]) + [spec["dynamic_obstacle"], spec["mission_target_slot"]]
    explicit += list(spec["landing"]["platforms"]) + list(spec["landing"]["markers"])
    ids = []
    for item in explicit:
        object_id = item.get("id")
        if not isinstance(object_id, int) or not id_range[0] <= object_id <= id_range[1]:
            raise CourseValidationError("object ID must be in owned range")
        ids.append(object_id)
        if item not in spec["landing"]["markers"] and item.get("vehicle_type") != box_asset["vehicle_type"]:
            raise CourseValidationError("{} must use the declared box asset".format(item.get("name", "entity")))
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

    for report in static_clearance_reports(spec):
        if not report["passes"]:
            raise CourseValidationError(
                "{} passable gap {:.6f} m is below required {:.6f} m or obstacle is outside its segment".format(
                    report["name"], report["passable_gap_m"], report["required_gap_m"]
                )
            )
    for report in turn_clearance_reports(spec):
        if not report["passes"]:
            raise CourseValidationError(
                "{} center margin {:.6f} m is below required {:.6f} m".format(
                    report["name"], report["center_margin_m"], report["required_margin_m"]
                )
            )
    spawn_report = spawn_clearance_report(spec)
    if not spawn_report["passes"]:
        for name in ("uav1", "uav2"):
            if spawn_report["boundary_clearance_m"][name] < 0:
                raise CourseValidationError("{} spawn safety envelope leaves the takeoff area".format(name))
            if not spawn_report["headings_toward_entry"][name]:
                raise CourseValidationError("{} spawn heading points away from course entry".format(name))
        raise CourseValidationError("spawn separation is below the clearance policy")
    dynamic_report = pendulum_clearance_report(spec)
    if not dynamic_report["passes"]:
        raise CourseValidationError(
            "{} safe window {:.6f} s is below required {:.6f} s or open-side gap is insufficient".format(
                dynamic_report["name"], dynamic_report["longest_safe_window_sec"],
                dynamic_report["required_safe_window_sec"]
            )
        )


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


def _box_scale(size: Sequence[float], spec: Dict[str, Any]) -> List[float]:
    native = spec["box_asset"]["native_size_m"]
    return [float(value) / float(native[index]) for index, value in enumerate(size)]


def _entity(item: Dict[str, Any], category: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    result = {"name": item["name"], "id": item["id"], "category": category, "center": item.get("center", item.get("pivot")), "size": item.get("size"), "vehicle_type": item.get("vehicle_type", item.get("class_id")), "collision": bool(item.get("collision", False))}
    if category != "aruco":
        result["scale"] = _box_scale(result["size"], spec)
    return result


def build_entity_manifest(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    walls = [{"name": item.name, "id": item.object_id, "category": item.category, "center": list(asdict(item.center).values()), "size": list(asdict(item.size).values()), "scale": _box_scale(list(asdict(item.size).values()), spec), "yaw_rad": item.yaw_rad, "vehicle_type": item.vehicle_type, "collision": item.collision} for item in build_wall_boxes(spec)]
    entities = walls + [_entity(item, item["category"], spec) for item in spec["arena_objects"]]
    entities += [_entity(item, "zone_surface", spec) for item in spec["zone_surfaces"]]
    entities += [_entity(item, "static_obstacle", spec) for item in spec["static_obstacles"]]
    dynamic_entity = _entity(spec["dynamic_obstacle"], "dynamic_obstacle", spec)
    # The suspension pivot is a reference point, not the moving object centre.
    # Spawning at the pivot would make the first motion update jump the bob into
    # its phase-zero position; the entity must be created at pendulum_pose(t=0).
    dynamic_entity["center"] = list(pendulum_pose(spec["dynamic_obstacle"], 0.0))
    dynamic_entity["pivot"] = list(spec["dynamic_obstacle"]["pivot"])
    entities += [dynamic_entity, _entity(spec["mission_target_slot"], "mission_target_slot", spec)]
    entities += [_entity(item, "landing_platform", spec) for item in spec["landing"]["platforms"]]
    entities += [_entity(item, "aruco", spec) for item in spec["landing"]["markers"]]
    ids = [item["id"] for item in entities]
    if len(ids) != len(set(ids)):
        raise CourseValidationError("duplicate object ID including generated walls")
    return sorted(entities, key=lambda item: item["id"])


def pendulum_pose(dynamic_spec: Dict[str, Any], elapsed_sec: float) -> Tuple[float, float, float]:
    elapsed = _number(elapsed_sec, "elapsed_sec")
    pivot = _vec(dynamic_spec["pivot"], 3, "pendulum pivot")
    angle = math.radians(float(dynamic_spec["amplitude_deg"])) * math.sin(2 * math.pi * elapsed / float(dynamic_spec["period_sec"]) + float(dynamic_spec["phase_rad"]))
    return (pivot[0], pivot[1] + float(dynamic_spec["length_m"]) * math.sin(angle), pivot[2] - float(dynamic_spec["length_m"]) * math.cos(angle))
