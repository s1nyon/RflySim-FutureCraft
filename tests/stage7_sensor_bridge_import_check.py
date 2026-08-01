#!/usr/bin/env python3
"""Contract check for project-local RflySimSDK sensor bridge imports."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_bridge(module_path: Path):
    spec = importlib.util.spec_from_file_location("rflysim_sensor_bridge", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sensor bridge module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    parser.add_argument("--psp-path", required=True)
    args = parser.parse_args()

    sdk_root = str(Path(args.psp_path) / "RflySimAPIs/RflySimSDK")
    sdk_ue = str(Path(args.psp_path) / "RflySimAPIs/RflySimSDK/ue")
    sys.path[:] = [value for value in sys.path if value != sdk_root]
    sys.path[:] = [value for value in sys.path if value != sdk_ue]

    bridge = load_bridge(Path(args.module))
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
