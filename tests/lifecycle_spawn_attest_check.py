#!/usr/bin/env python3
"""spawn_attested ownership: marker-attested PX4 daemons, strict conditions, safe stop (Cases A-G)."""

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

    def replace(self, pid, proc):
        self._by_pid[int(pid)] = proc


class FakeAttestVerifier:
    """Returns True only for pids in `approved`."""

    def __init__(self, approved=()):
        self.approved = set(int(p) for p in approved)
        self.checks = []

    def verify(self, entry, proc) -> bool:
        self.checks.append(int(proc.pid))
        return int(proc.pid) in self.approved


class FakeStopBackend:
    def __init__(self, wsl_table=None, fail_signals=()):
        self.calls = []
        self.wsl_table = wsl_table
        self.fail_signals = set(fail_signals)

    def close_main_window(self, proc):
        self.calls.append(("close", int(proc.pid)))
        return True

    def stop(self, proc, signal):
        self.calls.append((signal, int(proc.pid)))
        if signal in self.fail_signals:
            return False
        if signal == "KILL":
            self.wsl_table.remove(int(proc.pid))
        return True

    def stop_group(self, pgid, signal):
        self.calls.append((signal, -int(pgid)))
        if signal in self.fail_signals:
            return False
        if signal == "KILL":
            for pid in [p for p, pr in self.wsl_table._by_pid.items() if pr.pgid == int(pgid)]:
                self.wsl_table.remove(pid)
        return True

    def alive_group(self, pgid):
        return any(p.pgid == int(pgid) for p in self.wsl_table.snapshot())

    def delete_task(self, identity):
        return True


def make_candidate(pid, index, stack_id, exe="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4",
                   start="2026-08-08T14:39:15Z", marker=True, pgid=None, sid=None):
    env = {}
    if marker:
        env["RFLY_STACK_ID"] = stack_id
        env["RFLY_SIM_INSTANCE_ID"] = stack_id
    cmdline = f"/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -i {index} -d /mnt/d/PX4PSP/Firmware/Tools/../build/px4_sitl_default/etc -s etc/init.d-posix/rcS"
    return {
        "pid": pid,
        "pgid": pgid or pid,
        "sid": sid or pid,
        "start_time_utc": start,
        "start_time_raw": "Sat Aug  8 14:39:15 2026",
        "exe": exe,
        "cwd": "/mnt/d/PX4PSP/Firmware/build/px4_sitl_default",
        "cmdline": cmdline,
        "environ": env,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attest-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--stop-module", required=True, type=Path)
    args = parser.parse_args()

    attest = load_module("spawn_attest", args.attest_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)
    ownership = load_module("stack_ownership", args.ownership_module)
    table_mod = load_module("process_table", args.process_table_module)
    stop = load_module("stack_stop", args.stop_module)

    STACK = "stack-20260808T150000Z-a1b2c3d4"
    PARENT_START = "2026-08-08T14:39:00Z"

    manifest = manifest_mod.new_manifest(
        stack_id=STACK,
        launcher={"kind": "batch", "identity": "test"},
    )
    parent_entry = ownership.register_process(
        manifest, side="wsl", pid=9000, pgid=9000, role="wsl:px4_build_session", name="bash",
        command_line="bash -lic sitl_multiple_run_rfly.sh", start_time_utc=PARENT_START,
        reason="created by stack SITL wrapper (wsl session registration at start)",
    )

    # Case A: old PX4 (no marker) + current PX4 (marker) -> current approved, old rejected.
    current = make_candidate(pid=7001, index=1, stack_id=STACK)
    old = make_candidate(pid=7000, index=1, stack_id=STACK, start="2026-08-08T10:00:00Z", marker=False)
    approved, rejected = attest.attest_candidates(
        manifest, [current, old], parent_entry=parent_entry, sim_instance_token=STACK
    )
    assert [c["pid"] for c in approved] == [7001], "current marked PX4 must be approved"
    assert [c["pid"] for c in rejected] == [7000], "old unmarked PX4 must be rejected"
    assert "marker" in rejected[0]["reasons"][0].lower()

    # Case B: marker belongs to another stack -> reject.
    wrong = make_candidate(pid=7002, index=1, stack_id="stack-OTHERSTACK")
    approved_b, rejected_b = attest.attest_candidates(
        manifest, [wrong], parent_entry=parent_entry, sim_instance_token=STACK
    )
    assert approved_b == [] and rejected_b[0]["pid"] == 7002

    # Case C: marker missing -> reject even though name/exe/cmdline all look like PX4.
    missing = make_candidate(pid=7003, index=1, stack_id=STACK, marker=False)
    approved_c, rejected_c = attest.attest_candidates(
        manifest, [missing], parent_entry=parent_entry, sim_instance_token=STACK
    )
    assert approved_c == [] and rejected_c[0]["pid"] == 7003
    assert any("marker" in r.lower() for r in rejected_c[0]["reasons"])

    # Case C2: start time before parent session -> reject.
    early = make_candidate(pid=7004, index=1, stack_id=STACK, start="2026-08-08T14:38:00Z")
    approved_d, _ = attest.attest_candidates(
        manifest, [early], parent_entry=parent_entry, sim_instance_token=STACK
    )
    assert approved_d == [], "candidate starting before the SITL session must be rejected"

    # Case E: two UAV instances distinguished by -i index -> uav1/uav2 roles, no cross-binding.
    uav1 = make_candidate(pid=7101, index=1, stack_id=STACK)
    uav2 = make_candidate(pid=7102, index=2, stack_id=STACK)
    approved_e, _ = attest.attest_candidates(
        manifest, [uav1, uav2], parent_entry=parent_entry, sim_instance_token=STACK
    )
    roles = {c["pid"]: attest.role_for_candidate(c) for c in approved_e}
    assert roles[7101] == "wsl:px4_uav1"
    assert roles[7102] == "wsl:px4_uav2"

    # Register the approved candidates and verify schema.
    for candidate in approved_e:
        entry = attest.register_attested(
            manifest, candidate, parent_entry=parent_entry, sim_instance_token=STACK
        )
        assert entry["ownership"]["granted"] == "spawn_attested"
        assert entry["ownership"]["ownership_parent_role"] == "wsl:px4_build_session"
        assert entry["ownership"]["stack_marker"]["value"] == STACK
        assert entry["ownership"]["ownership_evidence"]["px4_instance_index"] in (1, 2)
        assert entry["ownership"]["ownership_evidence"]["start_after_parent"] is True
        assert entry["ownership"]["ownership_evidence"]["exe_matches"] is True
        assert entry["ownership"]["ownership_evidence"]["marker_match"] is True
        assert entry["sid"] is not None
    manifest_mod.validate_manifest(manifest)

    # Case D: stale PID reuse -> stop refused for spawn_attested entry.
    manifest_d = manifest_mod.new_manifest(stack_id=STACK)
    ownership.register_process(
        manifest_d, side="wsl", pid=9000, pgid=9000, role="wsl:px4_build_session", name="bash",
        command_line="bash -lic sitl_multiple_run_rfly.sh", start_time_utc=PARENT_START, reason="t",
    )
    entry_d = attest.register_attested(
        manifest_d, make_candidate(pid=7201, index=1, stack_id=STACK),
        parent_entry=manifest_d["wsl_processes"][0], sim_instance_token=STACK,
    )
    reused = table_mod.ProcessInfo(
        pid=7201, name="px4", start_time_utc="2026-08-08T16:00:00Z",
        command_line=entry_d["command_line"], parent_pid=1, pgid=7201,
    )
    wsl_table = MutableTable([reused])
    backend_d = FakeStopBackend(wsl_table=wsl_table)
    verifier = FakeAttestVerifier(approved=())
    report = stop.execute_stop(
        manifest_d, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend_d, wsl_backend=backend_d,
        dry_run=False, reason="t", int_wait_s=0, term_wait_s=0,
        attest_verifier=verifier,
    )
    assert 7201 not in {pid for _, pid in backend_d.calls}, "stale spawn_attested pid must never be signalled"
    assert report.clean is False and report.refused

    # Case G: spawn_attested stop -> INT/TERM/KILL only on re-verified owned pids.
    manifest_g = manifest_mod.new_manifest(stack_id=STACK)
    ownership.register_process(
        manifest_g, side="wsl", pid=9000, pgid=9000, role="wsl:px4_build_session", name="bash",
        command_line="bash -lic sitl_multiple_run_rfly.sh", start_time_utc=PARENT_START, reason="t",
    )
    entry_g = attest.register_attested(
        manifest_g, make_candidate(pid=7301, index=1, stack_id=STACK),
        parent_entry=manifest_g["wsl_processes"][0], sim_instance_token=STACK,
    )
    proc_g = table_mod.ProcessInfo(
        pid=7301, name="px4", start_time_utc=entry_g["start_time_utc"],
        command_line=entry_g["command_line"], parent_pid=1, pgid=7301,
    )
    unowned = table_mod.ProcessInfo(
        pid=7400, name="px4", start_time_utc="2026-08-08T14:39:15Z",
        command_line=entry_g["command_line"], parent_pid=1, pgid=7301,
    )
    wsl_table = MutableTable([proc_g, unowned])
    backend = FakeStopBackend(wsl_table=wsl_table)
    verifier_g = FakeAttestVerifier(approved=(7301,))
    report_g = stop.execute_stop(
        manifest_g, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0, attest_verifier=verifier_g,
    )
    # Group kill must be refused because the PGID contains an unowned member (7400);
    # stop falls back to per-PID verified signals for 7301 only.
    group_targets = [pid for _, pid in backend.calls if pid < 0]
    assert group_targets == [], f"group kill must be refused with unowned member: {group_targets}"
    stopped = {pid for sig, pid in backend.calls if sig in ("INT", "TERM", "KILL")}
    assert 7301 in stopped, "owned spawn_attested px4 must be stopped per-PID"
    assert 7400 not in stopped, "unowned member must never be signalled"

    # Case G2: group kill allowed when every member is owned and verified.
    manifest_g2 = manifest_mod.new_manifest(stack_id=STACK)
    ownership.register_process(
        manifest_g2, side="wsl", pid=9000, pgid=9000, role="wsl:px4_build_session", name="bash",
        command_line="bash -lic sitl_multiple_run_rfly.sh", start_time_utc=PARENT_START, reason="t",
    )
    e1 = attest.register_attested(
        manifest_g2, make_candidate(pid=7501, index=1, stack_id=STACK),
        parent_entry=manifest_g2["wsl_processes"][0], sim_instance_token=STACK,
    )
    e2 = attest.register_attested(
        manifest_g2, make_candidate(pid=7502, index=2, stack_id=STACK),
        parent_entry=manifest_g2["wsl_processes"][0], sim_instance_token=STACK,
    )
    p1 = table_mod.ProcessInfo(pid=7501, name="px4", start_time_utc=e1["start_time_utc"],
                               command_line=e1["command_line"], parent_pid=1, pgid=7501)
    p2 = table_mod.ProcessInfo(pid=7502, name="px4", start_time_utc=e2["start_time_utc"],
                               command_line=e2["command_line"], parent_pid=1, pgid=7502)
    wsl_table = MutableTable([p1, p2])
    backend = FakeStopBackend(wsl_table=wsl_table)
    verifier_g2 = FakeAttestVerifier(approved=(7501, 7502))
    stop.execute_stop(
        manifest_g2, win_table=MutableTable([]), wsl_table=wsl_table,
        win_backend=backend, wsl_backend=backend, dry_run=False, reason="t",
        int_wait_s=0, term_wait_s=0, attest_verifier=verifier_g2,
    )
    group_targets_g2 = {pid for _, pid in backend.calls if pid < 0}
    assert group_targets_g2 == {-7501, -7502}, f"owned-only groups may be group-stopped: {group_targets_g2}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
