#!/usr/bin/env python3
"""Start RflySim ROS sensor publishing without starting or replacing MAVROS."""

import argparse
import json
import signal
import sys
import time
from pathlib import Path


def add_sdk_paths(psp_path):
    root = Path(psp_path)
    for relative in (
        "RflySimAPIs/RflySimSDK",
        "RflySimAPIs/RflySimSDK/vision",
        "RflySimAPIs/RflySimSDK/ctrl",
        "RflySimAPIs/RflySimSDK/ue",
    ):
        value = str(root / relative)
        if value not in sys.path:
            sys.path.insert(0, value)


def validate_sensor_config(config_path: Path, copter_id: int, sensor_seq_id: int, udp_port: int) -> dict:
    """Return the uniquely matching sensor after validating its bridge identity."""
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load sensor config {config_path}: {exc}") from exc

    sensors = config.get("VisionSensors")
    if not isinstance(sensors, list):
        raise ValueError("VisionSensors must be a list")
    matches = [sensor for sensor in sensors if sensor.get("SeqID") == sensor_seq_id]
    if len(matches) != 1:
        raise ValueError(f"SeqID {sensor_seq_id} must identify exactly one VisionSensors entry")

    sensor = matches[0]
    if sensor.get("TargetCopter") != copter_id:
        raise ValueError(
            f"TargetCopter mismatch: expected {copter_id}, got {sensor.get('TargetCopter')}"
        )
    protocol = sensor.get("SendProtocol")
    if not isinstance(protocol, list) or len(protocol) < 6:
        raise ValueError("SendProtocol must contain the UDP port at index 5")
    if protocol[5] != udp_port:
        raise ValueError(f"SendProtocol[5] mismatch: expected {udp_port}, got {protocol[5]}")
    return sensor


def build_identity(args, sensor: dict, target_ip: str) -> dict:
    """Build the declarative bridge identity published before sensor requests."""
    return {
        "copter_id": args.copter_id,
        "identity_topic": args.identity_topic,
        "process_start_marker": args.process_start_marker,
        "raw_imu_topic": args.raw_imu_topic,
        "raw_imu_topic_verified": False,
        "raw_lidar_topic": args.raw_lidar_topic,
        "runtime_probe_required": True,
        "sensor_seq_id": sensor["SeqID"],
        "target_ip": target_ip,
        "udp_port": args.udp_port,
    }


def publish_identity(identity: dict, identity_topic: str):
    """Publish identity once as a latched ROS 1 String message."""
    import rospy
    from std_msgs.msg import String

    publisher = rospy.Publisher(identity_topic, String, queue_size=1, latch=True)
    publisher.publish(String(data=json.dumps(identity, sort_keys=True)))
    return publisher


def start_bridge(args, sensor: dict):
    add_sdk_paths(args.psp_path)
    import ReqCopterSim
    import VisionCaptureApi

    VisionCaptureApi.isEnableRosTrans = True

    requester = ReqCopterSim.ReqCopterSim()
    target_ip = requester.getSimIpID(args.copter_id)
    identity = build_identity(args, sensor, target_ip)
    identity_publisher = publish_identity(identity, args.identity_topic)
    requester.sendReSimIP(args.copter_id)

    bridge = VisionCaptureApi.VisionCaptureApi(target_ip)
    if args.config:
        bridge.jsonLoad(args.change_mode, str(args.config))
    else:
        bridge.jsonLoad(args.change_mode)
    bridge.sendReqToUE4(0, target_ip)
    bridge.startImgCap()
    bridge.sendImuReqCopterSim(args.copter_id, target_ip, args.imu_rate_hz)
    return target_ip, identity_publisher


def main(argv=None):
    parser = argparse.ArgumentParser(description="RflySim sensor bridge without MAVROS orchestration")
    parser.add_argument("--psp-path", default="/mnt/d/PX4PSP", help="WSL path to the PX4PSP root")
    parser.add_argument("--config", type=Path, help="VisionCaptureApi Config.json path")
    parser.add_argument("--change-mode", type=int, default=1, help="VisionCaptureApi jsonLoad ChangeMode")
    parser.add_argument("--copter-id", type=int, default=1, help="CopterSim ID to request")
    parser.add_argument("--sensor-seq-id", type=int, default=0, help="Validated VisionSensors SeqID")
    parser.add_argument("--udp-port", type=int, default=9999, help="Validated VisionSensors SendProtocol UDP port")
    parser.add_argument(
        "--raw-lidar-topic",
        default="/rflysim/sensor0/mid360_lidar",
        help="Declared SDK lidar topic for this sensor sequence",
    )
    parser.add_argument(
        "--raw-imu-topic",
        default="/rflysim/imu",
        help="Declared IMU remap source; Task 5 must verify the SDK-resolved topic",
    )
    parser.add_argument(
        "--identity-topic",
        default="/rflysim/sensor_identity",
        help="Latched bridge identity topic",
    )
    parser.add_argument(
        "--process-start-marker",
        default="",
        help="Run-scoped marker proving this bridge was started for the current readiness run",
    )
    parser.add_argument("--imu-rate-hz", type=int, default=200, help="IMU request frequency")
    parser.add_argument("--keepalive", action="store_true", help="Keep the bridge process alive")
    args, unknown = parser.parse_known_args(argv)
    invalid_unknown = [value for value in unknown if ":=" not in value]
    if invalid_unknown:
        parser.error(f"unrecognized arguments: {' '.join(invalid_unknown)}")

    try:
        if args.config is None:
            raise ValueError("--config is required to validate bridge identity")
        if not args.process_start_marker:
            raise ValueError("--process-start-marker is required for run-scoped bridge identity")
        sensor = validate_sensor_config(args.config, args.copter_id, args.sensor_seq_id, args.udp_port)

        import rospy

        if not rospy.core.is_initialized():
            rospy.init_node("rflysim_sensor_bridge", anonymous=False)

        target_ip, identity_publisher = start_bridge(args, sensor)
        print(f"[INFO] RflySim sensor bridge started for CopterSim {args.copter_id} at {target_ip}", flush=True)
        if args.keepalive:
            stop = False

            def _stop(_signum, _frame):
                nonlocal stop
                stop = True

            signal.signal(signal.SIGINT, _stop)
            signal.signal(signal.SIGTERM, _stop)
            while not stop:
                time.sleep(1.0)
        del identity_publisher
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
