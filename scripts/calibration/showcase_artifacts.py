#!/usr/bin/env python3
"""Deterministic JSON and SVG artifacts for the near-field showcase."""

import hashlib
import json
from pathlib import Path


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_showcase_artifacts(output, placements, report):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    resolved = [{
        "class_id": item.class_id, "expected_dimensions_m": list(item.expected_dimensions),
        "key": item.key, "measured_dimensions_m": list(item.measured_dimensions),
        "object_id": item.object_id, "position_enu_m": list(item.position_enu), "scale": list(item.scale),
    } for item in placements]
    _write(output / "resolved_showcase.json", resolved)
    _write(output / "validation_report.json", report)
    circles = "".join('<circle cx="{}" cy="{}" r="8"/><text x="{}" y="{}">{}</text>'.format(
        40 + (item.position_enu.y + 5) * 32, 70 + (item.position_enu.x - 11) * 80,
        50 + (item.position_enu.y + 5) * 32, 74 + (item.position_enu.x - 11) * 80, item.key
    ) for item in placements)
    (output / "showcase_preview.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="460" height="260"><style>text{{font:10px sans-serif}}circle{{fill:#ff9f1c}}</style>{}</svg>\n'.format(circles), encoding="utf-8"
    )
    files = ("resolved_showcase.json", "showcase_preview.svg", "validation_report.json")
    manifest = {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in files}
    _write(output / "artifact_manifest.json", {"artifacts": manifest})
    return {"artifacts": manifest}
