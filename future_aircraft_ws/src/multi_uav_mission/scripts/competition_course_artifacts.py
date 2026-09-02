#!/usr/bin/env python3
"""Generate deterministic Competition Course V2 deployment artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import cv2

from competition_course_geometry import (
    build_entity_manifest,
    build_wall_boxes,
    load_spec,
    pendulum_clearance_report,
    route_geometry_report,
    spawn_clearance_report,
    static_clearance_reports,
    turn_clearance_reports,
)
from narrow_course_artifacts import write_flat_png16


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _course_points(spec: Dict[str, Any]) -> List[List[float]]:
    points: List[List[float]] = []
    for item in spec["course"]:
        if item["kind"] == "line":
            candidates = [item["start"], item["end"]]
        else:
            center, start = item["center"], item["start"]
            a0 = math.atan2(start[1] - center[1], start[0] - center[0])
            sweep = math.pi / 2 if item["turn"] == "left" else -math.pi / 2
            candidates = [[center[0] + item["radius"] * math.cos(a0 + sweep * i / 12), center[1] + item["radius"] * math.sin(a0 + sweep * i / 12)] for i in range(13)]
        for point in candidates:
            value = [round(float(point[0]), 6), round(float(point[1]), 6), 1.0]
            if not points or points[-1] != value:
                points.append(value)
    return points


def _rect(item: Dict[str, Any], fill: str, opacity: float = 1.0) -> str:
    center, size = item["center"], item["size"]
    yaw = -math.degrees(float(item.get("yaw_rad", 0.0)))
    return ('<rect x="{:.3f}" y="{:.3f}" width="{:.3f}" height="{:.3f}" '
            'fill="{}" opacity="{:.3f}" transform="rotate({:.3f} {:.3f} {:.3f})"/>').format(
                center[0] - size[0] / 2.0, -center[1] - size[1] / 2.0,
                size[0], size[1], fill, opacity, yaw, center[0], -center[1])


def _text(x: float, y: float, value: str, size: float = 0.24, fill: str = "#17202a") -> str:
    return '<text x="{:.3f}" y="{:.3f}" font-size="{:.3f}" fill="{}">{}</text>'.format(
        x, y, size, fill, escape(value))


def build_preview_svg(spec: Dict[str, Any], entities: List[Dict[str, Any]], reports: Dict[str, Any]) -> str:
    """Build a deterministic, dimensioned ENU top-down engineering preview."""
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="7.000 -13.000 34.000 23.500" width="1530" height="1058" data-coordinate-frame="ENU" data-shared-world="false">',
        '<rect x="7.000" y="-13.000" width="34.000" height="23.500" fill="#f6f7f2"/>',
    ]
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for entity in entities:
        by_category.setdefault(entity["category"], []).append(entity)

    rows.append('<g id="arena">')
    for category, color, opacity in (("arena_floor", "#dde7d7", 0.55), ("zone_surface", "#c6e2ff", 0.75),
                                     ("boundary_wall", "#6d747c", 0.9), ("ceiling", "#d8d8d8", 0.08)):
        for item in by_category.get(category, []):
            rows.append(_rect(item, color, opacity))
    rows.append('</g>')

    rows.append('<g id="centerline">')
    points = " ".join("{:.3f},{:.3f}".format(point[0], -point[1]) for point in _course_points(spec))
    rows.append('<polyline points="{}" fill="none" stroke="#f2a900" stroke-width="0.080" stroke-dasharray="0.240 0.120"/>'.format(points))
    for item in spec["course"]:
        if item["kind"] == "line":
            center = ((item["start"][0] + item["end"][0]) / 2.0, (item["start"][1] + item["end"][1]) / 2.0)
            label = "Section {}".format(item["name"].split("_")[-1].upper())
            rows.append(_text(center[0], -center[1] - 0.22, label))
    rows.append('</g>')

    rows.append('<g id="walls">')
    for item in by_category.get("wall", []):
        rows.append(_rect(item, "#3e4a59"))
    rows.append('</g>')

    rows.append('<g id="spawns">')
    safety_radius = (float(spec["clearance_policy"]["vehicle_diameter_m"]) / 2.0 +
                     float(spec["clearance_policy"]["lateral_margin_each_side_m"]))
    for name in ("uav1", "uav2"):
        position = spec["spawns"][name]
        rows.append('<circle cx="{:.3f}" cy="{:.3f}" r="{:.3f}" fill="#2d84c4" opacity="0.22" stroke="#1c5d8c" stroke-width="0.035"/>'.format(position[0], -position[1], safety_radius))
        rows.append(_text(position[0] + 0.20, -position[1] - 0.18, "{} ({:.3f},{:.3f})".format(name, position[0], position[1])))
    rows.append('</g>')

    rows.append('<g id="camera_axes">')
    for name in ("uav1", "uav2"):
        position, yaw = spec["spawns"][name], math.radians(float(spec["spawn_yaw_deg"][name]))
        end = (position[0] + math.cos(yaw), position[1] + math.sin(yaw))
        rows.append('<line x1="{:.3f}" y1="{:.3f}" x2="{:.3f}" y2="{:.3f}" stroke="#005f73" stroke-width="0.055"/>'.format(position[0], -position[1], end[0], -end[1]))
    rows.append('</g>')

    static_by_name = {item["name"]: item for item in reports["static"]}
    rows.append('<g id="static_obstacles">')
    for item in spec["static_obstacles"]:
        rows.append(_rect(item, "#c44536"))
        report = static_by_name[item["name"]]
        rows.append(_text(item["center"][0] + 0.20, -item["center"][1], "{} gap {:.3f} m".format(item["name"], report["passable_gap_m"]), 0.21, "#8b1e16"))
    rows.append('</g>')

    dynamic = spec["dynamic_obstacle"]
    deflection = float(dynamic["length_m"]) * math.sin(math.radians(float(dynamic["amplitude_deg"])))
    rows.append('<g id="pendulum_sweep">')
    rows.append('<rect x="{:.3f}" y="{:.3f}" width="{:.3f}" height="{:.3f}" fill="#8249a8" opacity="0.20" stroke="#60337d" stroke-width="0.035"/>'.format(
        dynamic["pivot"][0] - dynamic["size"][0] / 2.0,
        -dynamic["pivot"][1] - deflection - dynamic["size"][1] / 2.0,
        dynamic["size"][0], 2.0 * deflection + dynamic["size"][1]))
    rows.append(_text(dynamic["pivot"][0] - 1.50, -dynamic["pivot"][1] - 1.05,
                      "safe window {:.3f} s".format(reports["pendulum"]["longest_safe_window_sec"]), 0.22, "#60337d"))
    rows.append('</g>')

    target = spec["mission_target_slot"]
    rows.append('<g id="task_zone">')
    rows.append(_rect(target, "#f4a261", 0.60))
    rows.append(_text(target["center"][0] + 0.25, -target["center"][1] - 0.45, "mission target placeholder", 0.21))
    rows.append('</g>')

    rows.append('<g id="landing">')
    for item in spec["landing"]["platforms"]:
        rows.append(_rect(item, "#e9c46a"))
    for marker in spec["landing"]["markers"]:
        border = float(marker["white_border_size_m"])
        physical = float(marker["physical_size_m"])
        footprint = {"center": marker["center"], "size": [border, border], "yaw_rad": math.radians(float(marker["yaw_deg"]))}
        marker_face = {"center": marker["center"], "size": [physical, physical], "yaw_rad": footprint["yaw_rad"]}
        rows.append(_rect(footprint, "#ffffff"))
        rows.append(_rect(marker_face, "#202020", 0.82))
        rows.append(_text(marker["center"][0] + 0.55, -marker["center"][1], "ArUco {}".format(marker["marker_id"]), 0.20))
    rows.append('</g>')

    rows.append('<g id="dimensions">')
    dimension_y = 8.00
    rows.append(_text(8.0, dimension_y, "minimum passable gap {:.3f} m".format(spec["clearance_policy"]["minimum_passable_gap_m"]), 0.28))
    for index, item in enumerate(spec["course"]):
        if item["kind"] == "line":
            length = math.hypot(item["end"][0] - item["start"][0], item["end"][1] - item["start"][1])
            value = "{} length {:.3f} m width {:.3f} m".format(item["name"], length, item["width"])
        else:
            value = "{} radius {:.3f} m width {:.3f} m".format(item["name"], item["radius"], item["width"])
        rows.append(_text(8.0 + (index % 2) * 11.5, dimension_y + 0.35 + (index // 2) * 0.35, value, 0.23))
    rows.append('</g>')

    rows.append('<g id="legend">')
    rows.append(_text(8.0, 9.20, "Competition Course V2 — OFFLINE VISUAL REVIEW", 0.31))
    rows.append(_text(8.0, 9.55, "ENU map geometry; independent UAV localization origins; no shared-world TF", 0.22))
    rows.append(_text(25.0, 9.20, "spec_sha256 {}".format(spec["spec_sha256"]), 0.18))
    rows.append('</g>')
    rows.append('</svg>')
    return "\n".join(rows) + "\n"


def _box_polygon(item: Dict[str, Any]) -> List[List[float]]:
    center, size = item["center"], item["size"]
    yaw = float(item.get("yaw_rad", 0.0))
    cosine, sine = math.cos(yaw), math.sin(yaw)
    result: List[List[float]] = []
    for local_x, local_y in ((-size[0] / 2.0, -size[1] / 2.0),
                             (size[0] / 2.0, -size[1] / 2.0),
                             (size[0] / 2.0, size[1] / 2.0),
                             (-size[0] / 2.0, size[1] / 2.0)):
        result.append([
            center[0] + local_x * cosine - local_y * sine,
            center[1] + local_x * sine + local_y * cosine,
        ])
    return result


def _course_progress(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    progress: List[Dict[str, Any]] = []
    cumulative = 0.0
    for item in spec["course"]:
        if item["kind"] == "line":
            length = math.hypot(item["end"][0] - item["start"][0], item["end"][1] - item["start"][1])
        else:
            center = item["center"]
            a0 = math.atan2(item["start"][1] - center[1], item["start"][0] - center[0])
            a1 = math.atan2(item["end"][1] - center[1], item["end"][0] - center[0])
            sweep = ((a1 - a0) % (2.0 * math.pi) if item["turn"] == "left"
                     else -((a0 - a1) % (2.0 * math.pi)))
            length = abs(sweep) * float(item["radius"])
        entry = {
            "name": item["name"], "kind": item["kind"],
            "s_start_m": cumulative, "s_end_m": cumulative + length,
            "length_m": length, "width_m": float(item["width"]),
            "start_enu_xy": list(item["start"]), "end_enu_xy": list(item["end"]),
        }
        if item["kind"] == "arc":
            entry.update({"center_enu_xy": list(item["center"]), "radius_m": float(item["radius"]), "turn": item["turn"]})
        progress.append(entry)
        cumulative += length
    return progress


def build_evaluation_reference(spec: Dict[str, Any], entities: List[Dict[str, Any]], reports: Dict[str, Any]) -> Dict[str, Any]:
    """Describe map truth and evidence sources without inventing a GT transport."""
    wall_polygons = [
        {"id": item["id"], "name": item["name"], "polygon_enu_xy": _box_polygon(item)}
        for item in entities if item["category"] == "wall"
    ]
    static_polygons = [
        {"id": item["id"], "name": item["name"], "polygon_enu_xy": _box_polygon(item)}
        for item in spec["static_obstacles"]
    ]
    landing_polygons = [
        {"id": item["id"], "name": item["name"], "polygon_enu_xy": _box_polygon(item)}
        for item in spec["landing"]["platforms"]
    ]
    dynamic = spec["dynamic_obstacle"]
    metrics = [
        {"id": "takeoff_time", "unit": "s", "primary_evidence": "rflysim_ground_truth", "reference": "takeoff_area"},
        {"id": "corridor_entry_time", "unit": "s", "primary_evidence": "rflysim_ground_truth", "reference": "course_progress[0].start_enu_xy"},
        {"id": "segment_completion", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "course_progress.s_end_m"},
        {"id": "wall_clearance", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "geometry.wall_polygons"},
        {"id": "static_obstacle_clearance", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "geometry.static_obstacle_polygons"},
        {"id": "dynamic_obstacle_clearance", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "dynamic_obstacle"},
        {"id": "inter_uav_distance", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "spawns"},
        {"id": "collision_count", "unit": "count", "primary_evidence": "rflysim_ground_truth", "reference": "geometry"},
        {"id": "offboard_loss_count", "unit": "count", "primary_evidence": "ros_runtime", "reference": "/uavX/mavros/state"},
        {"id": "target_error", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "geometry.target_truth"},
        {"id": "landing_error", "unit": "m", "primary_evidence": "rflysim_ground_truth", "reference": "geometry.landing_polygons"},
        {"id": "localization_error", "unit": "m", "primary_evidence": "derived_offline", "reference": "rflysim_ground_truth+ros_runtime"},
    ]
    return {
        "schema_version": 1,
        "map_id": spec["map_id"],
        "coordinate_frame": "ENU",
        "spec_sha256": spec["spec_sha256"],
        "ground_truth_transport": "NOT_AUDITED_IN_MAP_TASK",
        "evidence_planes": {
            "map_spec": {"role": "versioned_geometry_and_semantics"},
            "rflysim_ground_truth": {"role": "physical_simulation_truth", "transport": "NOT_AUDITED_IN_MAP_TASK"},
            "ros_runtime": {"role": "algorithm_state_and_control_evidence"},
            "derived_offline": {"role": "aligned_metrics_and_error_analysis"},
            "rviz": {"role": "visualization_only", "scoring_source": False},
        },
        "spawns": dict(spec["spawns"]),
        "clearance_policy": dict(spec["clearance_policy"]),
        "course_progress": _course_progress(spec),
        "geometry": {
            "wall_polygons": wall_polygons,
            "static_obstacle_polygons": static_polygons,
            "landing_polygons": landing_polygons,
            "target_truth": {
                "id": spec["mission_target_slot"]["id"],
                "center_enu": list(spec["mission_target_slot"]["center"]),
                "size_m": list(spec["mission_target_slot"]["size"]),
                "asset": spec["mission_target_slot"]["asset"],
                "replaceable": spec["mission_target_slot"]["replaceable"],
            },
        },
        "dynamic_obstacle": {
            "id": dynamic["id"], "name": dynamic["name"],
            "pivot_enu": list(dynamic["pivot"]), "length_m": float(dynamic["length_m"]),
            "amplitude_deg": float(dynamic["amplitude_deg"]), "period_sec": float(dynamic["period_sec"]),
            "phase_rad": float(dynamic["phase_rad"]), "size_m": list(dynamic["size"]),
            "trajectory_model": "angle=amplitude*sin(2*pi*t/period+phase); swing_plane=ENU_YZ",
            "safe_windows_sec": list(reports["pendulum"]["safe_windows_sec"]),
            "longest_safe_window_sec": reports["pendulum"]["longest_safe_window_sec"],
            "maximum_open_side_gap_m": reports["pendulum"]["maximum_open_side_gap_m"],
        },
        "metrics": metrics,
    }


def _write_marker(path: Path, marker_id: int) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    image = cv2.aruco.generateImageMarker(dictionary, marker_id, 512, borderBits=1)
    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OpenCV failed to encode ArUco marker {}".format(marker_id))
    path.write_bytes(encoded.tobytes())


def generate_artifacts(spec_path: Path, output_dir: Path) -> Dict[str, Any]:
    spec = load_spec(spec_path)
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    marker_dir = output / "aruco"; marker_dir.mkdir(exist_ok=True)
    entities = build_entity_manifest(spec)
    reports = {
        "static": static_clearance_reports(spec),
        "turns": turn_clearance_reports(spec),
        "spawn": spawn_clearance_report(spec),
        "pendulum": pendulum_clearance_report(spec),
        "route": route_geometry_report(spec),
    }
    _json(output / "entity_manifest.json", {"map_id": spec["map_id"], "coordinate_frame": "ENU", "spec_sha256": spec["spec_sha256"], "owned_cleanup": "receipt_only", "entities": entities})
    _json(output / "planning_points.json", {"frame_id": "competition_course_v2_enu", "semantic_note": "map geometry only; not an established shared UAV TF", "spec_sha256": spec["spec_sha256"], "points": _course_points(spec)})
    _json(output / "evaluation_reference.json", build_evaluation_reference(spec, entities, reports))
    _json(output / "validation_report.json", {"result": "PASS", "validation_level": "STRUCTURAL", "spec_sha256": spec["spec_sha256"], "entity_count": len(entities), "wall_count": len(build_wall_boxes(spec)), "route_geometry": reports["route"], "static_obstacle_count": len(spec["static_obstacles"]), "dynamic_obstacle_count": 1, "aruco_marker_ids": sorted(item["marker_id"] for item in spec["landing"]["markers"]), "full_mission": "NOT_REQUIRED"})
    (output / "course_preview.svg").write_text(build_preview_svg(spec, entities, reports), encoding="utf-8")
    terrain = spec["terrain"]
    write_flat_png16(output / "SLAMScene.png", int(terrain["pixels"][0]), int(terrain["pixels"][1]), int(terrain["height_raw"]))
    bounds = terrain["bounds"]
    (output / "SLAMScene.txt").write_text("{},{},0,{},{},0,0,0,0\n".format(int(round(bounds[1] * 100)), int(round(bounds[3] * 100)), int(round(bounds[0] * 100)), int(round(bounds[2] * 100))), encoding="ascii")
    for marker in spec["landing"]["markers"]:
        _write_marker(marker_dir / "marker_{}.png".format(marker["marker_id"]), int(marker["marker_id"]))
    files = [
        output / "SLAMScene.png",
        output / "SLAMScene.txt",
        output / "course_preview.svg",
        output / "entity_manifest.json",
        output / "evaluation_reference.json",
        output / "planning_points.json",
        output / "validation_report.json",
    ]
    files.extend(output / "aruco" / "marker_{}.png".format(marker["marker_id"])
                 for marker in spec["landing"]["markers"])
    files = sorted(files)
    return {"spec_sha256": spec["spec_sha256"], "artifacts": {str(path.relative_to(output)).replace("\\", "/"): _sha(path) for path in files}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate_artifacts(args.spec, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
