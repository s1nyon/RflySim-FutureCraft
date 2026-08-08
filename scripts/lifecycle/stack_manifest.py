"""Stack manifest: stack_id, schema, fingerprints, and PID-reuse-safe process matching."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 2
MATCH_TOLERANCE_SEC = 2.0

REQUIRED_TOP_LEVEL = {
    "schema_version",
    "stack_id",
    "git_commit",
    "start_time_utc",
    "launcher",
    "ros_master",
    "simulation_instance_id",
    "windows_processes",
    "wsl_processes",
    "required_ports",
    "health",
    "stop",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_stack_id(now_utc: Optional[datetime] = None, entropy: Optional[str] = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    ent = entropy or secrets.token_hex(4)
    return f"stack-{now.strftime('%Y%m%dT%H%M%SZ')}-{ent}"


def manifest_dir(project_root: Path, stack_id: str) -> Path:
    return Path(project_root) / "logs" / "live_stack" / stack_id


def manifest_path(project_root: Path, stack_id: str) -> Path:
    return manifest_dir(project_root, stack_id) / "stack_manifest.json"


def new_manifest(
    stack_id: str,
    git_commit: Optional[str] = None,
    launcher: Optional[dict] = None,
    ros_master: Optional[dict] = None,
    start_time_utc: Optional[str] = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "stack_id": stack_id,
        "git_commit": git_commit,
        "start_time_utc": start_time_utc or utc_now_iso(),
        "launcher": launcher or {"kind": "unknown", "identity": None},
        "ros_master": ros_master
        or {"uri": "http://127.0.0.1:11311", "host": "127.0.0.1", "port": 11311},
        "simulation_instance_id": None,
        "windows_processes": [],
        "wsl_processes": [],
        "required_ports": [
            {"port": 14600, "protocol": "udp", "owner": "uav1-mavros"},
            {"port": 14601, "protocol": "udp", "owner": "uav1-mavros"},
            {"port": 14610, "protocol": "udp", "owner": "uav2-mavros"},
            {"port": 14611, "protocol": "udp", "owner": "uav2-mavros"},
            {"port": 11311, "protocol": "tcp", "owner": "ros_master"},
        ],
        "health": {
            "schema_version": 1,
            "stack_id": stack_id,
            "checked_at_utc": None,
            "all_ready": False,
            "statuses": {},
        },
        "stop": {"last_stop_reason": None, "last_stop_utc": None, "clean": None},
    }


def validate_manifest(manifest: dict) -> None:
    missing = REQUIRED_TOP_LEVEL - set(manifest)
    if missing:
        raise ValueError(f"manifest missing required fields: {sorted(missing)}")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {manifest['schema_version']}")
    if not re.fullmatch(r"stack-\d{8}T\d{6}Z-[0-9a-f]{8}", str(manifest["stack_id"])):
        raise ValueError(f"malformed stack_id: {manifest['stack_id']}")
    if not isinstance(manifest["windows_processes"], list):
        raise ValueError("windows_processes must be a list")
    if not isinstance(manifest["wsl_processes"], list):
        raise ValueError("wsl_processes must be a list")
    for entry in list(manifest["windows_processes"]) + list(manifest["wsl_processes"]):
        for field in ("pid", "name", "start_time_utc", "command_line", "role"):
            if field not in entry:
                raise ValueError(f"process entry missing '{field}': {entry}")
        ownership = entry.get("ownership")
        if not isinstance(ownership, dict):
            raise ValueError(f"process entry without ownership grant: pid={entry.get('pid')}")
        grant = ownership.get("granted")
        if grant == "at_creation":
            if not ownership.get("reason") or not ownership.get("granted_at_utc"):
                raise ValueError(
                    f"at_creation grant must include reason and granted_at_utc: pid={entry.get('pid')}"
                )
        elif grant == "spawn_attested":
            required = ("reason", "granted_at_utc", "ownership_parent_role", "stack_marker", "ownership_evidence")
            missing = [field for field in required if not ownership.get(field)]
            if missing:
                raise ValueError(
                    f"spawn_attested grant missing {missing} for pid={entry.get('pid')}"
                )
        else:
            raise ValueError(f"unknown ownership grant '{grant}' for pid={entry.get('pid')}")


def normalize_command_line(command_line: str) -> str:
    return " ".join(str(command_line or "").lower().split())


def command_line_fingerprint(command_line: str) -> str:
    return hashlib.sha256(normalize_command_line(command_line).encode("utf-8")).hexdigest()[:16]


def parse_utc(value: Any) -> Optional[datetime]:
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def entry_matches_process(
    entry: dict, proc: Any, tolerance_s: float = MATCH_TOLERANCE_SEC
) -> bool:
    """PID + start-time + command-line verification (PID-reuse safe)."""
    if int(entry["pid"]) != int(getattr(proc, "pid")):
        return False

    entry_raw = entry.get("start_time_raw")
    proc_raw = getattr(proc, "start_time_raw", None)
    if entry_raw is not None and proc_raw is not None:
        # Both sides carry a raw start-time token (same format family): compare
        # it exactly. If only ONE side has raw (e.g. spawn_attested manifest
        # entries carry only start_time_utc while the WSL process table always
        # carries lstart raw), fall back to UTC comparison - otherwise every
        # spawn_attested entry would fail identity verification in live WSL.
        if str(entry_raw).strip() != str(proc_raw).strip():
            return False
    else:
        entry_time = parse_utc(entry["start_time_utc"])
        proc_time = parse_utc(getattr(proc, "start_time_utc"))
        if entry_time is None or proc_time is None:
            return False
        if abs((entry_time - proc_time).total_seconds()) > tolerance_s:
            return False

    return normalize_command_line(entry["command_line"]) == normalize_command_line(
        getattr(proc, "command_line", "")
    )


def save_manifest(manifest: dict, path: Path) -> None:
    validate_manifest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    import os

    os.replace(tmp_path, path)


def load_manifest(path: Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def _cli_main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project-root", required=True, type=Path)
    init.add_argument("--stack-id", required=True)
    init.add_argument("--git-commit", default=None)
    init.add_argument("--launcher-kind", default="scheduled_task")
    init.add_argument("--launcher-identity", default=None)
    args = parser.parse_args()

    if args.cmd == "init":
        manifest = new_manifest(
            args.stack_id,
            git_commit=args.git_commit,
            launcher={"kind": args.launcher_kind, "identity": args.launcher_identity},
        )
        path = manifest_path(args.project_root, args.stack_id)
        save_manifest(manifest, path)
        print(f"[OK] manifest: {path}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli_main())
