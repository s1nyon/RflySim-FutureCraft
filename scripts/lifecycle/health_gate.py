"""Health gate v2: one file per status, atomic writes, aggregation with fail-closed semantics."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .stack_manifest import utc_now_iso

HEALTH_STATUSES = [
    "GUI_READY",
    "ROSCORE_READY",
    "MAVROS_UAV1_CONNECTED",
    "MAVROS_UAV2_CONNECTED",
    "COURSE_READY",
]


def status_file(health_dir: Path, name: str) -> Path:
    if name not in HEALTH_STATUSES:
        raise ValueError(f"unknown health status: {name}")
    return Path(health_dir) / f"{name}.json"


def write_status_file(health_dir: Path, stack_id: str, name: str, ready: bool, detail: str = "") -> None:
    """Write ONLY the named status file, atomically. Producers never touch other statuses."""
    if name not in HEALTH_STATUSES:
        raise ValueError(f"unknown health status: {name}")
    path = status_file(health_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "stack_id": stack_id,
        "status": name,
        "ready": bool(ready),
        "detail": str(detail),
        "written_at_utc": utc_now_iso(),
    }
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def read_status_files(health_dir: Path) -> dict:
    """Aggregate all status files. Missing files stay absent (fail closed)."""
    result: dict = {}
    for name in HEALTH_STATUSES:
        path = status_file(health_dir, name)
        if not path.exists():
            continue
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry.get("status") != name:
                raise ValueError(f"status file {name}.json declares {entry.get('status')}")
            result[name] = entry
        except (ValueError, json.JSONDecodeError):
            result[name] = {"ready": False, "detail": f"invalid status file: {name}.json"}
    return result


def status_ready(health_dir: Path, name: str) -> bool:
    return bool(read_status_files(health_dir).get(name, {}).get("ready"))


def all_ready(health_dir: Path) -> bool:
    statuses = read_status_files(health_dir)
    if set(statuses) != set(HEALTH_STATUSES):
        return False
    return all(entry.get("ready") for entry in statuses.values())


def health_summary(health_dir: Path) -> str:
    statuses = read_status_files(health_dir)
    parts = []
    for name in HEALTH_STATUSES:
        entry = statuses.get(name)
        parts.append(f"{name}={'READY' if entry and entry.get('ready') else 'NOT_READY'}")
    return " ".join(parts)


def status_detail(health_dir: Path, name: str) -> Optional[str]:
    entry = read_status_files(health_dir).get(name)
    return entry.get("detail") if entry else None
