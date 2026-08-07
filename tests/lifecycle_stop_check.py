#!/usr/bin/env python3
"""Graceful stop contract: DryRun no-op, owned-only, PID-reuse protection, verified force, reason record."""

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


class MutableTable:
    """Fake process table whose snapshot reflects removals."""

    def __init__(self, processes):
        self._by_pid = {int(p.pid): p for p in processes}

    def snapshot(self):
        return list(self._by_pid.values())

    def remove(self, pid):
        self._by_pid.pop(int(pid), None)

    def replace(self, pid, proc):
        self._by_pid[int(pid)] = proc


class FakeStopBackend:
    def __init__(self, win_table=None, wsl_table=None):
        self.calls = []
        self.win_table = win_table
        self.wsl_table = wsl_table
        self.deleted_tasks = []

    def close_main_window(self, proc):
        self.calls.append(("close", int(proc.pid)))
        return True

    def stop(self, proc, signal):
        self.calls.append((signal, int(proc.pid)))
        if signal == "KILL":
            table = self.win_table if int(proc.pid) in {p.pid for p in self.win_table.snapshot()} else self.wsl_table
            table.remove(int(proc.pid))
        return True

    def delete_task(self, identity):
        self.deleted_tasks.append(identity)
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    args = parser.parse_args()

    stop = load_module("stack_stop", args.stop_module)
    table_mod = load_module("process_table", args.process_table_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)
    ownership = load_module("stack_ownership", args.ownership_module)

    def make_proc(pid, name, start, cmd, parent=1):
        return table_mod.ProcessInfo(
            pid=pid, name=name, start_time_utc=start, command_line=cmd, parent_pid=parent
        )

    start = "2026-08-08T12:00:00Z"
    proc_a = make_proc(1, "RflySim3D", start, '"D:\\p\\RflySim3D.exe"')
    proc_b = make_proc(2, "CopterSim", start, '"D:\\p\\CopterSim.exe"')
    proc_c = make_proc(3, "QGroundControl", start, '"D:\\p\\QGroundControl.exe"')  # unowned

    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        launcher={
            "kind": "scheduled_task",
            "identity": "\\FutureAircraftSim_LiveStack_stack-20260808T120000Z-a1b2c3d4",
        },
    )
    manifest["windows_processes"] = [
        {
            "pid": 1, "name": "RflySim3D", "start_time_utc": start,
            "command_line": '"D:\\p\\RflySim3D.exe"', "role": "gui:RflySim3D",
        },
        {
            "pid": 2, "name": "CopterSim", "start_time_utc": start,
            "command_line": '"D:\\p\\CopterSim.exe"', "role": "gui:CopterSim",
        },
    ]

    # 1. DryRun: zero side effects, but full plan produced
    win_table = MutableTable([proc_a, proc_b, proc_c])
    backend = FakeStopBackend(win_table=win_table)
    report = stop.execute_stop(
        manifest, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=True, reason="test",
        int_wait_s=0, term_wait_s=0,
    )
    assert report.dry_run is True
    assert backend.calls == [], "DryRun must not touch processes"
    assert backend.deleted_tasks == []
    assert {a.pid for a in report.actions} == {1, 2}
    assert report.refused == []

    # 2. Owned A/B stopped; unowned C stays alive
    win_table = MutableTable([proc_a, proc_b, proc_c])
    backend = FakeStopBackend(win_table=win_table)
    report = stop.execute_stop(
        manifest, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="test",
        int_wait_s=0, term_wait_s=0,
    )
    stopped = {pid for _, pid in backend.calls}
    assert {1, 2} <= stopped, f"A/B must be stopped: {stopped}"
    assert 3 not in stopped, "unowned C must stay alive"
    assert 1 not in {p.pid for p in win_table.snapshot()}
    assert 2 not in {p.pid for p in win_table.snapshot()}
    assert 3 in {p.pid for p in win_table.snapshot()}, "unowned C must survive"
    assert report.clean is True
    assert manifest["stop"]["last_stop_reason"] == "test"
    assert manifest["stop"]["clean"] is True

    # 3. PID reuse protection: same PID, different start time -> refused, never touched
    reused = make_proc(1, "RflySim3D", "2026-08-08T14:00:00Z", '"D:\\p\\RflySim3D.exe"')
    win_table = MutableTable([reused])
    backend = FakeStopBackend(win_table=win_table)
    report = stop.execute_stop(
        manifest, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="test",
        int_wait_s=0, term_wait_s=0,
    )
    assert 1 not in {pid for _, pid in backend.calls}
    assert any("reuse" in str(r) or "verification" in str(r).lower() for r in report.refused)
    assert report.clean is False

    # 4. Force only after re-verification: TERM survives, KILL issued with reason recorded
    win_table = MutableTable([proc_a])
    backend = FakeStopBackend(win_table=win_table)
    report = stop.execute_stop(
        manifest, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="test",
        int_wait_s=0, term_wait_s=0,
    )
    assert ("KILL", 1) in backend.calls, "force must be used only after verification"
    assert manifest["stop"]["force_reasons"], "force reason must be recorded"

    # 5. Force refused when PID is reused after TERM (verification fails at KILL phase)
    class SwapBackend(FakeStopBackend):
        def stop(self, proc, signal):
            self.calls.append((signal, int(proc.pid)))
            if signal == "TERM":
                self.win_table.replace(proc.pid, reused)
            if signal == "KILL":
                self.win_table.remove(proc.pid)
            return True

    win_table = MutableTable([proc_a])
    backend = SwapBackend(win_table=win_table)
    report = stop.execute_stop(
        manifest, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="test",
        int_wait_s=0, term_wait_s=0,
    )
    assert ("KILL", 1) not in backend.calls, "KILL must be refused after PID reuse"
    assert report.clean is False

    # 6. Scheduled-task identity: stop deletes only the manifest-recorded task
    win_table = MutableTable([])
    backend = FakeStopBackend(win_table=win_table)
    stop.execute_stop(
        manifest, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="test",
        int_wait_s=0, term_wait_s=0,
    )
    assert backend.deleted_tasks == [manifest["launcher"]["identity"]]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
