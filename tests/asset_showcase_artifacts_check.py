#!/usr/bin/env python3
"""Determinism contract for near-field showcase artifacts."""

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module; spec.loader.exec_module(module); return module


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,required=True); args=parser.parse_args()
    cal=load("asset_catalog",args.root/"scripts/calibration/asset_catalog.py")
    geo=load("showcase_geometry",args.root/"scripts/calibration/showcase_geometry.py")
    art=load("showcase_artifacts",args.root/"scripts/calibration/showcase_artifacts.py")
    catalog=cal.load_catalog(args.root/"config/calibration/official_asset_candidates_v1.json")
    spec=geo.load_showcase(args.root/"config/calibration/official_asset_showcase_v1.json")
    placements=geo.resolve_showcase(spec,catalog); report=geo.validate_showcase(placements,spec.spawn_centers,spec.spawn_exclusion_radius_m)
    with tempfile.TemporaryDirectory() as temp:
        a=Path(temp)/"a"; b=Path(temp)/"b"; art.generate_showcase_artifacts(a,placements,report); art.generate_showcase_artifacts(b,placements,report)
        assert sorted(p.name for p in a.iterdir()) == sorted(p.name for p in b.iterdir())
        assert all(p.read_bytes()==(b/p.name).read_bytes() for p in a.iterdir())
    print("asset showcase artifacts: PASS"); return 0


if __name__ == "__main__": raise SystemExit(main())
