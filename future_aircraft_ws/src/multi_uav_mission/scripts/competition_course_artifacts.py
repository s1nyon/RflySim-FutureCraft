#!/usr/bin/env python3
"""Generate deterministic Competition Course V2 deployment artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import cv2

from competition_course_geometry import build_entity_manifest, build_wall_boxes, load_spec
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


def _preview(spec: Dict[str, Any]) -> str:
    walls = build_wall_boxes(spec)
    rows = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -11 31 15" width="1240" height="600">', '<rect x="-1" y="-11" width="31" height="15" fill="#f5f5f2"/>']
    for wall in walls:
        rows.append('<rect x="{:.3f}" y="{:.3f}" width="{:.3f}" height="{:.3f}" fill="#515a66" transform="rotate({:.3f} {:.3f} {:.3f})"/>'.format(wall.center.x - wall.size.x / 2, -wall.center.y - wall.size.y / 2, wall.size.x, wall.size.y, -math.degrees(wall.yaw_rad), wall.center.x, -wall.center.y))
    points = " ".join("{:.3f},{:.3f}".format(p[0], -p[1]) for p in _course_points(spec))
    rows.append('<polyline points="{}" fill="none" stroke="#f2b134" stroke-width="0.08" stroke-dasharray="0.2 0.1"/>'.format(points))
    for name, position in sorted(spec["spawns"].items()):
        rows.append('<circle cx="{:.3f}" cy="{:.3f}" r="0.20" fill="#2780c2"/><text x="{:.3f}" y="{:.3f}" font-size="0.3">{}</text>'.format(position[0], -position[1], position[0] + .25, -position[1], name))
    for item in spec["static_obstacles"] + [spec["dynamic_obstacle"], spec["mission_target_slot"]]:
        center = item.get("center", item.get("pivot")); rows.append('<circle cx="{:.3f}" cy="{:.3f}" r="0.18" fill="#bd3d3a"/><text x="{:.3f}" y="{:.3f}" font-size="0.22">{}</text>'.format(center[0], -center[1], center[0] + .2, -center[1], item["name"]))
    for item in spec["landing"]["platforms"]:
        rows.append('<rect x="{:.3f}" y="{:.3f}" width="{:.3f}" height="{:.3f}" fill="#f1d86a"/>'.format(item["center"][0] - item["size"][0] / 2, -item["center"][1] - item["size"][1] / 2, item["size"][0], item["size"][1]))
    rows += ['<text x="0" y="3" font-size="0.28">Competition Course V2 — ENU, independent UAV localization origins</text>', '</svg>']
    return "\n".join(rows) + "\n"


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
    _json(output / "entity_manifest.json", {"map_id": spec["map_id"], "coordinate_frame": "ENU", "spec_sha256": spec["spec_sha256"], "owned_cleanup": "receipt_only", "entities": entities})
    _json(output / "planning_points.json", {"frame_id": "competition_course_v2_enu", "semantic_note": "map geometry only; not an established shared UAV TF", "spec_sha256": spec["spec_sha256"], "points": _course_points(spec)})
    _json(output / "validation_report.json", {"result": "PASS", "validation_level": "STRUCTURAL", "spec_sha256": spec["spec_sha256"], "entity_count": len(entities), "wall_count": len(build_wall_boxes(spec)), "static_obstacle_count": len(spec["static_obstacles"]), "dynamic_obstacle_count": 1, "aruco_marker_ids": sorted(item["marker_id"] for item in spec["landing"]["markers"]), "full_mission": "NOT_REQUIRED"})
    (output / "course_preview.svg").write_text(_preview(spec), encoding="utf-8")
    terrain = spec["terrain"]
    write_flat_png16(output / "SLAMScene.png", int(terrain["pixels"][0]), int(terrain["pixels"][1]), int(terrain["height_raw"]))
    bounds = terrain["bounds"]
    (output / "SLAMScene.txt").write_text("{},{},0,{},{},0,0,0,0\n".format(int(round(bounds[1] * 100)), int(round(bounds[3] * 100)), int(round(bounds[0] * 100)), int(round(bounds[2] * 100))), encoding="ascii")
    for marker in spec["landing"]["markers"]:
        _write_marker(marker_dir / "marker_{}.png".format(marker["marker_id"]), int(marker["marker_id"]))
    files = sorted(path for path in output.rglob("*") if path.is_file())
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
