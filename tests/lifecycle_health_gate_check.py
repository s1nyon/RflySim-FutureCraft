#!/usr/bin/env python3
"""Health gate v2: per-status files, atomic writes, concurrency-safe aggregation."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
import tempfile
import threading
from pathlib import Path


def load_module(name: str, module_path: Path):
    module_path = Path(module_path).resolve()
    if module_path.parent.name == "lifecycle":
        sys.path.insert(0, str(module_path.parent.parent))
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
        "GUI_READY", "ROSCORE_READY", "MAVROS_UAV1_CONNECTED", "MAVROS_UAV2_CONNECTED", "COURSE_READY",
    }

    with tempfile.TemporaryDirectory() as tmp:
        health_dir = Path(tmp)
        stack_id = "stack-20260808T120000Z-a1b2c3d4"

        # Each producer writes ONLY its own status file.
        for name in health_mod.HEALTH_STATUSES:
            health_mod.write_status_file(health_dir, stack_id, name, ready=True, detail="ok")
            assert (health_dir / f"{name}.json").exists()
            assert not (health_dir / "health.json").exists(), "no shared health.json allowed"
        assert health_mod.all_ready(health_dir) is True
        assert health_mod.status_ready(health_dir, "GUI_READY") is True
        summary = health_mod.health_summary(health_dir)
        assert "GUI_READY=READY" in summary and "COURSE_READY=READY" in summary

        # Any failure -> not ready (fail closed).
        health_mod.write_status_file(health_dir, stack_id, "MAVROS_UAV2_CONNECTED", ready=False, detail="timeout")
        assert health_mod.all_ready(health_dir) is False
        health_mod.write_status_file(health_dir, stack_id, "MAVROS_UAV2_CONNECTED", ready=True, detail="ok")

        # Unknown status rejected.
        try:
            health_mod.write_status_file(health_dir, stack_id, "NOT_A_STATUS", ready=True, detail="x")
            raise AssertionError("unknown status must be rejected")
        except ValueError:
            pass

        # Concurrent producers must not lose each other's status.
        health_dir2 = Path(tmp) / "concurrent"
        health_dir2.mkdir()
        errors = []

        def producer(name):
            try:
                for _ in range(20):
                    health_mod.write_status_file(health_dir2, stack_id, name, ready=True, detail=f"{name}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=producer, args=(n,)) for n in health_mod.HEALTH_STATUSES]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"concurrent writes failed: {errors}"
        assert health_mod.all_ready(health_dir2) is True
        for name in health_mod.HEALTH_STATUSES:
            entry = json.loads((health_dir2 / f"{name}.json").read_text(encoding="utf-8"))
            assert entry["status"] == name and entry["ready"] is True and entry["stack_id"] == stack_id
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
