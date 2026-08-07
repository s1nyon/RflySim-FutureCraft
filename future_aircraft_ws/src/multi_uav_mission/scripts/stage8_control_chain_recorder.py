#!/usr/bin/env python3
"""Read-only Stage 8 control-chain forensic recorder.

Subscribes to the full planner -> MAVROS -> FAST-LIO -> PX4 control chain and
writes a run-scoped JSONL plus a summary. It never publishes, never calls
services, and never arms. Watchdog decisions and flight-event recording stay
with the existing implementations; this script only references their files.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from pathlib import Path

MAVROS_IGNORE_PZ = 4  # mavros_msgs/PositionTarget.IGNORE_PZ
MAX_Z_SAMPLES = 50000


def control_event(
    kind,
    uav_id,
    receive_wall_time,
    receive_monotonic,
    header_stamp=None,
    **payload,
):
    """Build one JSONL event with wall, monotonic, and header time sources."""
    event = {
        "kind": str(kind),
        "uav_id": str(uav_id),
        "receive_wall_time": round(float(receive_wall_time), 6),
        "receive_monotonic": round(float(receive_monotonic), 6),
        "header_stamp": (
            round(float(header_stamp), 6)
            if header_stamp is not None
            else None
        ),
    }
    event.update(payload)
    return event


def setpoint_z_commanded(type_mask):
    """True when a PositionTarget actually commands z (IGNORE_PZ not set)."""
    return (int(type_mask) & MAVROS_IGNORE_PZ) == 0


def summarize_z_samples(samples, min_z, max_z):
    """Summarize z samples against a hard geofence z window."""
    if not samples:
        return {
            "count": 0,
            "min_z": None,
            "max_z": None,
            "outside_count": 0,
            "outside_min_z": None,
            "outside_max_z": None,
        }
    z_min = min(samples)
    z_max = max(samples)
    outside = [z for z in samples if z < float(min_z) or z > float(max_z)]
    return {
        "count": len(samples),
        "min_z": round(z_min, 3),
        "max_z": round(z_max, 3),
        "outside_count": len(outside),
        "outside_min_z": round(min(outside), 3) if outside else None,
        "outside_max_z": round(max(outside), 3) if outside else None,
    }


def summarize_mode_changes(events):
    """Compress state-change events into per-mode segments."""
    segments = []
    last_key = None
    for event in events:
        key = (event["mode"], bool(event["armed"]))
        if key == last_key and segments:
            segment = segments[-1]
            segment["last_receive_monotonic"] = round(
                float(event["receive_monotonic"]), 6
            )
            segment["count"] += 1
            continue
        segments.append(
            {
                "mode": str(event["mode"]),
                "armed": bool(event["armed"]),
                "first_receive_monotonic": round(
                    float(event["receive_monotonic"]), 6
                ),
                "last_receive_monotonic": round(
                    float(event["receive_monotonic"]), 6
                ),
                "count": 1,
            }
        )
        last_key = key
    return segments


class Channel:
    """Bounded per-channel accumulator for count and z samples."""

    def __init__(self):
        self.count = 0
        self.z_samples = deque(maxlen=MAX_Z_SAMPLES)

    def add(self, z=None):
        self.count += 1
        if z is not None:
            self.z_samples.append(float(z))


class UavRecorder:
    """Per-UAV recorder state and summary builder."""

    def __init__(self, uav, min_z, max_z):
        self.uav_id = uav["uav_id"]
        self.namespace = uav["namespace"]
        self.min_z = float(min_z)
        self.max_z = float(max_z)
        self.topics = {
            "planner": uav["planner_cmd_topic"],
            "setpoint": uav["mavros_setpoint_topic"],
            "slam_raw": f"{uav['slam_namespace']}/odometry_raw",
            "odom_out": uav["slam_odom_topic"],
            "odom_in": f"{uav['namespace']}/mavros/odometry/in",
            "local": uav["mavros_feedback_odom_topic"],
            "state": uav["mavros_state_topic"],
        }
        self.channels = {
            name: Channel()
            for name in (
                "planner",
                "setpoint",
                "slam_raw",
                "odom_out",
                "odom_in",
                "local",
            )
        }
        self.setpoint_z_ignored = 0
        self.setpoint_frames = {}
        self.mode_events = []
        self.last_state_key = None

    def z_summary(self, channel_name):
        return summarize_z_samples(
            list(self.channels[channel_name].z_samples),
            self.min_z,
            self.max_z,
        )

    def summary(self):
        setpoint_channel = self.channels["setpoint"]
        return {
            "planner_command_count": self.channels["planner"].count,
            "planner_z": self.z_summary("planner"),
            "setpoint_target_count": setpoint_channel.count,
            "setpoint_z_commanded": self.z_summary("setpoint"),
            "setpoint_z_ignored_count": self.setpoint_z_ignored,
            "setpoint_frames": dict(self.setpoint_frames),
            "slam_raw_odometry_count": self.channels["slam_raw"].count,
            "slam_raw_odometry_z": self.z_summary("slam_raw"),
            "mavros_odom_out_count": self.channels["odom_out"].count,
            "mavros_odom_out_z": self.z_summary("odom_out"),
            "mavros_odom_in_count": self.channels["odom_in"].count,
            "mavros_odom_in_z": self.z_summary("odom_in"),
            "local_position_count": self.channels["local"].count,
            "local_position_z": self.z_summary("local"),
            "mode_changes": summarize_mode_changes(self.mode_events),
        }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_summary(config, args, recorder_map):
    watchdog = {}
    if args.watchdog_dir:
        for uav_id in recorder_map:
            candidate = Path(args.watchdog_dir) / f"{uav_id}_watchdog_events.jsonl"
            watchdog[uav_id] = {
                "path": str(candidate),
                "exists": candidate.exists(),
            }
    return {
        "backend": args.backend,
        "run_id": args.run_id,
        "simulation_instance_id": args.simulation_instance_id,
        "duration_s": args.duration_s,
        "geofence_z": [args.min_z, args.max_z],
        "output": str(args.output),
        "watchdog_dir": str(args.watchdog_dir) if args.watchdog_dir else None,
        "watchdog": watchdog,
        "uavs": {
            uav_id: recorder.summary()
            for uav_id, recorder in recorder_map.items()
        },
    }


def validate_config(config):
    if config.get("mission_mode") != "live_slam_ego_swarm_flight":
        raise ValueError("config mission_mode must be live_slam_ego_swarm_flight")
    uavs = config.get("uavs")
    if not isinstance(uavs, list) or len(uavs) != 2:
        raise ValueError("config must contain exactly two UAV entries")
    for index, uav in enumerate(uavs):
        for field in (
            "uav_id",
            "namespace",
            "slam_namespace",
            "planner_cmd_topic",
            "mavros_setpoint_topic",
            "slam_odom_topic",
            "mavros_feedback_odom_topic",
            "mavros_state_topic",
        ):
            if not uav.get(field):
                raise ValueError(f"uavs[{index}] missing required field '{field}'")


def run_ros(config, args, log_file, recorder_map):
    import rospy
    from mavros_msgs.msg import PositionTarget, State
    from nav_msgs.msg import Odometry
    from quadrotor_msgs.msg import PositionCommand

    rospy.init_node(
        "future_aircraft_stage8_control_chain_recorder", anonymous=True
    )

    def stamp_secs(stamp):
        return stamp.secs + stamp.nsecs * 1e-9

    def write_event(recorder, event):
        log_file.write(json.dumps(event, sort_keys=True) + "\n")
        log_file.flush()

    def rounded_position(position):
        return [
            round(float(position.x), 6),
            round(float(position.y), 6),
            round(float(position.z), 6),
        ]

    def on_planner(message, recorder):
        recorder.channels["planner"].add(float(message.position.z))
        write_event(
            recorder,
            control_event(
                "planner_command",
                recorder.uav_id,
                time.time(),
                time.monotonic(),
                header_stamp=stamp_secs(message.header.stamp),
                position=rounded_position(message.position),
                yaw=round(float(message.yaw), 6),
            ),
        )

    def on_setpoint(message, recorder):
        commanded = setpoint_z_commanded(message.type_mask)
        recorder.channels["setpoint"].add(
            float(message.position.z) if commanded else None
        )
        if not commanded:
            recorder.setpoint_z_ignored += 1
        frame = int(message.coordinate_frame)
        recorder.setpoint_frames[str(frame)] = (
            recorder.setpoint_frames.get(str(frame), 0) + 1
        )
        write_event(
            recorder,
            control_event(
                "setpoint_target",
                recorder.uav_id,
                time.time(),
                time.monotonic(),
                header_stamp=stamp_secs(message.header.stamp),
                coordinate_frame=frame,
                type_mask=int(message.type_mask),
                position=rounded_position(message.position),
                yaw=round(float(message.yaw), 6),
            ),
        )

    def make_odom_callback(channel_name, kind):
        def on_odom(message, recorder):
            pose = message.pose.pose.position
            recorder.channels[channel_name].add(float(pose.z))
            write_event(
                recorder,
                control_event(
                    kind,
                    recorder.uav_id,
                    time.time(),
                    time.monotonic(),
                    header_stamp=stamp_secs(message.header.stamp),
                    frame_id=str(message.header.frame_id),
                    position=rounded_position(pose),
                ),
            )

        return on_odom

    def on_state(message, recorder):
        monotonic = time.monotonic()
        key = (str(message.mode), bool(message.armed))
        if recorder.last_state_key == key:
            return
        recorder.last_state_key = key
        recorder.mode_events.append(
            {
                "mode": str(message.mode),
                "armed": bool(message.armed),
                "receive_monotonic": monotonic,
            }
        )
        write_event(
            recorder,
            control_event(
                "state_change",
                recorder.uav_id,
                time.time(),
                monotonic,
                mode=str(message.mode),
                armed=bool(message.armed),
                connected=bool(message.connected),
            ),
        )

    for uav in config["uavs"]:
        recorder = recorder_map[uav["uav_id"]]
        rospy.Subscriber(
            recorder.topics["planner"],
            PositionCommand,
            lambda message, r=recorder: on_planner(message, r),
            queue_size=100,
        )
        rospy.Subscriber(
            recorder.topics["setpoint"],
            PositionTarget,
            lambda message, r=recorder: on_setpoint(message, r),
            queue_size=100,
        )
        rospy.Subscriber(
            recorder.topics["state"],
            State,
            lambda message, r=recorder: on_state(message, r),
            queue_size=10,
        )
        for channel_name, kind in (
            ("slam_raw", "slam_raw_odometry"),
            ("odom_out", "mavros_odom_out"),
            ("odom_in", "mavros_odom_in"),
            ("local", "local_position"),
        ):
            callback = make_odom_callback(channel_name, kind)
            rospy.Subscriber(
                recorder.topics[channel_name],
                Odometry,
                lambda message, cb=callback, r=recorder: cb(message, r),
                queue_size=100,
            )

    deadline = time.monotonic() + float(args.duration_s)
    rate = rospy.Rate(20.0)
    while not rospy.is_shutdown() and time.monotonic() < deadline:
        rate.sleep()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--backend", choices=("dry-run", "ros"), default="dry-run"
    )
    parser.add_argument("--duration-s", type=float, default=120.0)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--simulation-instance-id", default=None)
    parser.add_argument("--watchdog-dir", type=Path, default=None)
    parser.add_argument("--min-z", type=float, default=0.0)
    parser.add_argument("--max-z", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if args.max_z <= args.min_z:
        parser.error("--max-z must be greater than --min-z")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    recorder_map = {
        uav["uav_id"]: UavRecorder(uav, args.min_z, args.max_z)
        for uav in config["uavs"]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.backend == "dry-run":
        args.output.write_text("", encoding="utf-8")
    else:
        with args.output.open("w", encoding="utf-8") as log_file:
            run_ros(config, args, log_file, recorder_map)
    summary_path = args.output.with_name(args.output.stem + "_summary.json")
    write_json(summary_path, build_summary(config, args, recorder_map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
