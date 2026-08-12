#!/usr/bin/env python3
"""Pure schema and validation for official-asset calibration catalogs."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple


ALLOWED_ROLES = frozenset(
    ("static_obstacle", "dynamic_obstacle", "color_target", "image_target", "temperature_proxy")
)


class CatalogValidationError(ValueError):
    """Raised when an asset catalog violates its public contract."""


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __iter__(self):
        return iter((self.x, self.y, self.z))


@dataclass(frozen=True)
class AssetCandidate:
    key: str
    object_id: int
    class_id: int
    official_source: str
    variant: str
    intended_roles: Tuple[str, ...]
    position_enu: Vec3
    yaw_enu_rad: float
    scale: Vec3
    declared_bounds: Vec3


@dataclass(frozen=True)
class CalibrationCatalog:
    schema_version: int
    catalog_name: str
    frame: str
    units: str
    base_map: str
    owned_id_range: Tuple[int, int]
    zone_bounds: Tuple[float, float, float, float]
    placement_z: float
    station_clearance_m: float
    assets: Tuple[AssetCandidate, ...]
    sha256: str


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogValidationError("{} must be a finite number".format(label))
    result = float(value)
    if not math.isfinite(result):
        raise CatalogValidationError("{} must be finite".format(label))
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CatalogValidationError("{} must be an integer".format(label))
    return value


def _vec3(value: Any, label: str, positive: bool = False) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise CatalogValidationError("{} must contain three values".format(label))
    result = Vec3(*(_number(item, label) for item in value))
    if positive and min(result) <= 0.0:
        raise CatalogValidationError("{} must be positive".format(label))
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError("{} must be a non-empty string".format(label))
    return value.strip()


def catalog_sha256(path: Path) -> str:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogValidationError("cannot hash catalog {}: {}".format(path, exc)) from exc
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def profile_id(candidate: AssetCandidate) -> str:
    scale = "x".join("{:g}".format(value) for value in candidate.scale)
    return "{}@class{}@scale{}".format(candidate.key, candidate.class_id, scale)


def _parse_asset(raw: Dict[str, Any], owned_range: Tuple[int, int], zone: Sequence[float]) -> AssetCandidate:
    key = _text(raw.get("key"), "asset key")
    object_id = _integer(raw.get("object_id"), "object_id")
    if not owned_range[0] <= object_id <= owned_range[1]:
        raise CatalogValidationError("{} object_id is outside owned range".format(key))
    class_id = _integer(raw.get("class_id"), "class_id")
    if class_id <= 0:
        raise CatalogValidationError("class_id must be positive")
    source = _text(raw.get("official_source"), "official_source")
    variant = _text(raw.get("variant"), "variant")
    roles_raw = raw.get("intended_roles")
    if not isinstance(roles_raw, list) or not roles_raw:
        raise CatalogValidationError("{} intended_roles must be non-empty".format(key))
    roles = tuple(_text(role, "role") for role in roles_raw)
    unknown = sorted(set(roles) - ALLOWED_ROLES)
    if unknown:
        raise CatalogValidationError("unknown role: {}".format(unknown[0]))
    station = raw.get("station")
    if not isinstance(station, dict):
        raise CatalogValidationError("{} station must be an object".format(key))
    position = _vec3(station.get("position"), "station position")
    if not (zone[0] <= position.x <= zone[1] and zone[2] <= position.y <= zone[3]):
        raise CatalogValidationError("{} station is outside calibration zone".format(key))
    return AssetCandidate(
        key=key,
        object_id=object_id,
        class_id=class_id,
        official_source=source,
        variant=variant,
        intended_roles=roles,
        position_enu=position,
        yaw_enu_rad=_number(station.get("yaw_rad"), "station yaw_rad"),
        scale=_vec3(raw.get("scale"), "scale", positive=True),
        declared_bounds=_vec3(raw.get("declared_bounds"), "declared_bounds", positive=True),
    )


def load_catalog(path: Path) -> CalibrationCatalog:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogValidationError("cannot read catalog {}: {}".format(path, exc)) from exc
    if not isinstance(raw, dict):
        raise CatalogValidationError("catalog root must be an object")
    schema_version = _integer(raw.get("schema_version"), "schema_version")
    if schema_version != 1:
        raise CatalogValidationError("unsupported schema_version")
    frame = _text(raw.get("frame"), "frame")
    units = _text(raw.get("units"), "units")
    if frame != "ENU" or units != "m":
        raise CatalogValidationError("catalog frame/units must be ENU metres")
    id_raw = raw.get("owned_id_range")
    if not isinstance(id_raw, list) or len(id_raw) != 2:
        raise CatalogValidationError("owned_id_range must contain two integers")
    owned_range = (_integer(id_raw[0], "owned range"), _integer(id_raw[1], "owned range"))
    if owned_range[0] > owned_range[1]:
        raise CatalogValidationError("owned range is reversed")
    zone_raw = raw.get("calibration_zone")
    if not isinstance(zone_raw, dict):
        raise CatalogValidationError("calibration_zone must be an object")
    bounds_raw = zone_raw.get("bounds")
    if not isinstance(bounds_raw, list) or len(bounds_raw) != 4:
        raise CatalogValidationError("calibration zone bounds must contain four values")
    bounds = tuple(_number(item, "calibration zone bounds") for item in bounds_raw)
    if bounds[0] >= bounds[1] or bounds[2] >= bounds[3]:
        raise CatalogValidationError("calibration zone bounds are invalid")
    assets_raw = raw.get("assets")
    if not isinstance(assets_raw, list) or not assets_raw:
        raise CatalogValidationError("assets must be a non-empty list")
    assets = tuple(_parse_asset(item, owned_range, bounds) for item in assets_raw)
    keys = [asset.key for asset in assets]
    if len(set(keys)) != len(keys):
        raise CatalogValidationError("duplicate asset key")
    ids = [asset.object_id for asset in assets]
    if len(set(ids)) != len(ids):
        raise CatalogValidationError("duplicate object_id")
    station_clearance_m = _number(raw.get("station_clearance_m"), "station_clearance_m")
    if station_clearance_m <= 0.0:
        raise CatalogValidationError("station_clearance_m must be positive")
    return CalibrationCatalog(
        schema_version=schema_version,
        catalog_name=_text(raw.get("catalog_name"), "catalog_name"),
        frame=frame,
        units=units,
        base_map=_text(raw.get("base_map"), "base_map"),
        owned_id_range=owned_range,
        zone_bounds=bounds,
        placement_z=_number(zone_raw.get("placement_z"), "placement_z"),
        station_clearance_m=station_clearance_m,
        assets=assets,
        sha256=catalog_sha256(path),
    )
