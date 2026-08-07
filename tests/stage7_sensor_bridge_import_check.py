#!/usr/bin/env python3
"""Contract check for project-local RflySimSDK sensor bridge imports."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
from pathlib import Path


def load_bridge(module_path: Path):
    spec = importlib.util.spec_from_file_location("rflysim_sensor_bridge", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sensor bridge module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def expect_failure(message_fragment: str):
    try:
        yield
    except ValueError as exc:
        assert message_fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected ValueError containing {message_fragment!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    parser.add_argument("--psp-path", required=True)
    parser.add_argument("--config", type=Path, default=Path("config/rflysim_sensor_uav2.json"))
    args = parser.parse_args()

    sdk_root = str(Path(args.psp_path) / "RflySimAPIs/RflySimSDK")
    sdk_ue = str(Path(args.psp_path) / "RflySimAPIs/RflySimSDK/ue")
    sys.path[:] = [value for value in sys.path if value != sdk_root]
    sys.path[:] = [value for value in sys.path if value != sdk_ue]

    bridge = load_bridge(Path(args.module))

    sensor = bridge.validate_sensor_config(args.config, 2, 10, 10009)
    identity_args = argparse.Namespace(
        copter_id=2,
        sensor_seq_id=10,
        udp_port=10009,
        raw_lidar_topic="/rflysim/sensor10/mid360_lidar",
        raw_imu_topic="/uav2/rflysim/imu_raw",
        identity_topic="/uav2/rflysim/sensor_identity",
        process_start_marker="run-1:uav2:bridge",
        sensor_mode="lidar_only",
    )
    identity = bridge.build_identity(identity_args, sensor, "127.0.0.1")
    assert identity["copter_id"] == 2
    assert identity["sensor_seq_id"] == 10
    assert identity["udp_port"] == 10009
    assert identity["raw_lidar_topic"] == "/rflysim/sensor10/mid360_lidar"
    assert identity["process_start_marker"] == "run-1:uav2:bridge"
    assert identity["sensor_mode"] == "lidar_only"

    # lidar-only runtime must hand the SDK a config with only the matching sensor.
    filtered = bridge.filtered_sensor_config(args.config, sensor)
    assert [entry["SeqID"] for entry in filtered["VisionSensors"]] == [10]

    with expect_failure("TargetCopter"):
        bridge.validate_sensor_config(args.config, 1, 10, 10009)

    events = []

    class FakeRequester:
        def __init__(self):
            events.append("requester")

        def getSimIpID(self, copter_id):
            assert copter_id == 2
            return "127.0.0.1"

        def sendReSimIP(self, copter_id):
            assert copter_id == 2
            events.append("request_sim")

    class FakeVisionBridge:
        def __init__(self, target_ip):
            assert target_ip == "127.0.0.1"
            events.append("sdk_ros_init")

        def jsonLoad(self, change_mode, config_path):
            assert change_mode == 1
            events.append(("json_load", config_path))

        def sendReqToUE4(self, window_id, target_ip):
            assert (window_id, target_ip) == (0, "127.0.0.1")
            events.append("request_ue4")

        def startImgCap(self):
            events.append("start_capture")

        def sendImuReqCopterSim(self, copter_id, target_ip, rate_hz):
            assert (copter_id, target_ip, rate_hz) == (2, "127.0.0.1", 200)
            events.append("request_imu")

        def stopRun(self):
            events.append("stop_bridge")

    start_args = argparse.Namespace(
        psp_path=Path(args.psp_path),
        config=args.config,
        change_mode=1,
        copter_id=2,
        sensor_seq_id=10,
        udp_port=10009,
        raw_lidar_topic="/rflysim/sensor10/mid360_lidar",
        raw_imu_topic="/uav2/rflysim/imu_raw",
        identity_topic="/uav2/rflysim/sensor_identity",
        process_start_marker="run-1:uav2:bridge",
        imu_rate_hz=200,
        sensor_mode="lidar_only",
    )

    def fake_publish_identity(value, topic):
        assert value["sensor_seq_id"] == 10
        assert topic == "/uav2/rflysim/sensor_identity"
        events.append("publish_identity")
        return object()

    _, _, bridge_handle = bridge.start_bridge(
        start_args,
        sensor,
        requester_factory=FakeRequester,
        bridge_factory=FakeVisionBridge,
        identity_publisher=fake_publish_identity,
    )
    json_loads = [
        event[1]
        for event in events
        if isinstance(event, tuple) and event[0] == "json_load"
    ]
    assert len(json_loads) == 1, events
    loaded = json.loads(Path(json_loads[0]).read_text(encoding="utf-8"))
    assert [entry["SeqID"] for entry in loaded["VisionSensors"]] == [10]
    assert events.index("sdk_ros_init") < events.index("publish_identity"), events
    bridge.stop_bridge(bridge_handle)
    assert events[-1] == "stop_bridge", events

    # full mode must hand the SDK the complete sensor config.
    full_events = []

    class FullBridge:
        def __init__(self, target_ip):
            full_events.append("init")

        def jsonLoad(self, change_mode, config_path):
            full_events.append(config_path)

        def sendReqToUE4(self, window_id, target_ip):
            pass

        def startImgCap(self):
            pass

        def sendImuReqCopterSim(self, copter_id, target_ip, rate_hz):
            pass

        def stopRun(self):
            full_events.append("stop")

    class FullRequester:
        def getSimIpID(self, copter_id):
            return "127.0.0.1"

        def sendReSimIP(self, copter_id):
            pass

    full_start_args = argparse.Namespace(**{**vars(start_args), "sensor_mode": "full"})
    _, _, full_bridge = bridge.start_bridge(
        full_start_args,
        sensor,
        requester_factory=FullRequester,
        bridge_factory=FullBridge,
        identity_publisher=lambda value, topic: object(),
    )
    assert full_events[1] == str(args.config), full_events
    bridge.stop_bridge(full_bridge)
    assert full_events[-1] == "stop", full_events

    bridge.add_sdk_paths(args.psp_path)
    assert sdk_root in sys.path, "RflySimSDK root must be on sys.path for ctrl.* imports"
    assert sdk_ue in sys.path, "RflySimSDK ue path must be on sys.path for UE4CtrlAPI imports"

    import ReqCopterSim  # noqa: F401
    import UE4CtrlAPI  # noqa: F401
    import VisionCaptureApi  # noqa: F401
    import ctrl.IpManager  # noqa: F401

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
