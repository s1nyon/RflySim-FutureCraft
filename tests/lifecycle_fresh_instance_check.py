#!/usr/bin/env python3
"""Fresh-instance plan contract: phase order, gates, no auto force-retry, verify-clean decision."""

from __future__ import annotations

import argparse
import importlib.util
import sys
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


class FakeReport:
    def __init__(self, owned_alive=0, owned_exited=0, stale=0, unknown=0, ports_unknown=0):
        self.owned_alive = owned_alive
        self.owned_exited = owned_exited
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
        "inspect",
        "graceful_stop",
        "verify_clean",
        "start_new",
        "health_gate",
        "readiness",
        "flight",
    ]

    plan = fresh.build_plan()
    assert plan["auto_force_retry"] is False, "fresh-instance must never auto force-retry"
    assert [p["name"] for p in plan["phases"]] == fresh.FRESH_INSTANCE_PHASES
    for phase in plan["phases"]:
        assert phase["gate"], f"phase {phase['name']} must define a gate"

    # verify-clean: clean only when nothing owned is alive and no unknown/stale
    clean = fresh.verify_clean_decision(FakeReport(owned_alive=0, owned_exited=1))
    assert clean[0] is True and clean[1] == []

    alive = fresh.verify_clean_decision(FakeReport(owned_alive=1))
    assert alive[0] is False and any("alive" in r for r in alive[1])

    unknown = fresh.verify_clean_decision(FakeReport(owned_exited=1, unknown=1))
    assert unknown[0] is False

    stale = fresh.verify_clean_decision(FakeReport(owned_exited=1, stale=1))
    assert stale[0] is False

    # can proceed to a new start only when the pre-stop inspect is not fail-closed
    assert fresh.can_proceed_to_start(FakeReport()) is True
    assert fresh.can_proceed_to_start(FakeReport(unknown=1)) is False
    assert fresh.can_proceed_to_start(FakeReport(stale=1)) is False
    assert fresh.can_proceed_to_start(FakeReport(ports_unknown=1)) is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
