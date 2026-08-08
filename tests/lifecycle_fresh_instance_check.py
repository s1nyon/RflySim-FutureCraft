#!/usr/bin/env python3
"""Fresh-instance plan: fixed phases, gates, no auto force-retry, orphan-aware clean decisions."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
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


class FakeReport:
    def __init__(self, owned_alive=0, owned_exited=0, orphans=0, stale=0, unknown=0, ports_unknown=0):
        self.owned_alive = owned_alive
        self.owned_exited = owned_exited
        self.orphans = orphans
        self.stale = stale
        self.unknown = unknown
        self.ports_unknown = ports_unknown

    @property
    def fail_closed(self):
        return self.stale > 0 or self.unknown > 0 or self.ports_unknown > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-module", required=True, type=Path)
    args = parser.parse_args()

    fresh = load_module("fresh_instance", args.fresh_module)
    assert fresh.FRESH_INSTANCE_PHASES == [
        "inspect", "graceful_stop", "verify_clean", "start_new", "health_gate", "readiness", "flight",
    ]

    plan = fresh.build_plan()
    assert plan["auto_force_retry"] is False
    assert [p["name"] for p in plan["phases"]] == fresh.FRESH_INSTANCE_PHASES
    assert all(p["gate"] for p in plan["phases"])

    # verify-clean: no owned alive, no orphans, no unknown/stale.
    assert fresh.verify_clean_decision(FakeReport(owned_exited=1)) == (True, [])
    assert fresh.verify_clean_decision(FakeReport(owned_alive=1))[0] is False
    assert fresh.verify_clean_decision(FakeReport(orphans=1))[0] is False, "orphans must fail clean verification"
    assert fresh.verify_clean_decision(FakeReport(stale=1))[0] is False
    assert fresh.verify_clean_decision(FakeReport(unknown=1))[0] is False

    # can_proceed_to_start: orphans also block starting a new stack.
    assert fresh.can_proceed_to_start(FakeReport()) is True
    assert fresh.can_proceed_to_start(FakeReport(unknown=1)) is False
    assert fresh.can_proceed_to_start(FakeReport(stale=1)) is False
    assert fresh.can_proceed_to_start(FakeReport(orphans=1)) is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
