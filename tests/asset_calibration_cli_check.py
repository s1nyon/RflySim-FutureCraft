#!/usr/bin/env python3
"""Offline contracts for the DryRun-first asset calibration CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cli, *args):
    return subprocess.run([sys.executable, str(cli), *map(str, args)], check=False, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()

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

    print("asset calibration CLI: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
