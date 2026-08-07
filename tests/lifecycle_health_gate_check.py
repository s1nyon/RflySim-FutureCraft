#!/usr/bin/env python3
"""Health gate contract: schema, all_ready, fail-closed semantics, roundtrip."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def load_module(name: str, module_path: Path):
    module_path = Path(module_path).resolve()
    if module_path.parent.name == "lifecycle":
        sys.path.insert(0, str(module_path.parent.parent))
        import importlib

        importlib.import_module("lifecycle")
        return importlib.import_module(f"lifecycle.{name}")
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-module", required=True, type=Path)
    args = parser.parse_args()

    health_mod = load_module("health_gate", args.health_module)
    assert set(health_mod.HEALTH_STATUSES) == {
        "GUI_READY",
        "ROSCORE_READY",
        "MAVROS_UAV1_CONNECTED",
        "MAVROS_UAV2_CONNECTED",
        "COURSE_READY",
    }

    health = health_mod.new_health("stack-20260808T120000Z-a1b2c3d4")
    for name in health_mod.HEALTH_STATUSES:
        health_mod.merge_status(health, name, ready=True, detail="ok")
    assert health_mod.all_ready(health) is True
    assert health_mod.status_ready(health, "GUI_READY") is True
    health_mod.validate_health(health)

    # any single failure -> all_ready False (fail closed)
    health_mod.merge_status(health, "MAVROS_UAV2_CONNECTED", ready=False, detail="timeout")
    assert health_mod.all_ready(health) is False
    health_mod.validate_health(health)

    # unknown status names are rejected
    try:
        health_mod.merge_status(health, "NOT_A_STATUS", ready=True, detail="x")
        raise AssertionError("unknown health status must be rejected")
    except ValueError:
        pass

    # roundtrip
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "health.json"
        health_mod.save_health(health, path)
        loaded = health_mod.load_health(path)
        assert loaded == health
        assert loaded["stack_id"] == "stack-20260808T120000Z-a1b2c3d4"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
