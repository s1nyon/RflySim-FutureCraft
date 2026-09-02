#!/usr/bin/env python3
"""Record collision and emergency flight events to a run-scoped JSONL file.

Emergency events include arming/mode changes, OFFBOARD mode loss, NaN or
out-of-geofence odometry, and max-speed violations. Collision events come from
RflySim3D's crash data (UE4CtrlAPI, 160-byte reqVeCrashData on UDP 20006);
the collision engine must be enabled (RflyChangeViewKeyCmd P).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path


def classify_mode_event(uav, prev_mode, mode, armed, timestamp, prev_armed=None):
    if prev_armed is not None and bool(prev_armed) != bool(armed):
        return {
            "timestamp": round(float(timestamp), 3),
            "uav": uav,
            "event": "arming",
            "armed": bool(armed),
        }
    if prev_mode != mode:
        if prev_mode == "OFFBOARD" and mode != "OFFBOARD" and armed:
            return {
                "timestamp": round(float(timestamp), 3),
                "uav": uav,
                "event": "mode_loss",
                "prev_mode": prev_mode,
                "mode": mode,
                "armed": bool(armed),
            }
        return {
            "timestamp": round(float(timestamp), 3),
            "uav": uav,
            "event": "mode_change",
            "prev_mode": prev_mode,
            "mode": mode,
            "armed": bool(armed),
        }
    return None


def detect_odom_anomaly(position, speed_mps, geofence, max_speed_mps=2.0):
    x, y, z = (float(value) for value in position)
    if not all(math.isfinite(value) for value in (x, y, z)):
        return "nan_position"
    min_x, max_x, min_y, max_y, min_z, max_z = geofence
    if not (min_x <= x <= max_x and min_y <= y <= max_y and min_z <= z <= max_z):
        return "outside_geofence"
    if not math.isfinite(float(speed_mps)) or float(speed_mps) > max_speed_mps:
        return "max_speed"
    return None


def crash_event(copter_id, crash_type, position_ned, crash_pos_ned, crashed_name, timestamp):
    return {
        "timestamp": round(float(timestamp), 3),
        "copter_id": int(copter_id),
        "event": "collision",
        "crash_type": int(crash_type),
        "position_ned": [round(float(value), 3) for value in position_ned],
        "crash_pos_ned": [round(float(value), 3) for value in crash_pos_ned],
        "crashed_name": str(crashed_name),
    }


def _write_event(path, event):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def write_crash_monitor_status(path, *, available, monitor_started_wall_time=None,
                               last_heartbeat_wall_time=None, error=None):
    """Atomically expose crash-listener availability to an acceptance runner."""
    value = {
        "available": bool(available),
        "error": str(error) if error is not None else None,
        "last_heartbeat_wall_time": (
            float(last_heartbeat_wall_time) if last_heartbeat_wall_time is not None else None
        ),
        "monitor_started_wall_time": (
            float(monitor_started_wall_time) if monitor_started_wall_time is not None else None
        ),
        "source": "rflysim_reqVeCrashData_udp_20006",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _ue4_crash_monitor(rflysim_root, output, status_path=None, interval_s=0.5):
    started = None
    try:
        api_dir = rflysim_root / "RflySimAPIs" / "RflySimSDK" / "ue"
        if not api_dir.is_dir():
            raise RuntimeError(f"RflySim UE API directory does not exist: {api_dir}")
        sys.path.insert(0, str(api_dir))
        import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel

        client = UE4CtrlAPI.UE4CtrlAPI()
        started = time.time()
        seen = set()
        while True:
            try:
                for item in client.inReqVect:
                    if item.crash_type != 0:
                        key = (
                            item.copter_id,
                            item.crash_type,
                            tuple(round(float(v), 3) for v in item.crash_pos),
                        )
                        if key not in seen:
                            seen.add(key)
                            _write_event(
                                output,
                                crash_event(
                                    copter_id=item.copter_id,
                                    crash_type=item.crash_type,
                                    position_ned=item.pos_e,
                                    crash_pos_ned=item.crash_pos,
                                    crashed_name=item.crashed_name,
                                    timestamp=time.time(),
                                ),
                            )
            except Exception as exc:  # allow a later poll to recover
                if status_path is not None:
                    write_crash_monitor_status(
                        status_path,
                        available=False,
                        monitor_started_wall_time=started,
                        last_heartbeat_wall_time=time.time(),
                        error=exc,
                    )
                print(f"[WARN] crash monitor iteration failed: {exc}", file=sys.stderr)
                time.sleep(interval_s)
                continue
            if status_path is not None:
                write_crash_monitor_status(
                    status_path,
                    available=True,
                    monitor_started_wall_time=started,
                    last_heartbeat_wall_time=time.time(),
                )
            time.sleep(interval_s)
    except Exception as exc:
        if status_path is not None:
            write_crash_monitor_status(
                status_path,
                available=False,
                monitor_started_wall_time=started,
                last_heartbeat_wall_time=time.time(),
                error=exc,
            )
        print(f"[ERROR] crash monitor stopped: {exc}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--uav", action="append", default=[], help="Repeatable: uav1 or uav2")
    parser.add_argument("--min-x", type=float, default=-1.0)
    parser.add_argument("--max-x", type=float, default=17.0)
    parser.add_argument("--min-y", type=float, default=-2.0)
    parser.add_argument("--max-y", type=float, default=7.0)
    parser.add_argument("--min-z", type=float, default=-0.5)
    parser.add_argument("--max-z", type=float, default=2.0)
    parser.add_argument("--max-speed-mps", type=float, default=2.0)
    parser.add_argument("--crash-listen", action="store_true")
    parser.add_argument("--crash-status", type=Path)
    parser.add_argument(
        "--rflysim-root",
        type=Path,
        default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")),
    )
    args = parser.parse_args(argv)
    if not args.uav:
        args.uav = ["uav1", "uav2"]

    import rospy
    from mavros_msgs.msg import State
    from nav_msgs.msg import Odometry

    rospy.init_node("future_aircraft_flight_event_recorder", anonymous=True)
    geofence = (args.min_x, args.max_x, args.min_y, args.max_y, args.min_z, args.max_z)
    states = {uav: {"mode": None, "armed": None} for uav in args.uav}

    def state_callback(uav):
        def _callback(message):
            prev = states[uav]
            event = classify_mode_event(
                uav,
                prev["mode"],
                str(message.mode),
                bool(message.armed),
                time.time(),
                prev_armed=prev["armed"],
            )
            if event is not None:
                _write_event(args.output, event)
            states[uav] = {"mode": str(message.mode), "armed": bool(message.armed)}

        return _callback

    def odom_callback(uav):
        def _callback(message):
            position = message.pose.pose.position
            speed = message.twist.twist.linear
            speed_mps = math.sqrt(
                float(speed.x) ** 2 + float(speed.y) ** 2 + float(speed.z) ** 2
            )
            reason = detect_odom_anomaly(
                (position.x, position.y, position.z),
                speed_mps,
                geofence,
                args.max_speed_mps,
            )
            if reason is not None:
                _write_event(
                    args.output,
                    {
                        "timestamp": round(time.time(), 3),
                        "uav": uav,
                        "event": "odom_anomaly",
                        "reason": reason,
                        "position": [
                            round(float(position.x), 3),
                            round(float(position.y), 3),
                            round(float(position.z), 3),
                        ],
                        "speed_mps": round(speed_mps, 3),
                    },
                )

        return _callback

    args.output.parent.mkdir(parents=True, exist_ok=True)
    for uav in args.uav:
        rospy.Subscriber(f"/{uav}/mavros/state", State, state_callback(uav), queue_size=1)
        rospy.Subscriber(
            f"/{uav}/mavros/local_position/odom", Odometry, odom_callback(uav), queue_size=1
        )

    if args.crash_listen:
        import threading

        monitor = threading.Thread(
            target=_ue4_crash_monitor,
            args=(args.rflysim_root, args.output, args.crash_status),
            daemon=True,
        )
        monitor.start()
    rospy.spin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
