#!/usr/bin/env python3
"""Read-only Stage 8 flight metrics from recorded odom/goal CSVs and events.

Computes speed profile, mid-course stop episodes, checkpoint handoff speeds,
cross-track error, geometric wall clearance, tandem arc-length gap, physical
inter-UAV distance, tunnel overlap, and duplicate-goal-burst detection.  It
publishes nothing and has no control-path dependency.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

import course_guidance


VEHICLE_RADIUS_M = 0.45 / 2.0
STOP_SPEED_MPS = 0.12
STOP_DURATION_S = 0.5


def _load_odom_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                rows.append(
                    {
                        "t": int(row["%time"]) / 1e9,
                        "x": float(row["field.pose.pose.position.x"]),
                        "y": float(row["field.pose.pose.position.y"]),
                        "z": float(row["field.pose.pose.position.z"]),
                        "vx": float(row["field.twist.twist.linear.x"]),
                        "vy": float(row["field.twist.twist.linear.y"]),
                        "vz": float(row["field.twist.twist.linear.z"]),
                    }
                )
            except (KeyError, ValueError):
                continue
    return rows


def _speed(row):
    return math.hypot(row["vx"], row["vy"], row["vz"])


def _percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))
    return ordered[index]


def _stop_episodes(rows):
    episodes = []
    start = None
    for row in rows:
        low = _speed(row) < STOP_SPEED_MPS
        if low and start is None:
            start = row["t"]
        elif not low and start is not None:
            if row["t"] - start >= STOP_DURATION_S:
                episodes.append((start, row["t"]))
            start = None
    if start is not None:
        episodes.append((start, rows[-1]["t"]))
    return [episode for episode in episodes if episode[1] - episode[0] >= STOP_DURATION_S]


def _course_metrics(rows, centreline, origin, entry_s, exit_s):
    traverse = []
    for row in rows:
        world = (row["x"] + origin[0], row["y"] + origin[1])
        s, cross = centreline.nearest_s(world)
        if entry_s <= s <= exit_s:
            traverse.append({**row, "s": s, "cross_track": cross})
    if not traverse:
        return None
    speeds = [_speed(row) for row in traverse]
    clearances = [
        centreline.width_at_s(row["s"]) / 2.0 - row["cross_track"] - VEHICLE_RADIUS_M
        for row in traverse
    ]
    return {
        "traverse_time_s": round(traverse[-1]["t"] - traverse[0]["t"], 2),
        "mean_speed_mps": round(statistics.fmean(speeds), 3),
        "median_speed_mps": round(statistics.median(speeds), 3),
        "max_speed_mps": round(max(speeds), 3),
        "p95_speed_mps": round(_percentile(speeds, 0.95), 3),
        "min_speed_mps": round(min(speeds), 3),
        "mid_course_stops": len(_stop_episodes(traverse)),
        "max_cross_track_m": round(max(row["cross_track"] for row in traverse), 3),
        "p05_cross_track_m": round(_percentile([row["cross_track"] for row in traverse], 0.05), 3),
        "median_cross_track_m": round(statistics.median([row["cross_track"] for row in traverse]), 3),
        "min_wall_clearance_m": round(min(clearances), 3),
        "p05_wall_clearance_m": round(_percentile(clearances, 0.05), 3),
        "median_wall_clearance_m": round(statistics.median(clearances), 3),
        "entry_time_s": traverse[0]["t"],
        "exit_time_s": traverse[-1]["t"],
    }


def _goal_counts(run_dir):
    result = {}
    for uav in ("uav1", "uav2"):
        path = run_dir / f"{uav}_goal_msgs.csv"
        if not path.exists():
            result[uav] = {"messages": 0, "bursts": 0}
            continue
        stamps = []
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    stamps.append(int(row["%time"]) / 1e9)
                except (KeyError, ValueError):
                    continue
        bursts = sum(
            1 for a, b in zip(stamps, stamps[1:]) if b - a < 0.1
        )
        result[uav] = {"messages": len(stamps), "duplicate_bursts": bursts}
    return result


def _handoff_speeds(run_dir):
    result = {}
    events_path = run_dir / "mission_events.jsonl"
    if not events_path.exists():
        return result
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") != "navigation_confirmed":
            continue
        result.setdefault(event["uav"], []).append(
            {
                "time": float(event["time"]),
                "speed_mps": float(event.get("speed_mps") or 0.0),
            }
        )
    return result


def _logical_goal_counts(run_dir):
    trace_path = run_dir / "executor_trace.json"
    if not trace_path.exists():
        return {}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    counts = {}
    for entry in trace:
        if entry.get("action") == "publish_planner_goal":
            counts[entry.get("uav")] = counts.get(entry.get("uav"), 0) + 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--course-spec", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    course = json.loads(args.course_spec.read_text(encoding="utf-8"))
    centreline = course_guidance.Centreline.from_course(course)
    poses = {item["name"]: item["position"] for item in course["takeoff_poses"]}
    total = centreline.total_length
    entry_s = 0.2
    exit_s = total - 0.2

    uav_metrics = {}
    odom_trajectories = {}
    for uav_id, origin in (("uav1", poses["uav1"]), ("uav2", poses["uav2"])):
        odom = _load_odom_csv(args.run_dir / f"{uav_id}_odom.csv")
        if not odom:
            continue
        odom_trajectories[uav_id] = odom
        metrics = _course_metrics(odom, centreline, origin, entry_s, exit_s)
        if metrics is not None:
            uav_metrics[uav_id] = metrics

    tandem = {}
    if set(uav_metrics) == {"uav1", "uav2"}:
        t0 = max(uav_metrics["uav1"]["entry_time_s"], uav_metrics["uav2"]["entry_time_s"])
        t1 = min(uav_metrics["uav1"]["exit_time_s"], uav_metrics["uav2"]["exit_time_s"])
        tandem["overlap_duration_s"] = round(max(0.0, t1 - t0), 2)

        overlap_samples = []
        for row1 in odom_trajectories["uav1"]:
            s1, _ = centreline.nearest_s((row1["x"] + poses["uav1"][0], row1["y"] + poses["uav1"][1]))
            if not (entry_s <= s1 <= exit_s):
                continue
            nearest = min(
                odom_trajectories["uav2"],
                key=lambda row2: abs(row2["t"] - row1["t"]),
            )
            s2, _ = centreline.nearest_s(
                (nearest["x"] + poses["uav2"][0], nearest["y"] + poses["uav2"][1])
            )
            if not (entry_s <= s2 <= exit_s):
                continue
            d12 = math.hypot(
                row1["x"] + poses["uav1"][0] - nearest["x"] - poses["uav2"][0],
                row1["y"] + poses["uav1"][1] - nearest["y"] - poses["uav2"][1],
                row1["z"] - nearest["z"],
            )
            overlap_samples.append(
                {"t": row1["t"], "s1": s1, "s2": s2, "gap_s": s1 - s2, "d12": d12}
            )
        if overlap_samples:
            gaps = [item["gap_s"] for item in overlap_samples]
            dists = [item["d12"] for item in overlap_samples]
            tandem.update(
                {
                    "min_gap_s": round(min(gaps), 3),
                    "median_gap_s": round(statistics.median(gaps), 3),
                    "p05_gap_s": round(_percentile(gaps, 0.05), 3),
                    "p95_gap_s": round(_percentile(gaps, 0.95), 3),
                    "min_physical_distance_m": round(min(dists), 3),
                    "p05_physical_distance_m": round(_percentile(dists, 0.05), 3),
                }
            )

    report = {
        "run_dir": str(args.run_dir),
        "uavs": uav_metrics,
        "tandem": tandem,
        "planner": {
            "logical_goal_counts": _logical_goal_counts(args.run_dir),
            "observed_goal_messages": _goal_counts(args.run_dir),
        },
        "handoff_speeds": _handoff_speeds(args.run_dir),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
