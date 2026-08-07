#!/usr/bin/env python3
"""Hard bounds and runtime watchdog decisions for simulated flight."""

from __future__ import annotations

from dataclasses import dataclass
import math


class GeofenceViolation(ValueError):
    """A goal or observed vehicle state is outside the allowed flight volume."""


@dataclass(frozen=True)
class Geofence:
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    max_speed_mps: float = 2.0
    max_odom_age_s: float = 0.5
    unreasonable_margin_m: float = 5.0

    def __post_init__(self):
        if not self.min_x < self.max_x or not self.min_y < self.max_y or not self.min_z < self.max_z:
            raise ValueError("geofence bounds must be ordered")
        if self.max_speed_mps <= 0.0 or self.max_odom_age_s <= 0.0 or self.unreasonable_margin_m <= 0.0:
            raise ValueError("geofence limits and unreasonable margin must be positive")


def _point(point):
    if len(point) != 3 or not all(math.isfinite(float(value)) for value in point):
        raise GeofenceViolation("point must contain three finite values")
    return tuple(float(value) for value in point)


def validate_point(point, fence: Geofence) -> bool:
    x, y, z = _point(point)
    if not (fence.min_x <= x <= fence.max_x and fence.min_y <= y <= fence.max_y and fence.min_z <= z <= fence.max_z):
        raise GeofenceViolation("point is outside geofence")
    return True


def validate_segment(start, end, fence: Geofence, step_m: float = 0.25) -> bool:
    if step_m <= 0.0 or not math.isfinite(step_m):
        raise ValueError("step_m must be positive and finite")
    first = _point(start)
    last = _point(end)
    distance = math.sqrt(sum((last[index] - first[index]) ** 2 for index in range(3)))
    count = max(1, int(math.ceil(distance / step_m)))
    for index in range(count + 1):
        ratio = index / count
        validate_point(tuple(first[axis] + ratio * (last[axis] - first[axis]) for axis in range(3)), fence)
    return True


def watchdog_decision_with_reason(
    position,
    fence: Geofence,
    *,
    armed: bool,
    mode: str,
    odom_age_s: float,
    speed_mps: float,
    mode_grace_active: bool = False,
) -> tuple:
    """Return (decision, reason) for a single watchdog observation."""
    if not armed:
        return "continue", "disarmed"
    try:
        validate_point(position, fence)
    except GeofenceViolation:
        x, y, z = (float(value) for value in position)
        if not all(math.isfinite(value) for value in (x, y, z)):
            return "no_autoland", "unreasonable_position"
        if (
            x < fence.min_x - fence.unreasonable_margin_m
            or x > fence.max_x + fence.unreasonable_margin_m
            or y < fence.min_y - fence.unreasonable_margin_m
            or y > fence.max_y + fence.unreasonable_margin_m
            or z < fence.min_z - fence.unreasonable_margin_m
            or z > fence.max_z + fence.unreasonable_margin_m
        ):
            return "no_autoland", "unreasonable_position"
        if x < fence.min_x or x > fence.max_x:
            return "land", "outside_x"
        if y < fence.min_y or y > fence.max_y:
            return "land", "outside_y"
        return "land", "outside_z"
    if mode != "OFFBOARD" and not mode_grace_active:
        return "land", "mode_loss"
    if not math.isfinite(float(odom_age_s)) or odom_age_s > fence.max_odom_age_s:
        return "land", "stale_odom"
    if not math.isfinite(float(speed_mps)) or speed_mps > fence.max_speed_mps:
        return "land", "max_speed"
    return "continue", "ok"


def watchdog_decision(
    position,
    fence: Geofence,
    *,
    armed: bool,
    mode: str,
    odom_age_s: float,
    speed_mps: float,
    mode_grace_active: bool = False,
) -> str:
    """Legacy decision string kept for existing callers."""
    decision, _reason = watchdog_decision_with_reason(
        position,
        fence,
        armed=armed,
        mode=mode,
        odom_age_s=odom_age_s,
        speed_mps=speed_mps,
        mode_grace_active=mode_grace_active,
    )
    return decision
