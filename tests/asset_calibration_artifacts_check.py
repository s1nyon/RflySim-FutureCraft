#!/usr/bin/env python3
"""Contract checks for deterministic asset-calibration artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-module", type=Path, required=True)
    parser.add_argument("--geometry-module", type=Path, required=True)
    parser.add_argument("--artifact-module", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    catalog_module = load_module("asset_catalog", args.catalog_module)
    load_module("calibration_geometry", args.geometry_module)
    artifacts = load_module("calibration_artifacts", args.artifact_module)

    with tempfile.TemporaryDirectory(prefix="asset_artifacts_a_") as a, tempfile.TemporaryDirectory(prefix="asset_artifacts_b_") as b:
        output_a, output_b = Path(a), Path(b)
        manifest_a = artifacts.generate_artifacts(args.catalog, output_a)
        manifest_b = artifacts.generate_artifacts(args.catalog, output_b)
        expected = [
            "artifact_manifest.json",
            "calibration_preview.svg",
            "declared_profiles.json",
            "resolved_scene.json",
            "validation_report.json",
        ]
        assert sorted(path.name for path in output_a.iterdir()) == expected
        assert manifest_a == manifest_b
        for name in expected:
            assert (output_a / name).read_bytes() == (output_b / name).read_bytes(), name

        catalog = catalog_module.load_catalog(args.catalog)
        profiles = json.loads((output_a / "declared_profiles.json").read_text(encoding="utf-8"))
        assert len(profiles["profiles"]) == 10
        for profile, candidate in zip(profiles["profiles"], catalog.assets):
            assert profile["profile_id"] == catalog_module.profile_id(candidate)
            assert profile["evidence_state"] == "DECLARED"
            assert profile["approved_roles"] == []
            assert profile["measurements"] == {}
            assert profile["catalog_sha256"] == catalog.sha256
            assert profile["official_source"] == candidate.official_source
        forbidden = ("LIDAR_MEASURED", "RGB_MEASURED", "ROLE_APPROVED", '"live"', '"collision": true')
        profiles_text = (output_a / "declared_profiles.json").read_text(encoding="utf-8")
        assert all(token not in profiles_text for token in forbidden)

        scene = json.loads((output_a / "resolved_scene.json").read_text(encoding="utf-8"))
        assert scene["map_change"] is False
        assert scene["arming_request"] is False
        assert [item["object_id"] for item in scene["assets"]] == list(range(13000, 13010))
        report = json.loads((output_a / "validation_report.json").read_text(encoding="utf-8"))
        assert report["valid"] is True and report["station_count"] == 10
        svg = (output_a / "calibration_preview.svg").read_text(encoding="utf-8")
        for token in [asset.key for asset in catalog.assets] + [catalog.sha256, "+X East", "+Y North", "1 m grid"]:
            assert token in svg, token
        manifest = json.loads((output_a / "artifact_manifest.json").read_text(encoding="utf-8"))
        assert manifest["catalog_sha256"] == catalog.sha256
        assert sorted(manifest["artifacts"]) == sorted(set(expected) - {"artifact_manifest.json"})

    print("asset calibration artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
