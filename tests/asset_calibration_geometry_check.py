#!/usr/bin/env python3
"""Contract checks for official-asset calibration station geometry."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import sys
import tempfile
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect_geometry_invalid(catalog_module, geometry, raw, mutate, fragment):
    candidate = copy.deepcopy(raw)
    mutate(candidate)
    with tempfile.TemporaryDirectory(prefix="asset_geometry_invalid_") as temp_dir:
        path = Path(temp_dir) / "catalog.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        catalog = catalog_module.load_catalog(path)
        try:
            geometry.validate_station_layout(catalog)
        except geometry.CalibrationGeometryError as exc:
            assert fragment in str(exc), str(exc)
        else:
            raise AssertionError("expected geometry error containing {!r}".format(fragment))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-module", type=Path, required=True)
    parser.add_argument("--geometry-module", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    catalog_module = load_module("asset_catalog", args.catalog_module)
    geometry = load_module("calibration_geometry", args.geometry_module)
    catalog = catalog_module.load_catalog(args.catalog)

    assert geometry.enu_to_ned(catalog_module.Vec3(3, 4, 2)) == catalog_module.Vec3(4, 3, -2)
    assert geometry.ned_to_enu(catalog_module.Vec3(4, 3, -2)) == catalog_module.Vec3(3, 4, 2)
    assert math.isclose(geometry.yaw_enu_to_ned(0), math.pi / 2)
    report = geometry.validate_station_layout(catalog)
    assert report["valid"] is True
    assert report["station_count"] == 10
    assert report["minimum_station_clearance_m"] >= 0.75

    raw = json.loads(args.catalog.read_text(encoding="utf-8"))
    expect_geometry_invalid(
        catalog_module, geometry, raw,
        lambda data: data["assets"][1]["station"].__setitem__("position", data["assets"][0]["station"]["position"]),
        "pillar_813 overlaps box_815",
    )
    expect_geometry_invalid(
        catalog_module, geometry, raw,
        lambda data: data["assets"][0].__setitem__("declared_bounds", [5, 1, 2]),
        "pillar_813 leaves calibration zone",
    )
    expect_geometry_invalid(
        catalog_module, geometry, raw,
        lambda data: data["assets"][0]["station"].__setitem__("position", [42, -4, 0.5]),
        "pillar_813 crosses placement plane",
    )
    print("asset calibration geometry: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
