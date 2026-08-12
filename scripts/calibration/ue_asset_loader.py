#!/usr/bin/env python3
"""Bounded official-asset placement and removal for calibration."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List

from asset_catalog import CalibrationCatalog, Vec3
from calibration_geometry import enu_to_ned, yaw_enu_to_ned


@dataclass(frozen=True)
class PlacementCommand:
    object_id: int
    class_id: int
    position_ned: Vec3
    yaw_ned_rad: float
    scale: Vec3


def build_commands(catalog: CalibrationCatalog) -> List[PlacementCommand]:
    commands = []
    for asset in catalog.assets:
        if not catalog.owned_id_range[0] <= asset.object_id <= catalog.owned_id_range[1]:
            raise ValueError("{} is outside calibration-owned range".format(asset.object_id))
        commands.append(
            PlacementCommand(
                object_id=asset.object_id,
                class_id=asset.class_id,
                position_ned=enu_to_ned(asset.position_enu),
                yaw_ned_rad=yaw_enu_to_ned(asset.yaw_enu_rad),
                scale=asset.scale,
            )
        )
    return commands


def _receipt(action: str, catalog: CalibrationCatalog, ids: List[int]) -> Dict[str, object]:
    return {
        "acted_on_ids": ids,
        "action": action,
        "arming_request": False,
        "catalog_sha256": catalog.sha256,
        "map_change": False,
        "mode": "live",
    }


def place_assets(client, catalog: CalibrationCatalog, window_id: int, repeat: int = 3, delay_s: float = 0.02) -> Dict[str, object]:
    if repeat < 1:
        raise ValueError("repeat must be positive")
    commands = build_commands(catalog)
    for command in commands:
        kwargs = {
            "copterID": command.object_id,
            "vehicleType": command.class_id,
            "MotorRPMSMean": 0,
            "PosE": list(command.position_ned),
            "AngEuler": [0.0, 0.0, command.yaw_ned_rad],
            "Scale": list(command.scale),
            "windowID": window_id,
        }
        for _attempt in range(repeat):
            client.sendUE4PosScale(**kwargs)
            if delay_s > 0.0:
                time.sleep(delay_s)
    return _receipt("load", catalog, [item.object_id for item in commands])


def remove_assets(client, catalog: CalibrationCatalog, window_id: int, repeat: int = 3, delay_s: float = 0.02) -> Dict[str, object]:
    if repeat < 1:
        raise ValueError("repeat must be positive")
    ids = [item.object_id for item in build_commands(catalog)]
    for object_id in ids:
        for _attempt in range(repeat):
            client.sendUE4Destroy(object_id, window_id)
            if delay_s > 0.0:
                time.sleep(delay_s)
    return _receipt("remove", catalog, ids)


def place_showcase(client, catalog, placements, window_id: int, repeat: int = 3, delay_s: float = 0.02):
    ids = []
    for item in placements:
        ids.append(item.object_id)
        kwargs = {
            "copterID": item.object_id,
            "vehicleType": item.class_id,
            "MotorRPMSMean": 0,
            "PosE": list(enu_to_ned(item.position_enu)),
            "AngEuler": [0.0, 0.0, yaw_enu_to_ned(item.yaw_enu_rad)],
            "Scale": list(item.scale),
            "windowID": window_id,
        }
        for _ in range(repeat):
            client.sendUE4PosScale2Ground(**kwargs)
            if delay_s > 0: time.sleep(delay_s)
    return _receipt("showcase-load", catalog, ids)


def remove_showcase(client, catalog, placements, window_id: int, repeat: int = 3, delay_s: float = 0.02):
    ids = [item.object_id for item in placements]
    for object_id in ids:
        for _ in range(repeat):
            client.sendUE4Destroy(object_id, window_id)
            if delay_s > 0: time.sleep(delay_s)
    return _receipt("showcase-remove", catalog, ids)
