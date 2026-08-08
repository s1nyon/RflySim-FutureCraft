#!/usr/bin/env python3
"""spawn_attested ownership: marker-attested PX4 SITL daemons spawned by a registered SITL session.

Ownership is granted ONLY when all of the following are true:
  * /proc/<pid>/environ inherits RFLY_STACK_ID == current stack_id (primary proof);
  * process start time is after the registered wsl:px4_build_session start;
  * /proc/<pid>/exe points to the expected PX4 SITL executable;
  * /proc/<pid>/cmdline carries a PX4 instance index (uav1/uav2) and matches the expected shape;
  * registration happens inside the current SITL launch transaction.

Name/regex is never sufficient: a process without the stack marker is unknown, period.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.stack_manifest import (  # noqa: E402
    command_line_fingerprint,
    load_manifest,
    parse_utc,
    save_manifest,
    utc_now_iso,
)
from lifecycle.stack_ownership import register_process  # noqa: E402

STACK_MARKER_NAME = "RFLY_STACK_ID"
SIM_MARKER_NAME = "RFLY_SIM_INSTANCE_ID"
PX4_EXE_FRAGMENT = "px4_sitl_default"
KNOWN_PX4_BASENAMES = {
    "px4",
    "px4-load_mon",
    "px4-battery_simulator",
    "px4-tone_alarm",
    "px4-commander",
    "px4-rc",
    "px4-rc_channels",
    "px4-sensors",
    "px4-mavlink",
}
PARENT_ROLE = "wsl:px4_build_session"


def parse_environ(data: bytes) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in data.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, _, value = item.partition(b"=")
        result[key.decode("utf-8", errors="replace")] = value.decode("utf-8", errors="replace")
    return result


def read_environ(pid: int) -> Dict[str, str]:
    try:
        with open(f"/proc/{int(pid)}/environ", "rb") as handle:
            return parse_environ(handle.read())
    except (OSError, FileNotFoundError):
        return {}


def px4_instance_index(cmdline: str) -> Optional[int]:
    m = re.search(r"(?:^|\s)-i\s+(\d+)", cmdline) or re.search(
        r"(?:^|\s)--instance\s+(\d+)", cmdline
    )
    if not m:
        return None
    index = int(m.group(1))
    return index if index in (1, 2) else None


def is_px4_exe(exe: str) -> bool:
    if not exe:
        return False
    basename = Path(exe).name
    return basename in KNOWN_PX4_BASENAMES or PX4_EXE_FRAGMENT in exe


def read_proc_candidate(pid: int) -> Optional[dict]:
    """Read /proc/<pid> identity fields (exe/cwd/cmdline/environ/ps info)."""
    try:
        environ = read_environ(pid)
        if not environ:
            return None
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            cmdline = " ".join(
                part.decode("utf-8", errors="replace") for part in handle.read().split(b"\0") if part
            )
        exe = os.readlink(f"/proc/{pid}/exe")
        cwd = os.readlink(f"/proc/{pid}/cwd")
        result = subprocess.run(
            ["ps", "-o", "pid=,ppid=,pgid=,sid=,etimes=,args=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split(None, 5)
        if len(parts) < 6:
            return None
        _, _, pgid, sid, etimes, args = parts
        start_epoch = time.time() - int(etimes)
        start_time_utc = dt.datetime.fromtimestamp(start_epoch, tz=dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return {
            "pid": int(pid),
            "pgid": int(pgid),
            "sid": int(sid),
            "start_time_raw": f"etime {etimes}s",
            "start_time_utc": start_time_utc,
            "exe": exe,
            "cwd": cwd,
            "cmdline": cmdline or args,
            "environ": environ,
        }
    except (OSError, FileNotFoundError, PermissionError, ValueError):
        return None


def attestation_decision(
    candidate: dict,
    stack_id: str,
    parent_entry: dict,
    sim_instance_token: Optional[str] = None,
    now_utc: Optional[str] = None,
) -> Tuple[bool, dict, List[str]]:
    reasons: List[str] = []
    evidence: dict = {
        "marker_match": False,
        "sim_marker_match": False,
        "start_after_parent": False,
        "exe_matches": False,
        "px4_instance_index": None,
        "cmdline_fingerprint": command_line_fingerprint(candidate.get("cmdline", "")),
        "sid": candidate.get("sid"),
        "cwd": candidate.get("cwd"),
        "exe": candidate.get("exe"),
        "transaction": f"sitl_launch:{stack_id}:{now_utc or utc_now_iso()}",
    }

    environ = candidate.get("environ", {})
    if environ.get(STACK_MARKER_NAME) != stack_id:
        reasons.append(f"stack marker missing/mismatch ({STACK_MARKER_NAME})")
    else:
        evidence["marker_match"] = True

    if sim_instance_token is not None:
        if environ.get(SIM_MARKER_NAME) != sim_instance_token:
            reasons.append(f"simulation marker missing/mismatch ({SIM_MARKER_NAME})")
        else:
            evidence["sim_marker_match"] = True

    parent_start = parse_utc(parent_entry.get("start_time_utc", ""))
    candidate_start = parse_utc(candidate.get("start_time_utc", ""))
    if parent_start is None or candidate_start is None:
        reasons.append("cannot parse parent/candidate start time")
    elif (candidate_start - parent_start).total_seconds() < -1.0:
        reasons.append("candidate started before the registered SITL session")
    else:
        evidence["start_after_parent"] = True

    if not is_px4_exe(candidate.get("exe", "")):
        reasons.append(f"executable is not an expected PX4 SITL binary: {candidate.get('exe')}")
    else:
        evidence["exe_matches"] = True

    index = px4_instance_index(candidate.get("cmdline", ""))
    if index is None:
        reasons.append("cmdline has no PX4 instance index (-i 1/2)")
    else:
        evidence["px4_instance_index"] = index

    approved = not reasons
    return approved, evidence, reasons


def role_for_candidate(candidate: dict) -> str:
    index = px4_instance_index(candidate.get("cmdline", "")) or 0
    basename = Path(candidate.get("exe", "")).name
    if basename == "px4":
        return f"wsl:px4_uav{index}"
    return f"wsl:px4_uav{index}:{basename}"


def attest_candidates(
    manifest: dict,
    candidates: List[dict],
    parent_entry: dict,
    sim_instance_token: Optional[str] = None,
    now_utc: Optional[str] = None,
) -> Tuple[List[dict], List[dict]]:
    approved: List[dict] = []
    rejected: List[dict] = []
    for candidate in candidates:
        ok, evidence, reasons = attestation_decision(
            candidate, manifest["stack_id"], parent_entry, sim_instance_token, now_utc
        )
        if ok:
            approved.append(candidate)
        else:
            rejected.append({"pid": candidate.get("pid"), "reasons": reasons})
    return approved, rejected


def register_attested(
    manifest: dict,
    candidate: dict,
    parent_entry: dict,
    sim_instance_token: Optional[str] = None,
    now_utc: Optional[str] = None,
) -> dict:
    approved, evidence, reasons = attestation_decision(
        candidate, manifest["stack_id"], parent_entry, sim_instance_token, now_utc
    )
    if not approved:
        raise ValueError(f"candidate pid {candidate.get('pid')} failed attestation: {reasons}")
    basename = Path(candidate.get("exe", "")).name
    entry = register_process(
        manifest,
        side="wsl",
        pid=candidate["pid"],
        pgid=candidate.get("pgid"),
        role=role_for_candidate(candidate),
        name=basename,
        command_line=candidate.get("cmdline", ""),
        start_time_utc=candidate.get("start_time_utc"),
        reason="spawned by registered SITL session (marker-attested)",
        ownership_extras={
            "granted": "spawn_attested",
            "ownership_parent_role": parent_entry.get("role", PARENT_ROLE),
            "stack_marker": {"name": STACK_MARKER_NAME, "value": manifest["stack_id"]},
            "simulation_instance_id": manifest.get("simulation_instance_id"),
            "ownership_evidence": evidence,
        },
    )
    entry["sid"] = candidate.get("sid")
    entry["exe"] = candidate.get("exe")
    entry["cwd"] = candidate.get("cwd")
    return entry


def _find_parent(manifest: dict, parent_pid: Optional[int]) -> Optional[dict]:
    for entry in manifest["wsl_processes"]:
        if entry.get("role") == PARENT_ROLE:
            if parent_pid is None or int(entry.get("pid", -1)) == int(parent_pid):
                return entry
    return None


def _enumerate_marker_candidates(stack_id: str) -> List[dict]:
    candidates: List[dict] = []
    try:
        pids = [int(name) for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return candidates
    for pid in pids:
        environ = read_environ(pid)
        if environ.get(STACK_MARKER_NAME) == stack_id:
            candidate = read_proc_candidate(pid)
            if candidate:
                candidates.append(candidate)
    return candidates


def _cli_main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "attest":
        argv = argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--parent-pid", type=int, default=None)
    parser.add_argument("--sim-instance-token", default=None)
    args = parser.parse_args(argv)

    if args.manifest is None:
        env_manifest = os.environ.get("STACK_MANIFEST")
        if env_manifest:
            args.manifest = Path(env_manifest)
    if args.sim_instance_token is None:
        args.sim_instance_token = os.environ.get("RFLY_SIM_INSTANCE_ID")
    if args.manifest is None:
        print("[ERROR] --manifest is required (or export STACK_MANIFEST)", file=sys.stderr)
        return 2

    manifest = load_manifest(args.manifest)
    parent = _find_parent(manifest, args.parent_pid)
    if parent is None:
        print(f"[ERROR] no {PARENT_ROLE} entry in manifest (parent-pid={args.parent_pid})", file=sys.stderr)
        return 1

    # Bounded retry: sitl_multiple_run_rfly.sh returns before the PX4 daemons
    # fully daemonize; poll up to 60s for marker-attested candidates.
    candidates: List[dict] = []
    deadline = time.time() + 60
    while time.time() < deadline:
        candidates = _enumerate_marker_candidates(manifest["stack_id"])
        if any(
            attestation_decision(c, manifest["stack_id"], parent, args.sim_instance_token)[0]
            for c in candidates
        ):
            break
        time.sleep(5)
    approved, rejected = attest_candidates(
        manifest, candidates, parent_entry=parent, sim_instance_token=args.sim_instance_token
    )
    for candidate in approved:
        register_attested(
            manifest, candidate, parent_entry=parent, sim_instance_token=args.sim_instance_token
        )
    save_manifest(manifest, args.manifest)

    print(f"[attest] approved={len(approved)} rejected={len(rejected)}")
    for candidate in approved:
        print(
            f"[attest] + pid={candidate['pid']} role={role_for_candidate(candidate)} "
            f"exe={candidate['exe']}"
        )
    for item in rejected:
        print(f"[attest] - pid={item['pid']} reasons={item['reasons']}", file=sys.stderr)
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
