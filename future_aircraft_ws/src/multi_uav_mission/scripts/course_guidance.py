#!/usr/bin/env python3
"""Arc-length centreline geometry and fly-through guidance for Stage 8.

The static course centreline is a sequence of ``line`` and ``arc`` segments.
This module exposes a one-dimensional arc-length coordinate ``s`` along that
centreline and turns it into two distinct planning concepts:

* a **checkpoint** (progress gate): where the vehicle is judged to have reached
  a certain point along the course; and
* a **look-ahead target**: a point ahead of the checkpoint that is actually
  sent to EGO-Swarm, so the planner keeps moving instead of braking to zero at
  every intermediate gate.

This is pure geometry and contains no ROS dependencies.
"""

from __future__ import annotations

import math


LOOKAHEAD_STRAIGHT_M = 2.2
LOOKAHEAD_TURN_M = 1.0
LOOKAHEAD_RAMP_M = 0.9
CHECKPOINT_STRAIGHT_M = 0.8
CHECKPOINT_TURN_M = 0.5

_EPS = 1e-9


def _directed_arc_sweep(start_angle, end_angle, turn):
    if turn == "left":
        return (end_angle - start_angle) % (2.0 * math.pi)
    if turn == "right":
        return -((start_angle - end_angle) % (2.0 * math.pi))
    raise ValueError("arc turn must be left or right")


def _clamp(value, low, high):
    return max(low, min(high, value))


class Centreline:
    """Parametric arc-length view of a course centreline."""

    def __init__(self, segments):
        self.segments = segments
        self._total_length = segments[-1]["s_end"] if segments else 0.0

    @staticmethod
    def from_course(course):
        segments = []
        traversed = 0.0
        for item in course["centreline"]:
            kind = item["kind"]
            start = (float(item["start"][0]), float(item["start"][1]))
            end = (float(item["end"][0]), float(item["end"][1]))
            width = float(item["width"])
            if kind == "line":
                length = math.hypot(end[0] - start[0], end[1] - start[1])
                segment = {
                    "kind": "line",
                    "start": start,
                    "end": end,
                    "width": width,
                    "length": length,
                }
            elif kind == "arc":
                center = (float(item["center"][0]), float(item["center"][1]))
                radius = float(item["radius"])
                start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
                end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
                sweep = _directed_arc_sweep(start_angle, end_angle, item["turn"])
                length = abs(sweep) * radius
                segment = {
                    "kind": "arc",
                    "center": center,
                    "radius": radius,
                    "start_angle": start_angle,
                    "sweep": sweep,
                    "width": width,
                    "length": length,
                }
            else:
                raise ValueError("centreline segment kind must be line or arc")
            if length <= _EPS:
                raise ValueError("centreline segments must have positive length")
            segment["s_start"] = traversed
            traversed += length
            segment["s_end"] = traversed
            segments.append(segment)
        if not segments:
            raise ValueError("centreline must not be empty")
        return Centreline(segments)

    @property
    def total_length(self):
        return self._total_length

    def _segment_at_s(self, s):
        s = _clamp(s, 0.0, self._total_length)
        for index, segment in enumerate(self.segments):
            is_last = index == len(self.segments) - 1
            if s <= segment["s_end"] + _EPS or is_last:
                return segment
        return self.segments[-1]

    def kind_at_s(self, s):
        return self._segment_at_s(s)["kind"]

    def width_at_s(self, s):
        return self._segment_at_s(s)["width"]

    def curvature_at_s(self, s):
        segment = self._segment_at_s(s)
        if segment["kind"] == "arc":
            return 1.0 / segment["radius"]
        return 0.0

    def point_at_s(self, s):
        s = _clamp(s, 0.0, self._total_length)
        segment = self._segment_at_s(s)
        ratio = _clamp((s - segment["s_start"]) / segment["length"], 0.0, 1.0)
        if segment["kind"] == "line":
            start = segment["start"]
            end = segment["end"]
            return (
                start[0] + ratio * (end[0] - start[0]),
                start[1] + ratio * (end[1] - start[1]),
            )
        center = segment["center"]
        radius = segment["radius"]
        angle = segment["start_angle"] + ratio * segment["sweep"]
        return (
            center[0] + radius * math.cos(angle),
            center[1] + radius * math.sin(angle),
        )

    def nearest_s(self, point, ds=0.02):
        """Return ``(s, distance_m)`` of the closest centreline sample.

        ``point`` is in the same world frame as the course JSON.  The result is
        the along-track arc length ``s`` of the nearest centreline point and the
        Euclidean distance to it (cross-track for a vehicle near the course).
        """
        best_s = 0.0
        best_dist = float("inf")
        s = 0.0
        while s <= self._total_length + _EPS:
            sample = self.point_at_s(s)
            distance = math.hypot(point[0] - sample[0], point[1] - sample[1])
            if distance < best_dist:
                best_dist = distance
                best_s = s
            s += ds
        # Local refinement so straight/arc projection is not limited by ds.
        fine_ds = ds / 10.0
        probe = max(0.0, best_s - ds)
        while probe <= min(self._total_length, best_s + ds) + _EPS:
            sample = self.point_at_s(probe)
            distance = math.hypot(point[0] - sample[0], point[1] - sample[1])
            if distance < best_dist:
                best_dist = distance
                best_s = probe
            probe += fine_ds
        return best_s, best_dist

    def _turn_influence(self, s):
        arcs = [segment for segment in self.segments if segment["kind"] == "arc"]
        if not arcs:
            return 0.0
        if any(segment["s_start"] - _EPS <= s <= segment["s_end"] + _EPS for segment in arcs):
            return 1.0
        distance = min(
            (segment["s_start"] - s) if s < segment["s_start"] else (s - segment["s_end"])
            for segment in arcs
        )
        if LOOKAHEAD_RAMP_M <= _EPS:
            return 0.0
        return _clamp(1.0 - distance / LOOKAHEAD_RAMP_M, 0.0, 1.0)

    def lookahead_s(
        self,
        s,
        *,
        lookahead_straight=LOOKAHEAD_STRAIGHT_M,
        lookahead_turn=LOOKAHEAD_TURN_M,
        ramp=LOOKAHEAD_RAMP_M,
    ):
        influence = self._turn_influence(s)
        return lookahead_straight + (lookahead_turn - lookahead_straight) * influence


def build_flythrough_gates(
    course,
    *,
    checkpoint_straight=CHECKPOINT_STRAIGHT_M,
    checkpoint_turn=CHECKPOINT_TURN_M,
    lookahead_straight=LOOKAHEAD_STRAIGHT_M,
    lookahead_turn=LOOKAHEAD_TURN_M,
    ramp=LOOKAHEAD_RAMP_M,
):
    centreline = Centreline.from_course(course)
    gates = []
    s = 0.0
    total = centreline.total_length
    while s < total - _EPS:
        target_s = min(
            s + centreline.lookahead_s(
                s,
                lookahead_straight=lookahead_straight,
                lookahead_turn=lookahead_turn,
                ramp=ramp,
            ),
            total,
        )
        gates.append(
            {
                "s": s,
                "checkpoint": centreline.point_at_s(s),
                "target_s": target_s,
                "target": centreline.point_at_s(target_s),
                "terminal": False,
            }
        )
        spacing = checkpoint_turn if centreline.kind_at_s(s) == "arc" else checkpoint_straight
        s = min(s + spacing, total)
    return gates


def gate_at_or_before(gates, s):
    """Return the gate with the largest ``s`` not greater than ``s``."""
    if not gates or s < gates[0]["s"] - _EPS:
        return None
    selected = gates[0]
    for gate in gates:
        if gate["s"] <= s + _EPS:
            selected = gate
        else:
            break
    return selected
