#!/usr/bin/env python3
"""Pure coordinate and station geometry for official-asset calibration."""

from __future__ import annotations

import math
from typing import Dict

from asset_catalog import CalibrationCatalog, Vec3


class CalibrationGeometryError(ValueError):
    """Raised when declared calibration stations cannot coexist safely."""


def enu_to_ned(point: Vec3) -> Vec3:
    return Vec3(point.y, point.x, -point.z)


def ned_to_enu(point: Vec3) -> Vec3:
    return Vec3(point.y, point.x, -point.z)


def yaw_enu_to_ned(yaw_rad: float) -> float:
    return math.pi / 2.0 - yaw_rad


def _edge_clearance(a, b) -> float:
    dx = abs(a.position_enu.x - b.position_enu.x) - (a.declared_bounds.x + b.declared_bounds.x) / 2.0
    dy = abs(a.position_enu.y - b.position_enu.y) - (a.declared_bounds.y + b.declared_bounds.y) / 2.0
    if dx < 0.0 and dy < 0.0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def validate_station_layout(catalog: CalibrationCatalog) -> Dict[str, object]:
    xmin, xmax, ymin, ymax = catalog.zone_bounds
    for asset in catalog.assets:
        half_x = asset.declared_bounds.x / 2.0
        half_y = asset.declared_bounds.y / 2.0
        if not (
            xmin <= asset.position_enu.x - half_x
            and asset.position_enu.x + half_x <= xmax
            and ymin <= asset.position_enu.y - half_y
            and asset.position_enu.y + half_y <= ymax
        ):
            raise CalibrationGeometryError("{} leaves calibration zone".format(asset.key))
        bottom = asset.position_enu.z - asset.declared_bounds.z / 2.0
        if bottom < catalog.placement_z - 0.01:
            raise CalibrationGeometryError("{} crosses placement plane".format(asset.key))

    clearances = []
    for index, first in enumerate(catalog.assets):
        for second in catalog.assets[index + 1 :]:
            edge = _edge_clearance(first, second)
            clearances.append(edge)
            if edge < catalog.station_clearance_m:
                raise CalibrationGeometryError("{} overlaps {} calibration clearance".format(first.key, second.key))
    return {
        "valid": True,
        "station_count": len(catalog.assets),
        "minimum_station_clearance_m": round(min(clearances), 6),
        "required_station_clearance_m": catalog.station_clearance_m,
    }
