#!/usr/bin/env python3
"""Start RflySim ROS sensor publishing without starting or replacing MAVROS."""

import argparse
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


def start_bridge(args):
    add_sdk_paths(args.psp_path)
    import ReqCopterSim
    import VisionCaptureApi

    VisionCaptureApi.isEnableRosTrans = True

    requester = ReqCopterSim.ReqCopterSim()
    target_ip = requester.getSimIpID(args.copter_id)
    requester.sendReSimIP(args.copter_id)

    bridge = VisionCaptureApi.VisionCaptureApi(target_ip)
    if args.config:
        bridge.jsonLoad(args.change_mode, str(args.config))
    else:
        bridge.jsonLoad(args.change_mode)
    bridge.sendReqToUE4(0, target_ip)
    bridge.startImgCap()
    bridge.sendImuReqCopterSim(args.copter_id, target_ip, args.imu_rate_hz)
    return target_ip


def main(argv=None):
    parser = argparse.ArgumentParser(description="RflySim sensor bridge without MAVROS orchestration")
    parser.add_argument("--psp-path", default="/mnt/d/PX4PSP", help="WSL path to the PX4PSP root")
    parser.add_argument("--config", type=Path, help="VisionCaptureApi Config.json path")
    parser.add_argument("--change-mode", type=int, default=1, help="VisionCaptureApi jsonLoad ChangeMode")
    parser.add_argument("--copter-id", type=int, default=1, help="CopterSim ID to request")
    parser.add_argument("--imu-rate-hz", type=int, default=200, help="IMU request frequency")
    parser.add_argument("--keepalive", action="store_true", help="Keep the bridge process alive")
    args = parser.parse_args(argv)

    try:
        target_ip = start_bridge(args)
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
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
