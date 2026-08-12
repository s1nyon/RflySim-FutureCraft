#!/usr/bin/env python3
"""DryRun and bounded-loader contracts for the near-field showcase."""

import argparse
import importlib.util
import json
import sys
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

    class Client:
        def __init__(self): self.created = []; self.destroyed = []
        def sendUE4PosScale2Ground(self, **kwargs): self.created.append(kwargs)
        def sendUE4Destroy(self, object_id, window_id): self.destroyed.append((object_id, window_id))
    client = Client()
    cli.place_showcase(client, catalog, placements, window_id=0, repeat=1, delay_s=0)
    assert len(client.created) == 10
    assert [item["copterID"] for item in client.created] == list(range(13000, 13010))
    assert all(item["windowID"] == 0 for item in client.created)
    cli.remove_showcase(client, catalog, placements, window_id=0, repeat=1, delay_s=0)
    assert client.destroyed == [(item, 0) for item in range(13000, 13010)]
    print("asset showcase CLI: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
