#!/usr/bin/env python3
"""Determinism checks for Competition Course V2 generated artifacts."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


def tree_hashes(root):
    return {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_artifacts import generate_artifacts  # pylint: disable=import-error

    with tempfile.TemporaryDirectory() as temp:
        first, second = Path(temp) / "first", Path(temp) / "second"
        manifest1 = generate_artifacts(root / "config/maps/competition_course_v2.json", first)
        manifest2 = generate_artifacts(root / "config/maps/competition_course_v2.json", second)
        assert manifest1 == manifest2
        assert tree_hashes(first) == tree_hashes(second)
        expected = {
            "SLAMScene.png", "SLAMScene.txt", "course_preview.svg", "entity_manifest.json",
            "planning_points.json", "evaluation_reference.json", "validation_report.json",
            "aruco/marker_31.png", "aruco/marker_47.png",
        }
        assert expected <= set(tree_hashes(first))
        entities = json.loads((first / "entity_manifest.json").read_text(encoding="utf-8"))
        ids = [item["id"] for item in entities["entities"]]
        assert len(ids) == len(set(ids))
        assert entities["spec_sha256"] == manifest1["spec_sha256"]
        report = json.loads((first / "validation_report.json").read_text(encoding="utf-8"))
        assert report["result"] == "PASS"
        assert report["static_obstacle_count"] == 2
        assert report["aruco_marker_ids"] == [31, 47]
        for marker_id in (31, 47):
            png = first / "aruco/marker_{}.png".format(marker_id)
            assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            assert png.stat().st_size > 100
        for path in first.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".svg", ".txt"}:
                text = path.read_text(encoding="utf-8")
                assert str(root) not in text
                assert "generated_at" not in text
    print("competition_course_v2_artifacts_check: PASS")


if __name__ == "__main__":
    main()
