#!/usr/bin/env python3
"""Emit a dry-run Stage 8 guidance table and static smoothness summary.

This is an offline diagnostic: it builds the real mission plan from the course
JSON and prints the fly-through checkpoint / look-ahead target pairs plus the
tandem arc-length gaps.  It makes no live or ROS calls.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import stage7_flight_plan


def _rounded(value, digits=3):
    return round(float(value), digits)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--course-spec", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="write summary JSON here")
    args = parser.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    course = json.loads(args.course_spec.read_text(encoding="utf-8"))
    plan = stage7_flight_plan.build_plan(config, course)

    poses = {item["name"]: item["position"] for item in course["takeoff_poses"]}
    publishes = [
        action
        for action in plan["actions"]
        if action["action"] == "publish_planner_goal"
    ]

    rows = []
    for action in publishes:
        uav_id = action["uav"]
        origin = poses[uav_id]
        terminal = bool(action.get("terminal"))
        world_x = float(action["goal"]["x"]) + float(origin[0])
        world_y = float(action["goal"]["y"]) + float(origin[1])
        rows.append(
            {
                "uav": uav_id,
                "checkpoint_s": action.get("checkpoint_s"),
                "target_s": action.get("target_s"),
                "lookahead_m": action.get("lookahead_m"),
                "segment_kind": action.get("segment_kind"),
                "width": action.get("width"),
                "terminal": terminal,
                "target_x": world_x,
                "target_y": world_y,
            }
        )

    print("UAV | checkpoint_s | target_s | lookahead | kind | width | terminal | target_x | target_y")
    print("---|---|---|---|---|---|---|---|---")
    for row in rows:
        checkpoint_s = "" if row["checkpoint_s"] is None else f"{_rounded(row['checkpoint_s']):.3f}"
        target_s = "" if row["target_s"] is None else f"{_rounded(row['target_s']):.3f}"
        lookahead = "" if row["lookahead_m"] is None else f"{_rounded(row['lookahead_m']):.3f}"
        width = "" if row["width"] is None else f"{_rounded(row['width']):.3f}"
        kind = row["segment_kind"] or "terminal"
        print(
            f"{row['uav']} | {checkpoint_s} | {target_s} | {lookahead} | {kind} | {width} | "
            f"{row['terminal']} | {_rounded(row['target_x']):.3f} | {_rounded(row['target_y']):.3f}"
        )

    leader = [row for row in rows if row["uav"] == "uav1" and not row["terminal"]]
    follower = [row for row in rows if row["uav"] == "uav2" and not row["terminal"]]
    leader_gaps = [
        leader[index + 1]["checkpoint_s"] - leader[index]["checkpoint_s"]
        for index in range(len(leader) - 1)
    ]
    follower_gaps = [
        follower[index + 1]["checkpoint_s"] - follower[index]["checkpoint_s"]
        for index in range(len(follower) - 1)
    ]
    turn_lookaheads = [row["lookahead_m"] for row in leader if row["segment_kind"] == "arc"]
    straight_lookaheads = [row["lookahead_m"] for row in leader if row["segment_kind"] == "line"]
    min_width = min(float(item["width"]) for item in course["centreline"])
    vehicle_radius = float(course["vehicle_envelope"]["horizontal_diameter"]) / 2.0

    summary = {
        "mission_name": plan["mission_name"],
        "leader_flythrough_gates": len(leader),
        "follower_flythrough_gates": len(follower),
        "checkpoint_spacing_leader": {
            "min": _rounded(min(leader_gaps)),
            "max": _rounded(max(leader_gaps)),
        },
        "checkpoint_spacing_follower": {
            "min": _rounded(min(follower_gaps)),
            "max": _rounded(max(follower_gaps)),
        },
        "turn_lookahead_range": {
            "min": _rounded(min(turn_lookaheads)),
            "max": _rounded(max(turn_lookaheads)),
        },
        "straight_lookahead_range": {
            "min": _rounded(min(straight_lookaheads)),
            "max": _rounded(max(straight_lookaheads)),
        },
        "nominal_centreline_wall_clearance_m": _rounded(min_width / 2.0 - vehicle_radius),
        "tandem_min_gap_m": _rounded(
            min(row["leader_checkpoint_s"] - row["checkpoint_s"] for row in [
                action
                for action in plan["actions"]
                if action["action"] == "publish_planner_goal"
                and action["uav"] == "uav2"
                and not action.get("terminal")
            ])
        ),
    }
    print()
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
