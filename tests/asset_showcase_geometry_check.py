#!/usr/bin/env python3
"""Contracts for near-field official-asset showcase geometry."""

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-module", type=Path, required=True)
    parser.add_argument("--showcase-module", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--showcase", type=Path, required=True)
    args = parser.parse_args()
    catalog_module = load("asset_catalog", args.catalog_module)
    showcase = load("showcase_geometry", args.showcase_module)
    catalog = catalog_module.load_catalog(args.catalog)
    spec = showcase.load_showcase(args.showcase)
    placements = showcase.resolve_showcase(spec, catalog)
    assert [item.object_id for item in placements] == list(range(13000, 13010))
    assert [(item.position_enu.x, item.position_enu.y) for item in placements] == [
        (11.0, -5.0), (11.0, -2.5), (11.0, 0.0), (11.0, 2.5), (11.0, 5.0),
        (13.0, -5.0), (13.0, -2.5), (13.0, 0.0), (13.0, 2.5), (13.0, 5.0),
    ]
    for item in placements:
        assert item.scale.x == item.scale.y == item.scale.z
        assert 0.02 <= item.scale.x <= 2.0
        target = 1.5 if item.key == "pillar_813" else 1.2
        measured_edge = item.measured_dimensions.z if item.key == "pillar_813" else max(item.measured_dimensions)
        assert abs(measured_edge * item.scale.x - target) < 1e-6 or item.scale.x in (0.02, 2.0)
    report = showcase.validate_showcase(placements, spec.spawn_centers, spec.spawn_exclusion_radius_m)
    assert report["valid"] is True
    assert report["station_count"] == 10
    assert report["minimum_spawn_center_distance_m"] >= 3.0
    raw = json.loads(args.showcase.read_text(encoding="utf-8"))
    raw["stations"][0]["position"] = [11.1, -5.0, 0.0]
    with tempfile.TemporaryDirectory() as temp_dir:
        changed = Path(temp_dir) / "changed.json"
        changed.write_text(json.dumps(raw), encoding="utf-8")
        try:
            showcase.load_showcase(changed)
            raise AssertionError("changed station grid accepted")
        except showcase.ShowcaseValidationError:
            pass
    print("asset showcase geometry: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
