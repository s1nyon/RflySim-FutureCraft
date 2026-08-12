#!/usr/bin/env python3
"""Pure near-field showcase specification and geometry."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from asset_catalog import CalibrationCatalog, Vec3


class ShowcaseValidationError(ValueError):
    pass


EXPECTED_STATIONS = (
    ("pillar_813", (11.0, -5.0, 0.0)), ("box_815", (11.0, -2.5, 0.0)),
    ("box_818", (11.0, 0.0, 0.0)), ("carton_500", (11.0, 2.5, 0.0)),
    ("carton_750", (11.0, 5.0, 0.0)), ("carton_1000", (13.0, -5.0, 0.0)),
    ("ring_target_150", (13.0, -2.5, 0.0)), ("quad_target_151", (13.0, 0.0, 0.0)),
    ("aruco_custom_43", (13.0, 2.5, 0.0)), ("luminous_light_60", (13.0, 5.0, 0.0)),
)


@dataclass(frozen=True)
class ShowcaseStation:
    key: str
    position_enu: Vec3
    measured_dimensions: Vec3


@dataclass(frozen=True)
class ShowcaseSpec:
    target_longest_edge_m: float
    pillar_target_height_m: float
    scale_clamp: Tuple[float, float]
    spawn_centers: Tuple[Tuple[float, float], ...]
    spawn_exclusion_radius_m: float
    stations: Tuple[ShowcaseStation, ...]


@dataclass(frozen=True)
class ShowcasePlacement:
    key: str
    object_id: int
    class_id: int
    position_enu: Vec3
    yaw_enu_rad: float
    scale: Vec3
    measured_dimensions: Vec3
    expected_dimensions: Vec3


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ShowcaseValidationError("{} must be finite numeric".format(label))
    return float(value)


def _vec3(value, label, positive=False):
    if not isinstance(value, list) or len(value) != 3:
        raise ShowcaseValidationError("{} must contain three values".format(label))
    result = Vec3(*(_number(item, label) for item in value))
    if positive and min(result) <= 0:
        raise ShowcaseValidationError("{} must be positive".format(label))
    return result


def load_showcase(path: Path) -> ShowcaseSpec:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or raw.get("frame") != "ENU":
        raise ShowcaseValidationError("showcase schema/frame must be v1 ENU")
    clamp = tuple(_number(item, "scale_clamp") for item in raw.get("scale_clamp", []))
    if len(clamp) != 2 or clamp[0] <= 0 or clamp[0] > clamp[1]:
        raise ShowcaseValidationError("scale_clamp is invalid")
    stations = tuple(
        ShowcaseStation(
            key=str(item.get("key", "")).strip(),
            position_enu=_vec3(item.get("position"), "station position"),
            measured_dimensions=_vec3(item.get("measured_dimensions"), "measured_dimensions", True),
        )
        for item in raw.get("stations", [])
    )
    if len(stations) != 10 or any(not item.key for item in stations) or len({item.key for item in stations}) != 10:
        raise ShowcaseValidationError("showcase requires ten unique keyed stations")
    if tuple((item.key, tuple(item.position_enu)) for item in stations) != EXPECTED_STATIONS:
        raise ShowcaseValidationError("showcase stations must match the approved two-row grid")
    centers = tuple(tuple(_number(value, "spawn center") for value in item) for item in raw.get("spawn_centers", []))
    if any(len(item) != 2 for item in centers):
        raise ShowcaseValidationError("spawn centers must be 2D")
    return ShowcaseSpec(
        target_longest_edge_m=_number(raw.get("target_longest_edge_m"), "target_longest_edge_m"),
        pillar_target_height_m=_number(raw.get("pillar_target_height_m"), "pillar_target_height_m"),
        scale_clamp=clamp,
        spawn_centers=centers,
        spawn_exclusion_radius_m=_number(raw.get("spawn_exclusion_radius_m"), "spawn_exclusion_radius_m"),
        stations=stations,
    )


def resolve_showcase(spec: ShowcaseSpec, catalog: CalibrationCatalog) -> Tuple[ShowcasePlacement, ...]:
    assets = {item.key: item for item in catalog.assets}
    placements = []
    for station in spec.stations:
        if station.key not in assets:
            raise ShowcaseValidationError("unknown showcase asset {}".format(station.key))
        asset = assets[station.key]
        measured_edge = station.measured_dimensions.z if station.key == "pillar_813" else max(station.measured_dimensions)
        target = spec.pillar_target_height_m if station.key == "pillar_813" else spec.target_longest_edge_m
        uniform = min(max(target / measured_edge, spec.scale_clamp[0]), spec.scale_clamp[1])
        scale = Vec3(uniform, uniform, uniform)
        expected = Vec3(*(value * uniform for value in station.measured_dimensions))
        placements.append(ShowcasePlacement(station.key, asset.object_id, asset.class_id, station.position_enu, 0.0, scale, station.measured_dimensions, expected))
    if [item.object_id for item in placements] != list(range(13000, 13010)):
        raise ShowcaseValidationError("showcase IDs must be exactly 13000..13009")
    return tuple(placements)


def validate_showcase(placements, spawn_centers, exclusion_radius_m):
    spawn_distances = [
        math.hypot(item.position_enu.x - center[0], item.position_enu.y - center[1])
        for item in placements for center in spawn_centers
    ]
    if min(spawn_distances) < exclusion_radius_m:
        raise ShowcaseValidationError("showcase enters spawn exclusion")
    for index, first in enumerate(placements):
        for second in placements[index + 1:]:
            center_distance = math.hypot(first.position_enu.x - second.position_enu.x, first.position_enu.y - second.position_enu.y)
            first_radius = math.hypot(first.expected_dimensions.x, first.expected_dimensions.y) / 2.0
            second_radius = math.hypot(second.expected_dimensions.x, second.expected_dimensions.y) / 2.0
            if center_distance <= first_radius + second_radius:
                raise ShowcaseValidationError("showcase stations overlap")
    return {"valid": True, "station_count": len(placements), "minimum_spawn_center_distance_m": min(spawn_distances)}
