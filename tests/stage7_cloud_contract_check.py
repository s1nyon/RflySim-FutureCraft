#!/usr/bin/env python3
"""Byte-level contract checks for the Stage 7 RflySim cloud adapter."""

from __future__ import annotations

import argparse
import importlib.util
import math
import struct
from pathlib import Path


RAW_FIELDS = [
    {"name": "x", "offset": 0, "datatype": 7, "count": 1},
    {"name": "y", "offset": 4, "datatype": 7, "count": 1},
    {"name": "z", "offset": 8, "datatype": 7, "count": 1},
    {"name": "seg", "offset": 12, "datatype": 7, "count": 1},
]

EXPECTED_FIELDS = [
    ("x", 0, 7, 1),
    ("y", 4, 7, 1),
    ("z", 8, 7, 1),
    ("intensity", 12, 7, 1),
    ("t", 16, 6, 1),
    ("reflectivity", 20, 4, 1),
    ("ring", 22, 2, 1),
    ("ambient", 24, 4, 1),
    ("range", 28, 6, 1),
]


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("rflysim_cloud_contract", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_value_error(action, message_fragment: str) -> None:
    try:
        action()
    except ValueError as exc:
        assert message_fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected ValueError containing {message_fragment!r}")


def converted_values(converted, format_string: str, offset: int):
    unpacker = struct.Struct(format_string)
    return [
        unpacker.unpack_from(converted.data, index * converted.point_step + offset)[0]
        for index in range(converted.accepted_points)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    args = parser.parse_args()
    module = load_module(args.module)

    points = [
        (1.0, 0.0, 0.0, 12.4),
        (0.0, 2.0, 0.0, 20.6),
        (0.0, 0.0, 3.0, -4.0),
        (1.0, 2.0, 2.0, 70000.0),
    ]
    raw = b"".join(struct.pack("<ffff", *point) for point in points)
    converted = module.convert_cloud(raw, RAW_FIELDS, 4, 1, 16, 2, 2, 0.1)

    actual_fields = [
        (field.name, field.offset, field.datatype, field.count) for field in converted.fields
    ]
    assert actual_fields == EXPECTED_FIELDS, actual_fields
    assert converted.point_step == 32
    assert converted.accepted_points == 4
    assert converted.time_span_sec == 0.1
    assert len(converted.data) == 128
    assert converted_values(converted, "<I", 16) == [0, 33333333, 66666667, 100000000]
    assert converted_values(converted, "<B", 22) == [0, 1, 0, 1]
    actual_intensities = converted_values(converted, "<f", 12)
    assert all(
        math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6)
        for actual, expected in zip(actual_intensities, [12.4, 20.6, 0.0, 70000.0])
    ), actual_intensities
    assert converted_values(converted, "<H", 20) == [12, 21, 0, 65535]
    assert converted_values(converted, "<H", 24) == [0, 0, 0, 0]
    assert converted_values(converted, "<I", 28) == [1000, 2000, 3000, 3000]

    sparse_raw = raw[:-16]
    sparse = module.convert_cloud(sparse_raw, RAW_FIELDS, 3, 1, 16, 2, 2, 0.1)
    assert sparse.accepted_points == 3
    assert len(sparse.data) == 3 * 32
    assert converted_values(sparse, "<I", 16) == [0, 50000000, 100000000]
    assert converted_values(sparse, "<B", 22) == [0, 1, 0]

    nan_raw = struct.pack("<ffff", math.nan, 0.0, 0.0, 1.0)
    expect_value_error(
        lambda: module.convert_cloud(nan_raw, RAW_FIELDS, 1, 1, 16, 1, 1, 0.1),
        "finite",
    )
    expect_value_error(
        lambda: module.convert_cloud(raw, RAW_FIELDS, 4, 1, 12, 2, 2, 0.1),
        "point_step",
    )
    expect_value_error(
        lambda: module.convert_cloud(raw[:-16], RAW_FIELDS, 4, 1, 16, 2, 2, 0.1),
        "data length",
    )
    oversized_raw = raw + raw[:16]
    expect_value_error(
        lambda: module.convert_cloud(oversized_raw, RAW_FIELDS, 5, 1, 16, 2, 2, 0.1),
        "configured scan capacity",
    )
    expect_value_error(
        lambda: module.convert_cloud(raw, RAW_FIELDS[:-1], 4, 1, 16, 2, 2, 0.1),
        "seg",
    )
    expect_value_error(
        lambda: module.convert_cloud(raw, RAW_FIELDS, 4, 1, 16, 2, 2, 0.0),
        "scan period",
    )

    print("stage7 cloud contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
