#!/usr/bin/env python3
"""Generate deterministic offline artifacts for an asset calibration scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List

from asset_catalog import AssetCandidate, CalibrationCatalog, load_catalog, profile_id
from calibration_geometry import enu_to_ned, validate_station_layout, yaw_enu_to_ned


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _asset_dict(asset: AssetCandidate) -> Dict[str, object]:
    position_ned = enu_to_ned(asset.position_enu)
    return {
        "class_id": asset.class_id,
        "declared_bounds_m": list(asset.declared_bounds),
        "intended_roles": list(asset.intended_roles),
        "key": asset.key,
        "object_id": asset.object_id,
        "official_source": asset.official_source,
        "position_enu_m": list(asset.position_enu),
        "position_vendor_ned_m": list(position_ned),
        "scale": list(asset.scale),
        "variant": asset.variant,
        "yaw_enu_rad": asset.yaw_enu_rad,
        "yaw_vendor_ned_rad": yaw_enu_to_ned(asset.yaw_enu_rad),
    }


def resolved_assets(catalog: CalibrationCatalog) -> List[Dict[str, object]]:
    return [_asset_dict(asset) for asset in sorted(catalog.assets, key=lambda item: item.object_id)]


def _svg(catalog: CalibrationCatalog) -> str:
    xmin, xmax, ymin, ymax = catalog.zone_bounds
    padding = 1.0
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{} {} {} {}">'.format(
            xmin - padding, -ymax - padding, xmax - xmin + 2 * padding, ymax - ymin + 2 * padding
        ),
        '<rect x="{}" y="{}" width="{}" height="{}" fill="#f7f7f2" stroke="#222" stroke-width="0.04"/>'.format(
            xmin, -ymax, xmax - xmin, ymax - ymin
        ),
        '<g stroke="#d6d6ce" stroke-width="0.015">',
    ]
    for x in range(int(xmin), int(xmax) + 1):
        rows.append('<line x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(x, -ymax, x, -ymin))
    for y in range(int(ymin), int(ymax) + 1):
        rows.append('<line x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(xmin, -y, xmax, -y))
    rows.append("</g>")
    for asset in sorted(catalog.assets, key=lambda item: item.object_id):
        rows.append(
            '<rect x="{:.3f}" y="{:.3f}" width="{:.3f}" height="{:.3f}" fill="#78a7d3" stroke="#174a74" stroke-width="0.03"/>'.format(
                asset.position_enu.x - asset.declared_bounds.x / 2.0,
                -asset.position_enu.y - asset.declared_bounds.y / 2.0,
                asset.declared_bounds.x,
                asset.declared_bounds.y,
            )
        )
        rows.append(
            '<text x="{:.3f}" y="{:.3f}" font-size="0.22" text-anchor="middle">{}</text>'.format(
                asset.position_enu.x, -asset.position_enu.y, asset.key
            )
        )
    rows.extend(
        [
            '<text x="{}" y="{}" font-size="0.24">1 m grid</text>'.format(xmin, -ymin + 0.45),
            '<text x="{}" y="{}" font-size="0.24">+X East</text>'.format(xmin, -ymin + 0.8),
            '<text x="{}" y="{}" font-size="0.24">+Y North</text>'.format(xmin + 2.0, -ymin + 0.8),
            '<text x="{}" y="{}" font-size="0.16">catalog_sha256 {}</text>'.format(xmin, -ymin + 1.15, catalog.sha256),
            "</svg>",
        ]
    )
    return "\n".join(rows) + "\n"


def generate_artifacts(catalog_path: Path, output_dir: Path) -> Dict[str, object]:
    catalog = load_catalog(catalog_path)
    report = validate_station_layout(catalog)
    report.update({"catalog_name": catalog.catalog_name, "catalog_sha256": catalog.sha256})
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = resolved_assets(catalog)
    _write_json(
        output_dir / "resolved_scene.json",
        {
            "arming_request": False,
            "assets": assets,
            "base_map": catalog.base_map,
            "catalog_sha256": catalog.sha256,
            "map_change": False,
            "owned_id_range": list(catalog.owned_id_range),
        },
    )
    _write_json(
        output_dir / "declared_profiles.json",
        {
            "catalog_sha256": catalog.sha256,
            "profiles": [
                {
                    "approved_roles": [],
                    "catalog_sha256": catalog.sha256,
                    "class_id": asset.class_id,
                    "evidence_state": "DECLARED",
                    "measurements": {},
                    "object_id": asset.object_id,
                    "official_source": asset.official_source,
                    "profile_id": profile_id(asset),
                    "variant": asset.variant,
                }
                for asset in sorted(catalog.assets, key=lambda item: item.object_id)
            ],
            "schema_version": 1,
        },
    )
    _write_json(output_dir / "validation_report.json", report)
    (output_dir / "calibration_preview.svg").write_text(_svg(catalog), encoding="utf-8")
    names = ["calibration_preview.svg", "declared_profiles.json", "resolved_scene.json", "validation_report.json"]
    manifest = {"artifacts": {name: _sha256(output_dir / name) for name in names}, "catalog_sha256": catalog.sha256}
    _write_json(output_dir / "artifact_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate_artifacts(args.catalog, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
