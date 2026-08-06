#!/usr/bin/env python3
"""Land a simulated UAV when its state leaves the hard course geofence."""

from __future__ import annotations

import argparse
import json
import math
import time

from course_geofence import Geofence, watchdog_decision_with_reason


def decision_event(
    *,
    position,
    speed_mps,
    odom_age_s,
    armed,
    mode,
    mode_grace_active,
    decision,
    reason,
    timestamp,
):
    return {
        "timestamp": round(float(timestamp), 3),
        "position": [round(float(value), 3) for value in position],
        "speed_mps": round(float(speed_mps), 3),
        "odom_age_s": round(float(odom_age_s), 3),
        "armed": bool(armed),
        "mode": str(mode),
        "mode_grace_active": bool(mode_grace_active),
        "decision": str(decision),
        "reason": str(reason),
    }


def watchdog_node_name(state_topic: str) -> str:
    parts = [part for part in str(state_topic).split("/") if part]
    namespace = parts[0] if parts else "vehicle"
    return "course_geofence_watchdog_" + namespace.replace("-", "_")


def next_armed_since(current, *, armed: bool, now: float):
    if not armed:
        return None
    return float(now) if current is None else current


def mode_grace_active(armed_since, *, now: float, grace_s: float) -> bool:
    return armed_since is not None and float(now) - float(armed_since) < float(grace_s)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-topic", required=True)
    parser.add_argument("--odom-topic", required=True)
    parser.add_argument("--set-mode-service", required=True)
    for name in ("min-x", "max-x", "min-y", "max-y", "min-z", "max-z", "max-speed-mps", "max-odom-age-s"):
        parser.add_argument("--" + name, required=True, type=float)
    parser.add_argument("--mode-grace-s", type=float, default=2.0)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args(argv)
    if args.rate_hz < 10.0:
        parser.error("--rate-hz must be at least 10")
    if args.mode_grace_s <= 0.0:
        parser.error("--mode-grace-s must be positive")

    import rospy
    from mavros_msgs.msg import State
    from mavros_msgs.srv import SetMode
    from nav_msgs.msg import Odometry

    fence = Geofence(args.min_x, args.max_x, args.min_y, args.max_y, args.min_z, args.max_z, args.max_speed_mps, args.max_odom_age_s)
    rospy.init_node(watchdog_node_name(args.state_topic), anonymous=False)
    state = {"message": None, "received": 0.0, "armed_since": None}
    odom = {"message": None, "received": 0.0}

    def state_callback(message):
        now = time.monotonic()
        state["armed_since"] = next_armed_since(
            state["armed_since"], armed=bool(message.armed), now=now
        )
        state.update(message=message, received=now)

    rospy.Subscriber(args.state_topic, State, state_callback, queue_size=1)
    rospy.Subscriber(args.odom_topic, Odometry, lambda message: odom.update(message=message, received=time.monotonic()), queue_size=1)
    rospy.wait_for_service(args.set_mode_service, timeout=10.0)
    set_mode = rospy.ServiceProxy(args.set_mode_service, SetMode)
    rate = rospy.Rate(args.rate_hz)
    landed = False
    last_state_key = None
    decision_log = open(args.output, "a", encoding="utf-8") if args.output else None
    while not rospy.is_shutdown():
        if state["message"] is not None and odom["message"] is not None:
            position = odom["message"].pose.pose.position
            twist = odom["message"].twist.twist.linear
            speed = math.sqrt(float(twist.x) ** 2 + float(twist.y) ** 2 + float(twist.z) ** 2)
            now = time.monotonic()
            decision, reason = watchdog_decision_with_reason(
                (position.x, position.y, position.z),
                fence,
                armed=bool(state["message"].armed),
                mode=str(state["message"].mode),
                odom_age_s=now - odom["received"],
                speed_mps=speed,
                mode_grace_active=mode_grace_active(
                    state["armed_since"], now=now, grace_s=args.mode_grace_s
                ),
            )
            state_key = (
                decision,
                reason,
                round(float(position.x), 3),
                round(float(position.y), 3),
                round(float(position.z), 3),
                round(speed, 3),
                round(now - odom["received"], 3),
                bool(state["message"].armed),
                str(state["message"].mode),
            )
            if state_key != last_state_key:
                event = decision_event(
                    position=(position.x, position.y, position.z),
                    speed_mps=speed,
                    odom_age_s=now - odom["received"],
                    armed=bool(state["message"].armed),
                    mode=str(state["message"].mode),
                    mode_grace_active=mode_grace_active(
                        state["armed_since"], now=now, grace_s=args.mode_grace_s
                    ),
                    decision=decision,
                    reason=reason,
                    timestamp=now,
                )
                if decision_log is not None:
                    decision_log.write(json.dumps(event, sort_keys=True) + "\n")
                    decision_log.flush()
                last_state_key = state_key
            if decision == "land" and not landed:
                rospy.logerr("course geofence violated; requesting AUTO.LAND")
                set_mode(custom_mode="AUTO.LAND")
                landed = True
        rate.sleep()
    if decision_log is not None:
        decision_log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
