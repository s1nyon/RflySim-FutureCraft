"""Health gate: fixed status enum, all-ready decision, fail-closed JSON contract."""

from __future__ import annotations

import json
from pathlib import Path

from .stack_manifest import utc_now_iso

HEALTH_STATUSES = [
    "GUI_READY",
    "ROSCORE_READY",
    "MAVROS_UAV1_CONNECTED",
    "MAVROS_UAV2_CONNECTED",
    "COURSE_READY",
]


def new_health(stack_id: str) -> dict:
    return {
        "schema_version": 1,
        "stack_id": stack_id,
        "checked_at_utc": utc_now_iso(),
        "all_ready": False,
        "statuses": {},
    }


def merge_status(health: dict, name: str, ready: bool, detail: str = "") -> None:
    if name not in HEALTH_STATUSES:
        raise ValueError(f"unknown health status: {name}")
    health["statuses"][name] = {
        "ready": bool(ready),
        "detail": str(detail),
        "checked_at_utc": utc_now_iso(),
    }
    health["checked_at_utc"] = utc_now_iso()
    health["all_ready"] = all_ready(health)


def status_ready(health: dict, name: str) -> bool:
    return bool(health["statuses"][name]["ready"])


def all_ready(health: dict) -> bool:
    if set(health.get("statuses", {})) != set(HEALTH_STATUSES):
        return False
    return all(s["ready"] for s in health["statuses"].values())


def validate_health(health: dict) -> None:
    for field in ("schema_version", "stack_id", "checked_at_utc", "all_ready", "statuses"):
        if field not in health:
            raise ValueError(f"health missing field: {field}")
    unknown = set(health["statuses"]) - set(HEALTH_STATUSES)
    if unknown:
        raise ValueError(f"health has unknown statuses: {sorted(unknown)}")


def save_health(health: dict, path: Path) -> None:
    validate_health(health)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(health, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_health(path: Path) -> dict:
    health = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_health(health)
    return health


def health_summary(health: dict) -> str:
    parts = []
    for name in HEALTH_STATUSES:
        status = health.get("statuses", {}).get(name)
        parts.append(f"{name}={'READY' if status and status['ready'] else 'NOT_READY'}")
    return " ".join(parts)
