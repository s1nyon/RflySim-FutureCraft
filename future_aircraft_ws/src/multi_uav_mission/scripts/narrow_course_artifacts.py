#!/usr/bin/env python3
"""Generate deterministic preview, planning, and terrain artifacts."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import math
import struct
import zlib
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from narrow_course_geometry import BoxObject, CourseModel, course_report, load_course


Point = Tuple[float, float, float]


def _axis_samples(length: float, spacing: float) -> List[float]:
    steps = max(1, int(math.ceil(length / spacing)))
    return [-length / 2.0 + length * index / steps for index in range(steps + 1)]


def _world_point(box: BoxObject, local_x: float, local_y: float, local_z: float) -> Point:
    cosine, sine = math.cos(box.yaw_rad), math.sin(box.yaw_rad)
    return (
        box.center.x + cosine * local_x - sine * local_y,
        box.center.y + sine * local_x + cosine * local_y,
        box.center.z + local_z,
    )


def _box_surface_points(box: BoxObject, spacing: float) -> Iterable[Point]:
    xs = _axis_samples(box.size.x, spacing)
    ys = _axis_samples(box.size.y, spacing)
    zs = _axis_samples(box.size.z, spacing)
    half_x, half_y, half_z = box.size.x / 2.0, box.size.y / 2.0, box.size.z / 2.0
    for x in xs:
        for y in ys:
            yield _world_point(box, x, y, -half_z)
            yield _world_point(box, x, y, half_z)
    for x in xs:
        for z in zs:
            yield _world_point(box, x, -half_y, z)
            yield _world_point(box, x, half_y, z)
    for y in ys:
        for z in zs:
            yield _world_point(box, -half_x, y, z)
            yield _world_point(box, half_x, y, z)


def sample_surface_points(model: CourseModel, spacing_m: float) -> List[Point]:
    if not math.isfinite(spacing_m) or spacing_m <= 0.0:
        raise ValueError("spacing_m must be finite and positive")
    unique: Dict[Tuple[int, int, int], Point] = {}
    for box in model.wall_boxes + model.landing_platforms:
        for point in _box_surface_points(box, spacing_m):
            key = tuple(int(round(value * 1000.0)) for value in point)
            unique[key] = tuple(round(value, 6) for value in point)
    return sorted(unique.values())


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", checksum)


def write_flat_png16(path: Path, width: int, height: int, raw_value: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    if raw_value < 0 or raw_value > 65535:
        raise ValueError("16-bit PNG raw value is outside 0..65535")
    sample = struct.pack(">H", raw_value)
    scanline = b"\x00" + sample * width
    raw = scanline * height
    ihdr = struct.pack(">IIBBBBB", width, height, 16, 0, 0, 0, 0)
    encoded = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(encoded)


def _box_polygon(box: BoxObject) -> str:
    points = []
    for local_x, local_y in (
        (-box.size.x / 2.0, -box.size.y / 2.0),
        (box.size.x / 2.0, -box.size.y / 2.0),
        (box.size.x / 2.0, box.size.y / 2.0),
        (-box.size.x / 2.0, box.size.y / 2.0),
    ):
        x, y, _ = _world_point(box, local_x, local_y, 0.0)
        points.append("{:.3f},{:.3f}".format(x, -y))
    return " ".join(points)


def _centreline_svg_points(model: CourseModel) -> str:
    points: List[Tuple[float, float]] = []
    for element in model.raw["centreline"]:
        if element["kind"] == "line":
            candidates = [tuple(element["start"]), tuple(element["end"])]
        else:
            center = element["center"]
            start = element["start"]
            end = element["end"]
            start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
            end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
            if element["turn"] == "left":
                while end_angle < start_angle:
                    end_angle += 2.0 * math.pi
            else:
                while end_angle > start_angle:
                    end_angle -= 2.0 * math.pi
            candidates = [
                (
                    center[0] + element["radius"] * math.cos(start_angle + (end_angle - start_angle) * i / 12.0),
                    center[1] + element["radius"] * math.sin(start_angle + (end_angle - start_angle) * i / 12.0),
                )
                for i in range(13)
            ]
        for candidate in candidates:
            if not points or candidate != points[-1]:
                points.append(candidate)
    return " ".join("{:.3f},{:.3f}".format(x, -y) for x, y in points)


def _svg(model: CourseModel, report: Dict[str, object]) -> str:
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-3 -8 22 11" width="1320" height="660">',
        '<rect x="-3" y="-8" width="22" height="11" fill="#f5f5f2"/>',
        '<g stroke="#d8d8d0" stroke-width="0.02">',
    ]
    for x in range(-3, 20):
        rows.append('<line x1="{}" y1="-8" x2="{}" y2="3"/>'.format(x, x))
    for y in range(-8, 4):
        rows.append('<line x1="-3" y1="{}" x2="19" y2="{}"/>'.format(y, y))
    rows.append("</g>")
    for surface in model.zone_surfaces:
        rows.append(
            '<polygon points="{}" fill="#d8f0d0" stroke="#4d8a43" stroke-width="0.05"/>'.format(
                _box_polygon(surface)
            )
        )
        rows.append(
            '<text x="{:.3f}" y="{:.3f}" font-size="0.28" text-anchor="middle">{}</text>'.format(
                surface.center.x, -surface.center.y, surface.name
            )
        )
    for wall in model.wall_boxes:
        rows.append(
            '<polygon points="{}" fill="#515a66" stroke="#20262d" stroke-width="0.02"/>'.format(
                _box_polygon(wall)
            )
        )
    rows.append(
        '<polyline points="{}" fill="none" stroke="#f2b134" stroke-width="0.07" stroke-dasharray="0.18 0.10"/>'.format(
            _centreline_svg_points(model)
        )
    )
    for pose in model.takeoff_poses:
        rows.append(
            '<circle cx="{:.3f}" cy="{:.3f}" r="0.18" fill="#2780c2"/><text x="{:.3f}" y="{:.3f}" font-size="0.25">{}</text>'.format(
                pose.position.x,
                -pose.position.y,
                pose.position.x + 0.25,
                -pose.position.y,
                pose.name,
            )
        )
    for platform in model.landing_platforms:
        rows.append(
            '<polygon points="{}" fill="#f1d86a" stroke="#7e6710" stroke-width="0.04"/><text x="{:.3f}" y="{:.3f}" font-size="0.22" text-anchor="middle">{}</text>'.format(
                _box_polygon(platform), platform.center.x, -platform.center.y, platform.name
            )
        )
    rows.extend(
        [
            '<line x1="-2.5" y1="2.3" x2="-1.5" y2="2.3" stroke="#d33" stroke-width="0.06"/>',
            '<text x="-1.4" y="2.38" font-size="0.23">+X East</text>',
            '<line x1="-2.5" y1="2.3" x2="-2.5" y2="1.3" stroke="#2a7" stroke-width="0.06"/>',
            '<text x="-2.4" y="1.25" font-size="0.23">+Y North</text>',
            '<text x="0" y="-7.35" font-size="0.28">centreline {:.6f} m | width min {:.1f} m | radius max {:.1f} m</text>'.format(
                report["centreline_length_m"],
                report["minimum_clear_width_m"],
                report["maximum_turn_radius_m"],
            ),
            '<text x="0" y="-7.72" font-size="0.20">spec_sha256 {}</text>'.format(
                model.spec_sha256
            ),
            "</svg>",
        ]
    )
    return "\n".join(rows) + "\n"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_artifacts(spec_path: Path, output_dir: Path) -> Dict[str, object]:
    model = load_course(Path(spec_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = course_report(model)
    points = sample_surface_points(model, 0.1)
    terrain = model.raw["terrain"]
    base_map = model.base_map

    _write_json(
        output_dir / "planning_points.json",
        {
            "frame_id": "world",
            "points": points,
            "spacing_m": 0.1,
            "spec_sha256": model.spec_sha256,
        },
    )
    _write_json(output_dir / "validation_report.json", report)
    (output_dir / "course_preview.svg").write_text(_svg(model, report), encoding="utf-8")
    write_flat_png16(
        output_dir / "{}.png".format(base_map),
        int(terrain["pixels"][0]),
        int(terrain["pixels"][1]),
        int(terrain["height_raw"]),
    )
    bounds = terrain["bounds"]
    terrain_text = "{},{},0,{},{},0,0,0,0\n".format(
        int(round(bounds[1] * 100.0)),
        int(round(bounds[3] * 100.0)),
        int(round(bounds[0] * 100.0)),
        int(round(bounds[2] * 100.0)),
    )
    (output_dir / "{}.txt".format(base_map)).write_text(terrain_text, encoding="ascii")

    names = [
        "{}.png".format(base_map),
        "{}.txt".format(base_map),
        "course_preview.svg",
        "planning_points.json",
        "validation_report.json",
    ]
    return {
        "artifacts": {name: _sha256(output_dir / name) for name in names},
        "spec_sha256": model.spec_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = generate_artifacts(args.spec, args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
