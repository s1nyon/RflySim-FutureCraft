#!/usr/bin/env python3
"""Contract checks for the arc-length course guidance used by Stage 8."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path


def load_module(path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("course_guidance", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load guidance module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_close(actual, expected, tol=1e-9):
    if abs(actual - expected) > tol:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guidance-module", required=True, type=Path)
    parser.add_argument("--course-spec", required=True, type=Path)
    args = parser.parse_args()

    guidance = load_module(args.guidance_module)
    course = json.loads(args.course_spec.read_text(encoding="utf-8"))
    centreline = guidance.Centreline.from_course(course)

    total = 4.5 + 3.1 + 4.5 + 0.9 * math.pi
    assert_close(centreline.total_length, total, 1e-9)

    assert_close(centreline.point_at_s(0.0)[0], 18.5, 1e-9)
    assert_close(centreline.point_at_s(0.0)[1], 0.0, 1e-9)
    assert_close(centreline.point_at_s(4.5)[0], 23.0, 1e-9)
    assert_close(centreline.point_at_s(4.5)[1], 0.0, 1e-9)
    arc1_end = 4.5 + 0.9 * math.pi / 2.0
    assert_close(centreline.point_at_s(arc1_end)[0], 23.9, 1e-9)
    assert_close(centreline.point_at_s(arc1_end)[1], 0.9, 1e-9)
    assert_close(centreline.point_at_s(total)[0], 29.3, 1e-9)
    assert_close(centreline.point_at_s(total)[1], 4.9, 1e-9)

    assert centreline.kind_at_s(2.0) == "line"
    assert centreline.kind_at_s(5.0) == "arc"
    assert centreline.kind_at_s(7.0) == "line"
    assert centreline.kind_at_s(9.5) == "arc"
    assert centreline.kind_at_s(12.0) == "line"

    assert_close(centreline.width_at_s(2.0), 1.5, 1e-9)
    assert_close(centreline.width_at_s(5.0), 1.5, 1e-9)
    assert_close(centreline.width_at_s(7.0), 1.4, 1e-9)
    assert_close(centreline.width_at_s(12.0), 1.5, 1e-9)

    assert_close(centreline.curvature_at_s(2.0), 0.0, 1e-9)
    assert_close(centreline.curvature_at_s(5.0), 1.0 / 0.9, 1e-9)
    assert_close(centreline.curvature_at_s(9.5), 1.0 / 0.9, 1e-9)

    # Look-ahead ramps from straight (2.2 m) to turn (1.0 m) over 0.9 m.
    assert_close(centreline.lookahead_s(3.6), 2.2, 1e-9)
    assert_close(centreline.lookahead_s(4.05), 1.6, 1e-9)
    assert_close(centreline.lookahead_s(4.5), 1.0, 1e-9)
    assert_close(centreline.lookahead_s(5.0), 1.0, 1e-9)
    assert centreline.lookahead_s(3.6) > centreline.lookahead_s(4.05) > centreline.lookahead_s(4.5)

    gates = guidance.build_flythrough_gates(course)
    assert len(gates) >= 18
    assert len(gates) <= 30
    assert gates[0]["s"] == 0.0
    assert gates[-1]["s"] < total
    assert_close(gates[-1]["target_s"], total, 1e-9)
    assert all(gate["target_s"] > gate["s"] for gate in gates)

    deltas = [gates[index + 1]["s"] - gates[index]["s"] for index in range(len(gates) - 1)]
    assert min(deltas) >= 0.4
    assert max(deltas) <= 0.8 + 1e-9
    assert any(abs(delta - 0.5) <= 1e-9 for delta in deltas)
    assert any(abs(delta - 0.8) <= 1e-9 for delta in deltas)

    arc_interior = [gate for gate in gates if 4.5 < gate["s"] < arc1_end]
    assert arc_interior
    for gate in arc_interior:
        assert_close(gate["target_s"] - gate["s"], 1.0, 1e-9)

    assert guidance.gate_at_or_before(gates, -0.1) is None
    assert_close(guidance.gate_at_or_before(gates, 1.6)["s"], 1.6, 1e-9)
    assert guidance.gate_at_or_before(gates, total + 10.0) is gates[-1]

    print("stage8 course guidance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
