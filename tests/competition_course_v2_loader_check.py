#!/usr/bin/env python3
"""Offline fake-SDK and reversible-file tests for the V2 scene loader."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


class FakeApi:
    def __init__(self):
        self.created = []
        self.destroyed = []
        self.ext = []
        self.commands = []

    def sendUE4Destroy(self, object_id, window_id): self.destroyed.append((object_id, window_id))
    def sendUE4PosScale(self, **kwargs): self.created.append(("scale", kwargs))
    def sendUE4PosNew(self, **kwargs): self.created.append(("new", kwargs))
    def sendUE4ExtAct(self, **kwargs): self.ext.append(kwargs)
    def sendUE4Cmd(self, command, window_id): self.commands.append((command, window_id))


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", default="."); args = parser.parse_args()
    root = Path(args.project_root).resolve(); sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_geometry import load_spec
    from competition_course_ue_loader import installed_asset_transaction, load_scene, unload_scene

    spec = load_spec(root / "config/maps/competition_course_v2.json")
    generated = root / "generated/competition_course_v2"
    assert (generated / "entity_manifest.json").exists(), "run generator before loader check"
    manifest = json.loads((generated / "entity_manifest.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp); receipt = temp / "receipt.json"
        receipt.write_text(json.dumps({"spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only", "created_ids": [15100, 15120]}), encoding="utf-8")
        api = FakeApi()
        result = load_scene(api, spec, manifest, receipt, generated / "aruco", -1, sleep=lambda _: None, asset_path=None)
        assert api.destroyed == [(15100, -1), (15120, -1)]
        assert len(result["created_ids"]) == len(manifest["entities"])
        assert set(result["created_ids"]) == {item["id"] for item in manifest["entities"]}
        assert len([call for call in api.created if call[0] == "new"]) == 2
        assert len(api.ext) == 2
        assert ("RflyChangeViewKeyCmd P", -1) in api.commands
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        assert saved["cleanup_policy"] == "receipt_only"
        stop_file = temp / "motion.stop"
        unload_api = FakeApi()
        unloaded = unload_scene(unload_api, spec, receipt, -1, stop_file, sleep=lambda _: None)
        assert unload_api.destroyed == [(value, -1) for value in saved["created_ids"]]
        assert unloaded["destroyed_ids"] == saved["created_ids"]
        assert stop_file.exists() and not receipt.exists()
        assert (temp / "unload_receipt.json").exists()

        original, replacement = b"original-installed-asset", b"new-marker"
        installed = temp / "Aruco.png"; source = temp / "marker.png"
        installed.write_bytes(original); source.write_bytes(replacement)
        with installed_asset_transaction(source, installed, sha(original)) as evidence:
            assert installed.read_bytes() == replacement
            assert evidence["replacement_sha256"] == sha(replacement)
        assert installed.read_bytes() == original
        assert not list(temp.glob("Aruco.png.*.tmp"))
        try:
            with installed_asset_transaction(source, installed, "0" * 64): pass
        except ValueError as exc:
            assert "fingerprint" in str(exc)
        else:
            raise AssertionError("wrong installed fingerprint must fail closed")
        assert installed.read_bytes() == original
        try:
            with installed_asset_transaction(source, installed, sha(original)):
                raise RuntimeError("injected failure")
        except RuntimeError:
            pass
        assert installed.read_bytes() == original
    print("competition_course_v2_loader_check: PASS")


if __name__ == "__main__": main()
