#!/usr/bin/env python3
"""Pure RflySim-to-Ouster PointCloud2 byte-layout conversion."""

from dataclasses import dataclass
import math
import struct
from typing import List, Tuple


FLOAT32 = 7
UINT32 = 6
UINT16 = 4
UINT8 = 2
RAW_POINT_STEP = 16
OUTPUT_POINT_STEP = 32
RAW_POINT = struct.Struct("<ffff")
OUSTER_POINT = struct.Struct("<ffffIHBxH2xI")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    offset: int
    datatype: int
    count: int = 1


@dataclass(frozen=True)
class ConvertedCloud:
    data: bytes
    fields: Tuple[FieldSpec, ...]
    point_step: int
    accepted_points: int
    time_span_sec: float


OUSTER_FIELDS = (
    FieldSpec("x", 0, FLOAT32),
    FieldSpec("y", 4, FLOAT32),
    FieldSpec("z", 8, FLOAT32),
    FieldSpec("intensity", 12, FLOAT32),
    FieldSpec("t", 16, UINT32),
    FieldSpec("reflectivity", 20, UINT16),
    FieldSpec("ring", 22, UINT8),
    FieldSpec("ambient", 24, UINT16),
    FieldSpec("range", 28, UINT32),
)

RAW_FIELDS = {
    "x": (0, FLOAT32, 1),
    "y": (4, FLOAT32, 1),
    "z": (8, FLOAT32, 1),
    "seg": (12, FLOAT32, 1),
}


def _validate_fields(fields: List[dict]) -> None:
    by_name = {field.get("name"): field for field in fields}
    for name, expected in RAW_FIELDS.items():
        if name not in by_name:
            raise ValueError(f"missing raw cloud field: {name}")
        field = by_name[name]
        actual = (field.get("offset"), field.get("datatype"), field.get("count"))
        if actual != expected:
            raise ValueError(f"invalid raw cloud field {name}: expected {expected}, got {actual}")


def convert_cloud(
    data: bytes,
    fields: List[dict],
    width: int,
    height: int,
    point_step: int,
    layout_width: int,
    layout_height: int,
    scan_period_sec: float,
) -> ConvertedCloud:
    """Convert one valid, possibly sparse RflySim scan to faster_lio's Ouster layout."""
    if point_step != RAW_POINT_STEP:
        raise ValueError(f"point_step must be {RAW_POINT_STEP}, got {point_step}")
    _validate_fields(fields)
    if width <= 0 or height <= 0 or layout_width <= 0 or layout_height <= 0:
        raise ValueError("cloud and configured layout dimensions must be positive")
    point_count = width * height
    if len(data) != point_count * point_step:
        raise ValueError("data length does not match cloud point count")
    if point_count > layout_width * layout_height:
        raise ValueError("point count exceeds configured scan capacity")
    if layout_width > 256:
        raise ValueError("layout width exceeds uint8 ring capacity")
    if not math.isfinite(scan_period_sec) or scan_period_sec <= 0.0:
        raise ValueError("scan period must be finite and positive")
    if scan_period_sec * 1_000_000_000.0 > 0xFFFFFFFF:
        raise ValueError("scan period exceeds uint32 nanosecond capacity")

    converted = bytearray(point_count * OUTPUT_POINT_STEP)
    divisor = max(point_count - 1, 1)
    for index in range(point_count):
        x, y, z, seg = RAW_POINT.unpack_from(data, index * point_step)
        if not all(math.isfinite(value) for value in (x, y, z, seg)):
            raise ValueError(f"point {index} values must be finite")
        intensity = max(0.0, float(seg))
        t_ns = round(scan_period_sec * index / divisor * 1_000_000_000.0)
        reflectivity = min(65535, round(intensity))
        ring = index % layout_width
        range_mm = round(math.sqrt(x * x + y * y + z * z) * 1000.0)
        if range_mm > 0xFFFFFFFF:
            raise ValueError(f"point {index} range exceeds uint32 millimetre capacity")
        OUSTER_POINT.pack_into(
            converted,
            index * OUTPUT_POINT_STEP,
            x,
            y,
            z,
            intensity,
            t_ns,
            reflectivity,
            ring,
            0,
            range_mm,
        )

    return ConvertedCloud(
        data=bytes(converted),
        fields=OUSTER_FIELDS,
        point_step=OUTPUT_POINT_STEP,
        accepted_points=point_count,
        time_span_sec=scan_period_sec,
    )
