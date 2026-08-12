#!/usr/bin/env python3
"""Offline contracts for the DryRun-first asset calibration CLI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cli, *args):
    return subprocess.run([sys.executable, str(cli), *map(str, args)], check=False, capture_output=True, text=True)


def load_cli(path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("calibration_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoMetadataClient:
    def __init__(self):
        self.initialize_count = 0
        self.shutdown_count = 0

    def reqCamCoptObj(self, *_args):
        pass

    def initUE4MsgRec(self):
        self.initialize_count += 1

    def endUE4MsgRec(self):
        self.shutdown_count += 1

    def getCamCoptObj(self, *_args):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()

    cli_module = load_cli(args.cli)
    catalog = cli_module.load_catalog(args.catalog)

    source = args.cli.read_text(encoding="utf-8")
    for forbidden in ("RflyChangeMapbyName", "set_mode", "OFFBOARD", "wsl --shutdown", "taskkill", "pkill"):
        assert forbidden not in source, forbidden

    for command in ("load", "remove"):
        result = run(args.cli, command, "--catalog", args.catalog)
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout)
        assert receipt["mode"] == "dry-run"
        assert receipt["map_change"] is False
        assert receipt["arming_request"] is False
        assert receipt["acted_on_ids"] == list(range(13000, 13010))
        if command == "load":
            assert len(receipt["placements"]) == 10
            assert set(receipt["placements"][0]) == {
                "class_id", "object_id", "position_enu_m", "position_ned_m", "scale", "yaw_enu_rad", "yaw_ned_rad"
            }

    with tempfile.TemporaryDirectory(prefix="asset_cli_") as temp_dir:
        root = Path(temp_dir)
        record = run(args.cli, "record", "--catalog", args.catalog, "--output", root / "record")
        assert record.returncode == 0, record.stderr
        receipt = json.loads(record.stdout)
        assert receipt["mode"] == "dry-run" and receipt["arming_request"] is False
        assert not (root / "record").exists()

        outputs = [root / "a", root / "b"]
        for output in outputs:
            generated = run(args.cli, "generate", "--catalog", args.catalog, "--output", output)
            assert generated.returncode == 0, generated.stderr
        assert sorted(path.name for path in outputs[0].iterdir()) == sorted(path.name for path in outputs[1].iterdir())
        for path in outputs[0].iterdir():
            assert path.read_bytes() == (outputs[1] / path.name).read_bytes()

        invalid = root / "invalid.json"
        invalid.write_text("{}", encoding="utf-8")
        failed = run(args.cli, "generate", "--catalog", invalid, "--output", root / "bad")
        assert failed.returncode != 0
        assert "schema_version" in failed.stderr

        rejected_dir = root / "rejected"
        no_metadata = NoMetadataClient()
        manifest, passed = cli_module._record(no_metadata, catalog, rejected_dir, 3, 0.0001, "run-timeout", "stack-1")
        assert passed is False
        assert len(manifest["profiles"]) == len(catalog.assets)
        assert manifest["states"] == ["REJECTED"] * len(catalog.assets)
        assert no_metadata.initialize_count == 1
        assert no_metadata.shutdown_count == 1
        for profile_name in manifest["profiles"]:
            profile = json.loads((rejected_dir / profile_name).read_text(encoding="utf-8"))
            assert "CAPTURE_TIMEOUT" in profile["measurements"]["rejection_reasons"]

        for missing in ("--run-id", "--stack-instance-id"):
            live = run(
                args.cli, "record", "--catalog", args.catalog, "--output", root / "live",
                "--execute", *( ["--stack-instance-id", "stack-1"] if missing == "--run-id" else ["--run-id", "run-1"] )
            )
            assert live.returncode != 0
            assert missing[2:] in live.stderr

    print("asset calibration CLI: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
