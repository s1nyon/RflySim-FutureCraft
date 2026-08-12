#!/usr/bin/env python3
"""Contract checks for the official-asset calibration catalog."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("asset_catalog", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from {}".format(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_invalid(module, source, mutate, fragment):
    candidate = copy.deepcopy(source)
    mutate(candidate)
    with tempfile.TemporaryDirectory(prefix="asset_catalog_invalid_") as temp_dir:
        path = Path(temp_dir) / "catalog.json"
        path.write_text(json.dumps(candidate, allow_nan=True), encoding="utf-8")
        try:
            module.load_catalog(path)
        except module.CatalogValidationError as exc:
            assert fragment in str(exc), str(exc)
        else:
            raise AssertionError("expected invalid catalog containing {!r}".format(fragment))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()

    module = load_module(args.module)
    catalog = module.load_catalog(args.catalog)
    assert catalog.schema_version == 1
    assert catalog.frame == "ENU"
    assert catalog.units == "m"
    assert catalog.owned_id_range == (13000, 13099)
    assert catalog.sha256 == module.catalog_sha256(args.catalog)
    with tempfile.TemporaryDirectory(prefix="asset_catalog_hash_") as temp_dir:
        raw = json.loads(args.catalog.read_text(encoding="utf-8"))
        canonical = json.dumps(raw, ensure_ascii=False, indent=2)
        lf_path = Path(temp_dir) / "lf.json"
        crlf_path = Path(temp_dir) / "crlf.json"
        lf_path.write_bytes((canonical + "\n").encode("utf-8"))
        crlf_path.write_bytes((canonical.replace("\n", "\r\n") + "\r\n").encode("utf-8"))
        assert module.catalog_sha256(lf_path) == module.catalog_sha256(crlf_path)
    assert [asset.key for asset in catalog.assets] == [
        "pillar_813",
        "box_815",
        "box_818",
        "carton_500",
        "carton_750",
        "carton_1000",
        "ring_target_150",
        "quad_target_151",
        "aruco_custom_43",
        "luminous_light_60",
    ]
    assert [asset.class_id for asset in catalog.assets[3:6]] == [500, 750, 1000]
    assert len({asset.object_id for asset in catalog.assets}) == len(catalog.assets)
    assert all(13000 <= asset.object_id <= 13099 for asset in catalog.assets)
    assert all(module.profile_id(asset).startswith(asset.key + "@") for asset in catalog.assets)

    raw = json.loads(args.catalog.read_text(encoding="utf-8"))
    expect_invalid(module, raw, lambda data: data.__setitem__("schema_version", 2), "schema_version")
    expect_invalid(module, raw, lambda data: data["assets"][1].__setitem__("key", data["assets"][0]["key"]), "duplicate asset key")
    expect_invalid(module, raw, lambda data: data["assets"][1].__setitem__("object_id", data["assets"][0]["object_id"]), "duplicate object_id")
    expect_invalid(module, raw, lambda data: data["assets"][0].__setitem__("object_id", 12999), "owned range")
    expect_invalid(module, raw, lambda data: data["assets"][0]["station"].__setitem__("position", [float("nan"), 0, 1]), "finite")
    expect_invalid(module, raw, lambda data: data["assets"][0].__setitem__("scale", [0, 1, 1]), "scale")
    expect_invalid(module, raw, lambda data: data["assets"][0].__setitem__("declared_bounds", [1, -1, 1]), "declared_bounds")
    expect_invalid(module, raw, lambda data: data["assets"][0].__setitem__("intended_roles", ["air_racing"]), "unknown role")
    expect_invalid(module, raw, lambda data: data["assets"][0].__setitem__("official_source", ""), "official_source")
    expect_invalid(module, raw, lambda data: data["assets"][0]["station"].__setitem__("position", [100, 0, 1]), "calibration zone")
    expect_invalid(module, raw, lambda data: data["assets"][0].__setitem__("class_id", True), "class_id")
    expect_invalid(module, raw, lambda data: data.__setitem__("station_clearance_m", 0), "station_clearance_m")

    print("asset calibration catalog: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
