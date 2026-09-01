#!/usr/bin/env python3
"""Read-only RflySim3D view command helper for map acceptance screenshots."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", required=True)
    parser.add_argument("--window-id", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")))
    args = parser.parse_args()
    api_dir = args.rflysim_root / "RflySimAPIs/RflySimSDK/ue"
    if not api_dir.is_dir():
        raise RuntimeError("RflySim UE API directory missing: {}".format(api_dir))
    sys.path.insert(0, str(api_dir))
    import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel
    api = UE4CtrlAPI.UE4CtrlAPI()
    api.sendUE4Cmd(args.command, args.window_id)
    if args.sleep > 0:
        time.sleep(args.sleep)
    print(json_dump({"command": args.command, "window_id": args.window_id}))
    return 0


def json_dump(value) -> str:
    import json
    return json.dumps(value, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
