#!/usr/bin/env python3
"""Contract checks for deterministic Stage 8 course artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path


def load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from {}".format(module_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def decode_png16(path: Path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0]
        assert zlib.crc32(chunk_type + payload) & 0xFFFFFFFF == crc
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
        offset += 12 + length
    assert bit_depth == 16 and color_type == 0
    raw = zlib.decompress(bytes(compressed))
    row_size = 1 + width * 2
    assert len(raw) == height * row_size
    samples = []
    for row_index in range(height):
        row = raw[row_index * row_size : (row_index + 1) * row_size]
        assert row[0] == 0
        samples.extend(struct.unpack(">{}H".format(width), row[1:]))
    return width, height, samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-module", type=Path, required=True)
    parser.add_argument("--artifact-module", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--cloud-module", type=Path)
    parser.add_argument("--launch", type=Path)
    args = parser.parse_args()

    geometry = load_module("narrow_course_geometry", args.geometry_module)
    artifacts = load_module("narrow_course_artifacts", args.artifact_module)

    with tempfile.TemporaryDirectory(prefix="stage8_artifacts_a_") as temp_a, tempfile.TemporaryDirectory(
        prefix="stage8_artifacts_b_"
    ) as temp_b:
        output_a = Path(temp_a)
        output_b = Path(temp_b)
        manifest_a = artifacts.generate_artifacts(args.spec, output_a)
        manifest_b = artifacts.generate_artifacts(args.spec, output_b)

        expected_names = [
            "SLAMScene.png",
            "SLAMScene.txt",
            "course_preview.svg",
            "planning_points.json",
            "validation_report.json",
        ]
        assert sorted(path.name for path in output_a.iterdir()) == expected_names
        assert manifest_a == manifest_b
        for name in expected_names:
            assert (output_a / name).read_bytes() == (output_b / name).read_bytes(), name

        report = json.loads((output_a / "validation_report.json").read_text(encoding="utf-8"))
        assert manifest_a["spec_sha256"] == report["spec_sha256"]
        assert report["centreline_length_m"] == 14.927433
        assert report["minimum_clear_width_m"] == 1.4
        assert report["maximum_turn_radius_m"] == 0.9
        assert report["takeoff_separation_m"] == 1.4
        assert report["platform_spacing_m"] == 2.0

        points_doc = json.loads((output_a / "planning_points.json").read_text(encoding="utf-8"))
        assert points_doc["frame_id"] == "world"
        assert points_doc["spacing_m"] == 0.1
        assert len(points_doc["points"]) > 1000
        assert points_doc["points"] == sorted(points_doc["points"])
        assert all(len(point) == 3 for point in points_doc["points"])

        png = (output_a / "SLAMScene.png").read_bytes()
        assert png[24] == 16 and png[25] == 0
        width, height, samples = decode_png16(output_a / "SLAMScene.png")
        assert (width, height) == (801, 501)
        assert len(samples) == 801 * 501
        assert set(samples) == {32768}
        assert (output_a / "SLAMScene.txt").read_text(encoding="ascii").strip() == (
            "5500,2500,0,-2500,-2500,0,0,0,0"
        )

        svg = (output_a / "course_preview.svg").read_text(encoding="utf-8")
        for marker in (
            "uav1",
            "uav2",
            "platform1",
            "platform2",
            "takeoff_surface",
            "landing_surface",
            "14.927433 m",
            "spec_sha256",
            manifest_a["spec_sha256"],
            "+X East",
            "+Y North",
        ):
            assert marker in svg, marker

    if args.cloud_module is not None:
        assert args.launch is not None
        cloud = load_module("narrow_course_cloud_server", args.cloud_module)
        payload = cloud.pack_xyz32([(1.0, 2.0, 3.0), (-1.0, 0.5, 4.0)])
        assert len(payload) == 24
        assert struct.unpack("<ffffff", payload) == (
            1.0,
            2.0,
            3.0,
            -1.0,
            0.5,
            4.0,
        )
        launch_text = args.launch.read_text(encoding="utf-8")
        assert "/uav1" not in launch_text and "/uav2" not in launch_text
        for name in ("spec", "topic", "frame_id", "spacing_m"):
            assert 'name="{}"'.format(name) in launch_text

    model = geometry.load_course(args.spec)
    direct_points = artifacts.sample_surface_points(model, 0.1)
    assert len(direct_points) > 1000
    print("stage8 course artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
