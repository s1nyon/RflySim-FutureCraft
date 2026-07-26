#!/usr/bin/env python3
"""Build a mission score summary from JSONL mission events."""

import argparse
import json
import sys
from pathlib import Path


def load_events(path):
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
            if "time" not in event:
                raise ValueError(f"line {line_number}: missing required field 'time'")
            if "event" not in event:
                raise ValueError(f"line {line_number}: missing required field 'event'")
            events.append(event)
    if not events:
        raise ValueError("no events found")
    return events


def build_summary(events):
    start_time = None
    end_time = None
    min_distance = None
    offboard_loss_count = 0
    collision_count = 0
    timeout_count = 0
    targets = set()
    failure_reasons = []

    for event in events:
        event_name = event["event"]
        event_time = float(event["time"])

        if event_name == "mission_start" and start_time is None:
            start_time = event_time
        elif event_name == "mission_end":
            end_time = event_time
        elif event_name in ("uav_distance", "min_uav_distance"):
            distance = float(event["distance_m"])
            min_distance = distance if min_distance is None else min(min_distance, distance)
        elif event_name == "offboard_lost":
            offboard_loss_count += 1
        elif event_name == "collision":
            collision_count += 1
        elif event_name == "timeout":
            timeout_count += 1
        elif event_name == "target_detected":
            target_id = event.get("target_id") or f"{event.get('target_type', 'unknown')}@{event_time}"
            targets.add(str(target_id))

    if start_time is None:
        failure_reasons.append("missing_mission_start")
        start_time = float(events[0]["time"])
    if end_time is None:
        failure_reasons.append("missing_mission_end")
        end_time = float(events[-1]["time"])
    if offboard_loss_count:
        failure_reasons.append("offboard_lost")
    if collision_count:
        failure_reasons.append("collision")
    if timeout_count:
        failure_reasons.append("timeout")

    duration = max(0.0, end_time - start_time)
    success = len(failure_reasons) == 0

    return {
        "success": success,
        "failure_reasons": failure_reasons,
        "mission_start_time": round(start_time, 3),
        "mission_end_time": round(end_time, 3),
        "duration_s": round(duration, 3),
        "min_uav_distance_m": None if min_distance is None else round(min_distance, 3),
        "offboard_loss_count": offboard_loss_count,
        "collision_count": collision_count,
        "timeout_count": timeout_count,
        "targets_detected_count": len(targets),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate future_aircraft_sim score_summary.json")
    parser.add_argument("--events", required=True, type=Path, help="Path to mission_events.jsonl")
    parser.add_argument("--output", required=True, type=Path, help="Path to write score_summary.json")
    args = parser.parse_args(argv)

    try:
        events = load_events(args.events)
        summary = build_summary(events)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:  # keep CLI errors concise for batch/PowerShell callers
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
