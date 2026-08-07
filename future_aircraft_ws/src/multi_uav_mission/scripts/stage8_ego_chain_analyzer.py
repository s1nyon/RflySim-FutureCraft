#!/usr/bin/env python3
"""Per-goal EGO execution-chain analyzer (read-only post-processing).

Consumes the Stage 8 control-chain JSONL produced by
``stage8_control_chain_recorder.py`` and correlates, per UAV and per
navigation goal, the chain:

    planner goal -> traj_start_trigger -> bspline -> pos_cmd -> reached

For every segment it reports the first/last message time, message count, and
any silent window (an interval without messages) for each chain stage, so the
first break point of a failed navigation goal can be identified.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


CHAIN_KINDS = (
    "planner_goal",
    "traj_start_trigger",
    "bspline",
    "planner_command",
)
CONTROL_FEEDBACK_KINDS = (
    "setpoint_target",
    "local_position",
)
ALL_KINDS = CHAIN_KINDS + CONTROL_FEEDBACK_KINDS


def _load_events(path):
    events = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL at {path}:{line_number}: {exc}"
                ) from exc
    return events


def _monotonic(event):
    return float(event["receive_monotonic"])


def _segment_gap_sec(events):
    """Longest interval between consecutive events, or None for <2 events."""
    if len(events) < 2:
        return 0.0
    stamps = sorted(_monotonic(event) for event in events)
    return max(
        right - left for left, right in zip(stamps, stamps[1:])
    )


def _kind_count(events, kind):
    return sum(1 for event in events if event.get("kind") == kind)


def build_segments(events, pre_roll_sec=1.0):
    """Group JSONL events into per-UAV navigation-goal segments."""
    by_uav = defaultdict(list)
    for event in events:
        uav_id = event.get("uav_id")
        if uav_id:
            by_uav[uav_id].append(event)

    segments = []
    for uav_id in sorted(by_uav):
        uav_events = sorted(by_uav[uav_id], key=_monotonic)
        goal_events = [
            event for event in uav_events if event.get("kind") == "planner_goal"
        ]
        if not goal_events:
            continue
        boundaries = [_monotonic(event) for event in goal_events]
        for index, start in enumerate(boundaries):
            end = boundaries[index + 1] if index + 1 < len(boundaries) else None
            window_start = start - pre_roll_sec
            window_end = end if end is not None else None
            window_events = [
                event
                for event in uav_events
                if _monotonic(event) >= window_start
                and (window_end is None or _monotonic(event) < window_end)
            ]
            goal_event = goal_events[index]
            stage_stats = {}
            for kind in ALL_KINDS:
                kind_events = [
                    event for event in window_events if event.get("kind") == kind
                ]
                stage_stats[kind] = {
                    "count": len(kind_events),
                    "first_monotonic": (
                        round(_monotonic(kind_events[0]), 6) if kind_events else None
                    ),
                    "last_monotonic": (
                        round(_monotonic(kind_events[-1]), 6) if kind_events else None
                    ),
                    "max_gap_sec": (
                        round(_segment_gap_sec(kind_events), 6) if kind_events else None
                    ),
                }
            segments.append(
                {
                    "uav_id": uav_id,
                    "goal_index": index + 1,
                    "goal_position": list(goal_event.get("position", [])),
                    "window_start_monotonic": round(window_start, 6),
                    "window_end_monotonic": (
                        round(window_end, 6) if window_end is not None else None
                    ),
                    "has_next_goal": end is not None,
                    "stages": stage_stats,
                    "chain_complete": all(
                        stage_stats[kind]["count"] > 0 for kind in CHAIN_KINDS
                    ),
                    "control_feedback_present": all(
                        stage_stats[kind]["count"] > 0
                        for kind in CONTROL_FEEDBACK_KINDS
                    ),
                    "executor_proceeded": end is not None,
                }
            )
    return segments


def build_report(events, pre_roll_sec=1.0):
    segments = build_segments(events, pre_roll_sec=pre_roll_sec)
    report = {
        "event_count": len(events),
        "chain_kinds": list(CHAIN_KINDS),
        "uavs": {},
        "segments": segments,
    }
    for uav_id in sorted({event.get("uav_id") for event in events if event.get("uav_id")}):
        uav_segments = [
            segment for segment in segments if segment["uav_id"] == uav_id
        ]
        report["uavs"][uav_id] = {
            "goal_count": len(uav_segments),
            "segments_with_bspline": sum(
                1 for segment in uav_segments
                if segment["stages"]["bspline"]["count"] > 0
            ),
            "segments_with_pos_cmd": sum(
                1 for segment in uav_segments
                if segment["stages"]["planner_command"]["count"] > 0
            ),
        }
    return report


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--pre-roll-sec", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.pre_roll_sec < 0:
        parser.error("--pre-roll-sec must be non-negative")
    events = _load_events(args.input)
    report = build_report(events, pre_roll_sec=args.pre_roll_sec)
    write_json(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
