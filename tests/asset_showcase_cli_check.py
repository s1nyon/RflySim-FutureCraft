#!/usr/bin/env python3
"""DryRun and bounded-loader contracts for the near-field showcase."""

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--showcase", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.cli.parent))
    spec = importlib.util.spec_from_file_location("calibration_cli", args.cli)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    catalog = cli.load_catalog(args.catalog)
    showcase = cli.load_showcase(args.showcase)
    placements = cli.resolve_showcase(showcase, catalog)
    receipt = cli._showcase_dry_receipt("showcase-load", catalog, placements)
    assert receipt["acted_on_ids"] == list(range(13000, 13010))
    assert receipt["mode"] == "dry-run" and receipt["map_change"] is False
    assert len(receipt["placements"]) == 10
    assert receipt["placements"][0]["fit_ground"] is True
    assert receipt["placements"][0]["position_ned_m"] == [-5.0, 11.0, -0.0]
    assert receipt["placements"][0]["yaw_enu_rad"] == 0.0
    assert receipt["placements"][0]["yaw_ned_rad"] == 1.5707963267948966

    for command in ("showcase-load", "showcase-remove"):
        completed = subprocess.run(
            [sys.executable, str(args.cli), command, "--catalog", str(args.catalog),
             "--showcase", str(args.showcase)], capture_output=True, text=True, check=False
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout)["mode"] == "dry-run"

    class Client:
        def __init__(self): self.created = []; self.destroyed = []
        def sendUE4PosScale2Ground(self, **kwargs): self.created.append(kwargs)
        def sendUE4Destroy(self, object_id, window_id): self.destroyed.append((object_id, window_id))
    client = Client()
    cli._create_client = lambda _root: client
    assert cli.main(["showcase-load", "--catalog", str(args.catalog), "--showcase", str(args.showcase),
                     "--window-id", "0", "--execute"]) == 0
    assert len(client.created) == 30
    assert [item["copterID"] for item in client.created[::3]] == list(range(13000, 13010))
    assert all(item["windowID"] == 0 for item in client.created)
    assert cli.main(["showcase-remove", "--catalog", str(args.catalog), "--showcase", str(args.showcase),
                     "--window-id", "0", "--execute"]) == 0
    assert client.destroyed == [(item, 0) for item in range(13000, 13010) for _ in range(3)]

    for bad_window in ("-1", "1"):
        try:
            cli.main(["showcase-load", "--catalog", str(args.catalog), "--showcase", str(args.showcase),
                      "--window-id", bad_window, "--execute"])
            raise AssertionError("non-zero showcase window accepted")
        except SystemExit as exc:
            assert exc.code == 2
    assert len(client.created) == 30

    for action in (cli.place_showcase, cli.remove_showcase):
        try:
            action(client, catalog, placements, window_id=0, repeat=0, delay_s=0)
            raise AssertionError("zero-repeat showcase action accepted")
        except ValueError:
            pass

    raw = json.loads(args.showcase.read_text(encoding="utf-8"))
    raw["stations"][0]["position"] = [16.0, -0.7, 0.0]
    with tempfile.TemporaryDirectory() as temp_dir:
        unsafe = Path(temp_dir) / "unsafe.json"
        unsafe.write_text(json.dumps(raw), encoding="utf-8")
        try:
            cli.main(["showcase-load", "--catalog", str(args.catalog), "--showcase", str(unsafe)])
            raise AssertionError("unsafe showcase geometry accepted")
        except cli.ShowcaseValidationError:
            pass
    print("asset showcase CLI: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
