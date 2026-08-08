#!/usr/bin/env python3
"""Graceful stop hardening: PGID targeting, final-verification clean, rich DryRun, orphan/signal-failure handling."""

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


class MutableTable:
    def __init__(self, processes):
        self._by_pid = {int(p.pid): p for p in processes}

    def snapshot(self):
        return list(self._by_pid.values())

    def remove(self, pid):
        self._by_pid.pop(int(pid), None)

    def remove_group(self, pgid):
        for pid in [p for p, proc in self._by_pid.items() if proc.pgid == int(pgid)]:
            self._by_pid.pop(pid, None)

    def replace(self, pid, proc):
        self._by_pid[int(pid)] = proc


class FakeStopBackend:
    """Records calls; KILL removes the pid/group from the matching table."""

    def __init__(self, win_table=None, wsl_table=None, fail_signals=(), fail_groups=()):
        self.calls = []
        self.win_table = win_table
        self.wsl_table = wsl_table
        self.fail_signals = set(fail_signals)
        self.fail_groups = set(fail_groups)
        self.deleted_tasks = []

    def close_main_window(self, proc):
        self.calls.append(("close", int(proc.pid)))
        return True

    def stop(self, proc, signal):
        self.calls.append((signal, int(proc.pid)))
        if signal in self.fail_signals:
            return False
        if signal == "KILL":
            table = self.win_table if int(proc.pid) in {p.pid for p in self.win_table.snapshot()} else self.wsl_table
            table.remove(int(proc.pid))
        return True

    def stop_group(self, pgid, signal):
        self.calls.append((signal, -int(pgid)))
        if signal in self.fail_signals or int(pgid) in self.fail_groups:
            return False
        if signal == "KILL":
            self.wsl_table.remove_group(int(pgid))
        return True

    def alive_group(self, pgid):
        return any(p.pgid == int(pgid) for p in self.wsl_table.snapshot())

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

    def make_proc(pid, name, start, cmd, parent=1, pgid=None):
        return table_mod.ProcessInfo(pid=pid, name=name, start_time_utc=start, command_line=cmd,
                                     parent_pid=parent, pgid=pgid)

    start = "2026-08-08T12:00:00Z"

    # 1. DryRun: zero side effects, rich action info (pid/pgid/start/fingerprint/ownership reason/signal).
    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        launcher={"kind": "scheduled_task", "identity": "\\FutureAircraftSim_LiveStack_xyz"},
    )
    ownership.register_process(
        manifest, side="windows", pid=1, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\p\\RflySim3D.exe"', start_time_utc=start,
        reason="launcher captured PID via Start-Process -PassThru",
    )
    ownership.register_process(
        manifest, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        command_line="/opt/ros/noetic/bin/roscore", start_time_utc=start,
        reason="created by stage2_two_mavros.sh (setsid)",
    )
    proc_a = make_proc(1, "RflySim3D", start, '"D:\\p\\RflySim3D.exe"', pgid=None)
    proc_roc = make_proc(500, "roscore", start, "/opt/ros/noetic/bin/roscore", pgid=500)
    win_table = MutableTable([proc_a])
    wsl_table = MutableTable([proc_roc])
    backend = FakeStopBackend(win_table=win_table, wsl_table=wsl_table)
    report = stop.execute_stop(
        manifest, win_table=win_table, wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=True, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert report.dry_run is True and backend.calls == []
    assert backend.deleted_tasks == []
    actions = {a.pid: a for a in report.actions}
    assert 1 in actions and 500 in actions
    for a in report.actions:
        assert a.signal in ("close", "INT", "TERM", "KILL")
        assert a.start_time and a.fingerprint and a.ownership_reason, "DryRun must expose identity fields"
    wsl_actions = [a for a in report.actions if a.side == "wsl"]
    assert all(a.target == "pgid" and a.pgid == 500 for a in wsl_actions), "WSL stop must target PGID"

    # 2. owned A/B stopped, unowned C (same GUI family) stays alive.
    manifest2 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest2, side="windows", pid=1, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\p\\RflySim3D.exe"', start_time_utc=start, reason="t",
    )
    ownership.register_process(
        manifest2, side="windows", pid=2, role="gui:CopterSim", name="CopterSim",
        command_line='"D:\\p\\CopterSim.exe"', start_time_utc=start, reason="t",
    )
    proc_b = make_proc(2, "CopterSim", start, '"D:\\p\\CopterSim.exe"')
    proc_c = make_proc(3, "RflySim3D", start, '"D:\\p\\RflySim3D.exe"')  # same name as A, NOT registered
    win_table = MutableTable([proc_a, proc_b, proc_c])
    backend = FakeStopBackend(win_table=win_table, wsl_table=MutableTable([]))
    report = stop.execute_stop(
        manifest2, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    stopped = {pid for _, pid in backend.calls}
    assert {1, 2} <= stopped and 3 not in stopped
    assert 3 in {p.pid for p in win_table.snapshot()}, "unowned same-name process must survive"
    assert report.clean is True

    # 3. Two same-name processes: only the registered one is stopped.
    manifest3 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest3, side="windows", pid=1, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\p\\RflySim3D.exe"', start_time_utc=start, reason="t",
    )
    other_same_name = make_proc(99, "RflySim3D", start, '"D:\\p\\RflySim3D.exe"')
    win_table = MutableTable([proc_a, other_same_name])
    backend = FakeStopBackend(win_table=win_table, wsl_table=MutableTable([]))
    stop.execute_stop(
        manifest3, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert 99 not in {pid for _, pid in backend.calls}
    assert 99 in {p.pid for p in win_table.snapshot()}

    # 4. Old roscore + new roscore: new stack must not claim/stop the old one.
    manifest4 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest4, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        command_line="/opt/ros/noetic/bin/roscore", start_time_utc=start, reason="created by current stack",
    )
    old_roscore = make_proc(600, "roscore", "2026-08-08T10:00:00Z", "/opt/ros/noetic/bin/roscore", pgid=600)
    new_roscore = make_proc(500, "roscore", start, "/opt/ros/noetic/bin/roscore", pgid=500)
    wsl_table = MutableTable([new_roscore, old_roscore])
    backend = FakeStopBackend(win_table=MutableTable([]), wsl_table=wsl_table)
    stop.execute_stop(
        manifest4, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert 600 not in {pid for _, pid in backend.calls}, "old roscore must not be touched"
    assert 600 in {p.pid for p in wsl_table.snapshot()}

    # 5. PGID isolation: signals go to the owned group only.
    manifest5 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest5, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        command_line="/opt/ros/noetic/bin/roscore", start_time_utc=start, reason="t",
    )
    other_group = make_proc(700, "roscore", start, "/opt/ros/noetic/bin/roscore", pgid=700)
    wsl_table = MutableTable([new_roscore, other_group])
    backend = FakeStopBackend(win_table=MutableTable([]), wsl_table=wsl_table)
    stop.execute_stop(
        manifest5, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    group_targets = [pid for _, pid in backend.calls if pid < 0]
    assert group_targets and all(pid == -500 for pid in group_targets), f"only owned PGID may be targeted: {group_targets}"
    assert 700 in {p.pid for p in wsl_table.snapshot()}

    # 6. Parent exited, orphan remains in registered PGID -> still stopped via PGID.
    manifest6 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest6, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        command_line="/opt/ros/noetic/bin/roscore", start_time_utc=start, reason="t",
    )
    orphan_child = make_proc(777, "roscore", start, "/opt/ros/noetic/bin/roscore", pgid=500)
    wsl_table = MutableTable([orphan_child])  # leader 500 exited
    backend = FakeStopBackend(win_table=MutableTable([]), wsl_table=wsl_table)
    report = stop.execute_stop(
        manifest6, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert -500 in {pid for _, pid in backend.calls}
    assert report.clean is True, "orphan group stopped via PGID must be clean"

    # 7. Signal failure -> clean=false with failure reasons recorded.
    manifest7 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest7, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        command_line="/opt/ros/noetic/bin/roscore", start_time_utc=start, reason="t",
    )
    wsl_table = MutableTable([new_roscore])
    backend = FakeStopBackend(win_table=MutableTable([]), wsl_table=wsl_table,
                              fail_signals={"KILL"}, fail_groups={500})
    report = stop.execute_stop(
        manifest7, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert report.clean is False
    assert manifest7["stop"]["clean"] is False
    assert manifest7["stop"]["failure_reasons"], "failure reasons must be recorded"

    # 8. Stale PID reuse: identity mismatch -> refused, never touched, clean=false.
    manifest8 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest8, side="windows", pid=1, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\p\\RflySim3D.exe"', start_time_utc=start, reason="t",
    )
    reused = make_proc(1, "RflySim3D", "2026-08-08T14:00:00Z", '"D:\\p\\RflySim3D.exe"')
    win_table = MutableTable([reused])
    backend = FakeStopBackend(win_table=win_table, wsl_table=MutableTable([]))
    report = stop.execute_stop(
        manifest8, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert 1 not in {pid for _, pid in backend.calls}
    assert report.clean is False and report.refused

    # 9. Force only after re-verification; force reason recorded.
    manifest9 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest9, side="windows", pid=1, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\p\\RflySim3D.exe"', start_time_utc=start, reason="t",
    )
    win_table = MutableTable([proc_a])
    backend = FakeStopBackend(win_table=win_table, wsl_table=MutableTable([]))
    report = stop.execute_stop(
        manifest9, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert ("KILL", 1) in backend.calls
    assert manifest9["stop"]["force_reasons"]

    # 10. clean must come from final verification: backend keeps process alive -> clean=false.
    manifest10 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest10, side="windows", pid=1, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\p\\RflySim3D.exe"', start_time_utc=start, reason="t",
    )

    class ZombieBackend(FakeStopBackend):
        def stop(self, proc, signal):
            self.calls.append((signal, int(proc.pid)))
            return True  # never removes: process survives every signal

    win_table = MutableTable([proc_a])
    backend = ZombieBackend(win_table=win_table, wsl_table=MutableTable([]))
    report = stop.execute_stop(
        manifest10, win_table=win_table, wsl_table=MutableTable([]),
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0,
    )
    assert report.clean is False, "clean must be false when owned process still alive after stop"
    assert 1 in {p.pid for p in win_table.snapshot()}
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
