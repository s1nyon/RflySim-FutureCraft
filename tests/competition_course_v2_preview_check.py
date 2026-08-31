#!/usr/bin/env python3
"""Semantic and dimensional contract for the generated course preview."""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    script_dir = root / "future_aircraft_ws/src/multi_uav_mission/scripts"
    sys.path.insert(0, str(script_dir))
    from competition_course_artifacts import build_preview_svg
    from competition_course_geometry import (
        build_entity_manifest,
        load_spec,
        pendulum_clearance_report,
        spawn_clearance_report,
        static_clearance_reports,
        turn_clearance_reports,
    )

    spec = load_spec(root / "config/maps/competition_course_v2.json")
    reports = {
        "static": static_clearance_reports(spec),
        "turns": turn_clearance_reports(spec),
        "spawn": spawn_clearance_report(spec),
        "pendulum": pendulum_clearance_report(spec),
    }
    svg = build_preview_svg(spec, build_entity_manifest(spec), reports)
    document = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    group_ids = {item.attrib.get("id") for item in document.findall("svg:g", namespace)}
    assert group_ids >= {
        "arena", "centerline", "walls", "spawns", "camera_axes",
        "static_obstacles", "pendulum_sweep", "task_zone", "landing",
        "dimensions", "legend",
    }
    view_x, view_y, view_width, view_height = [float(value) for value in document.attrib["viewBox"].split()]
    del view_x, view_width
    text_y = [float(item.attrib["y"]) for item in document.findall(".//svg:text", namespace)]
    assert view_y + view_height - max(text_y) >= 0.5
    dimensions = document.find("svg:g[@id='dimensions']", namespace)
    assert dimensions is not None
    assert min(float(item.attrib["y"]) for item in dimensions.findall("svg:text", namespace)) >= 7.9
    for text in (
        spec["spec_sha256"], "Section A", "Section B", "Section C",
        "static_box_a gap 1.225 m", "static_pillar_b gap 1.150 m",
        "safe window 1.858 s", "uav1 (16.000,-0.700)",
        "uav2 (16.000,0.700)", "minimum passable gap 1.000 m",
        "ArUco 31", "ArUco 47",
        "OFFLINE VISUAL REVIEW",
    ):
        assert text in svg, text
    assert 'data-coordinate-frame="ENU"' in svg
    assert 'data-shared-world="false"' in svg
    assert "x=2.000" not in svg
    assert svg.endswith("\n")
    print("competition_course_v2_preview_check: PASS")


if __name__ == "__main__":
    main()
