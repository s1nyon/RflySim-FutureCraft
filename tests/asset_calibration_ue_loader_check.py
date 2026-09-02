#!/usr/bin/env python3
"""Safety contracts for the heterogeneous official-asset loader."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self):
        self.created = []
        self.destroyed = []

    def sendUE4PosScale(self, **kwargs):
        self.created.append(kwargs)

    def sendUE4Destroy(self, object_id, window_id=-1):
        self.destroyed.append((object_id, window_id))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-module", type=Path, required=True)
    parser.add_argument("--geometry-module", type=Path, required=True)
    parser.add_argument("--loader-module", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    catalog_module = load_module("asset_catalog", args.catalog_module)
    load_module("calibration_geometry", args.geometry_module)
    loader = load_module("ue_asset_loader", args.loader_module)
    catalog = catalog_module.load_catalog(args.catalog)
    commands = loader.build_commands(catalog)
    assert [item.class_id for item in commands] == [item.class_id for item in catalog.assets]
    assert [item.object_id for item in commands] == [item.object_id for item in catalog.assets]
    assert all(13000 <= item.object_id <= 13099 for item in commands)

    client = FakeClient()
    receipt = loader.place_assets(client, catalog, window_id=2, repeat=3, delay_s=0)
    assert len(client.created) == 30
    for index, command in enumerate(commands):
        calls = client.created[index * 3 : index * 3 + 3]
        assert calls[0] == calls[1] == calls[2]
        assert calls[0] == {
            "copterID": command.object_id,
            "vehicleType": command.class_id,
            "MotorRPMSMean": 0,
            "PosE": list(command.position_ned),
            "AngEuler": [0.0, 0.0, command.yaw_ned_rad],
            "Scale": list(command.scale),
            "windowID": 2,
        }
    assert receipt["mode"] == "live"
    assert receipt["map_change"] is False
    assert receipt["arming_request"] is False
    assert receipt["acted_on_ids"] == list(range(13000, 13010))

    removal = loader.remove_assets(client, catalog, window_id=2, repeat=3, delay_s=0)
    assert client.destroyed == [(object_id, 2) for object_id in range(13000, 13010) for _ in range(3)]
    assert removal["acted_on_ids"] == list(range(13000, 13010))
    assert all(object_id not in range(13010, 13100) for object_id, _ in client.destroyed)
    for invalid in (0, -1):
        try:
            loader.place_assets(FakeClient(), catalog, window_id=0, repeat=invalid)
        except ValueError as exc:
            assert "repeat" in str(exc)
        else:
            raise AssertionError("non-positive repeat accepted")
    print("asset calibration UE loader: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
