#!/usr/bin/env python3
"""Read-only evidence checker for the PX4-to-MAVROS MAVLink return path."""

import argparse
import json
import re
from pathlib import Path


REQUIRED_CONFIG = {
    "stage": "2.1",
    "uav_id": "uav1",
    "namespace": "/uav1",
    "fcu_url": "udp://:16540@127.0.0.1:17540",
    "px4_instance": 1,
    "px4_out_log": "/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/instance_1/out.log",
    "timeout_s": 10,
    "state_topic": "/uav1/mavros/state",
    "odom_topic": "/uav1/mavros/local_position/odom",
    "set_mode_service": "/uav1/mavros/set_mode",
    "arming_service": "/uav1/mavros/cmd/arming",
}


def load_config(path):
    """Load and validate the deliberately fixed single-UAV contract."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("invalid Stage 2.1 config: {}".format(exc))
    if value != REQUIRED_CONFIG:
        raise ValueError("Stage 2.1 config does not match the fixed /uav1 contract")
    return value


def parse_px4_mavlink_status(text):
    """Extract bidirectional link evidence from the final PX4 channel-zero block."""
    if not text:
        return None
    starts = list(re.finditer(r"(?im)^.*\bmavlink\s+chan:\s*#0\b.*$", text))
    if not starts:
        return None
    block = text[starts[-1].start():]
    udp = re.search(r"UDP\s*\(\s*(\d+)\s*,\s*remote\s+port:\s*(\d+)\s*\)", block)
    partner = re.search(r"partner\s+IP:\s*([^\s]+)", block, re.IGNORECASE)
    received = re.search(
        r"received\s+from\s+sysid:\s*1\s+compid:\s*240\b[^\n]*?(?:\b([1-9]\d*)\b)?",
        block,
        re.IGNORECASE,
    )
    if not udp or not partner or not received:
        return None
    return {
        "started": True,
        "mavlink_local_port": int(udp.group(1)),
        "mavlink_remote_port": int(udp.group(2)),
        "partner_ip": partner.group(1),
        "received_mavros_traffic": True,
    }


def classify_report(px4, mavros):
    if not px4.get("started"):
        return "px4_not_started"
    if not mavros.get("state_topic_present"):
        return "mavros_not_started"
    if px4.get("received_mavros_traffic") and (
        not mavros.get("connected") or not mavros.get("odom_received")
    ):
        return "px4_to_mavros_return_path_blocked"
    if not px4.get("received_mavros_traffic"):
        return "mavros_to_px4_path_blocked"
    if all((mavros.get("connected"), mavros.get("odom_received"),
            mavros.get("set_mode_service"), mavros.get("arming_service"))):
        return "ready"
    return "inconclusive"


def _wait_for_any_message(rospy, topic, timeout_s):
    return rospy.wait_for_message(topic, object, timeout=timeout_s) is not None


def _wait_for_service(rospy, service, timeout_s):
    rospy.wait_for_service(service, timeout=timeout_s)
    return True


def _sample_ros(config):
    """Collect ROS observations without publishing or invoking a service."""
    errors = []
    mavros = {
        "state_topic_present": False,
        "connected": False,
        "odom_received": False,
        "set_mode_service": False,
        "arming_service": False,
    }
    try:
        import rospy
        from mavros_msgs.msg import State
        if not rospy.core.is_initialized():
            rospy.init_node("mavlink_return_path_check", anonymous=True, disable_signals=True)
        try:
            state = rospy.wait_for_message(config["state_topic"], State, timeout=config["timeout_s"])
            mavros["state_topic_present"] = True
            mavros["connected"] = bool(state.connected)
        except Exception as exc:  # ROS exceptions differ between Noetic installs.
            errors.append("state: {}".format(exc))
        for key, operation, target in (
            ("odom_received", _wait_for_any_message, config["odom_topic"]),
            ("set_mode_service", _wait_for_service, config["set_mode_service"]),
            ("arming_service", _wait_for_service, config["arming_service"]),
        ):
            try:
                mavros[key] = bool(operation(rospy, target, config["timeout_s"]))
            except Exception as exc:
                errors.append("{}: {}".format(key, exc))
    except Exception as exc:
        errors.append("ros import/init: {}".format(exc))
    return mavros, errors


def _px4_evidence(px4_log_text):
    if px4_log_text is None:
        return {"started": False}
    parsed = parse_px4_mavlink_status(px4_log_text[-16 * 1024:])
    if parsed is not None:
        return parsed
    return {"started": True, "evidence_complete": False}


def build_report(config, backend, px4_log_text=None):
    if backend == "dry-run":
        px4 = {"started": True, "evidence_complete": False}
        mavros = {
            "state_topic_present": True,
            "connected": True,
            "odom_received": True,
            "set_mode_service": True,
            "arming_service": True,
        }
        return {"backend": "dry-run", "status": "inconclusive", "classification": "inconclusive",
                "px4": px4, "mavros": mavros, "errors": [], "live_actions": []}
    px4 = _px4_evidence(px4_log_text)
    mavros, errors = _sample_ros(config)
    classification = "inconclusive" if not px4.get("evidence_complete", True) else classify_report(px4, mavros)
    return {"backend": "ros", "status": classification,
            "classification": classification, "px4": px4, "mavros": mavros,
            "errors": errors, "live_actions": []}


def write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--backend", choices=("dry-run", "ros"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--px4-log", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    px4_text = None
    if args.px4_log:
        try:
            px4_text = args.px4_log.read_text(encoding="utf-8", errors="replace")[-16 * 1024:]
        except OSError:
            px4_text = None
    report = build_report(config, args.backend, px4_text)
    write_report(args.report, report)
    return 0 if args.backend == "dry-run" or report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
