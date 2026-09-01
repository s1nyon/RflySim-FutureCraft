#!/usr/bin/env python3
"""Offline fake-SDK and reversible-file tests for the V2 scene loader."""

import argparse
import copy
import hashlib
import json
import subprocess
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


class FailingApi(FakeApi):
    def sendUE4PosScale(self, **kwargs):
        if len(self.created) == 3:
            raise RuntimeError("injected SDK failure")
        super().sendUE4PosScale(**kwargs)


def sha(data): return hashlib.sha256(data).hexdigest()


def expect_manifest_rejected(load_scene, spec, manifest, receipt, marker_dir):
    try:
        load_scene(
            FakeApi(),
            spec,
            manifest,
            receipt,
            marker_dir,
            -1,
            sleep=lambda _: None,
            asset_path=None,
        )
    except ValueError as exc:
        assert "manifest" in str(exc).lower()
    else:
        raise AssertionError("tampered entity manifest must fail closed")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", default="."); args = parser.parse_args()
    root = Path(args.project_root).resolve(); sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_geometry import load_spec
    from competition_course_artifacts import generate_artifacts
    from competition_course_ue_loader import installed_asset_transaction, load_scene, unload_scene

    spec = load_spec(root / "config/maps/competition_course_v2.json")

    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp); generated = temp / "generated"
        generate_artifacts(root / "config/maps/competition_course_v2.json", generated)
        manifest = json.loads((generated / "entity_manifest.json").read_text(encoding="utf-8"))
        tampered_manifests = []
        changed_center = copy.deepcopy(manifest)
        changed_center["entities"][0]["center"][0] += 0.25
        tampered_manifests.append(changed_center)
        changed_scale = copy.deepcopy(manifest)
        changed_scale["entities"][0]["scale"][2] += 0.25
        tampered_manifests.append(changed_scale)
        changed_id = copy.deepcopy(manifest)
        changed_id["entities"][0]["id"] += 500
        tampered_manifests.append(changed_id)
        added_entity = copy.deepcopy(manifest)
        extra = copy.deepcopy(added_entity["entities"][0])
        extra["id"] = 15998
        extra["name"] = "tampered_extra"
        added_entity["entities"].append(extra)
        tampered_manifests.append(added_entity)
        for index, tampered in enumerate(tampered_manifests):
            assert tampered["spec_sha256"] == spec["spec_sha256"]
            expect_manifest_rejected(
                load_scene,
                spec,
                tampered,
                temp / "tampered_receipt_{}.json".format(index),
                generated / "aruco",
            )

        tampered_generated = temp / "tampered_generated"
        tampered_generated.mkdir()
        (tampered_generated / "entity_manifest.json").write_text(
            json.dumps(changed_center), encoding="utf-8"
        )
        dry_run = subprocess.run(
            [
                sys.executable,
                str(root / "future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_ue_loader.py"),
                "--spec",
                str(root / "config/maps/competition_course_v2.json"),
                "--generated",
                str(tampered_generated),
                "--receipt",
                str(temp / "dry_run_receipt.json"),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )
        assert dry_run.returncode != 0, dry_run.stdout

        receipt = temp / "receipt.json"
        receipt.write_text(json.dumps({"spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only", "created_ids": [15100, 15120]}), encoding="utf-8")
        api = FakeApi()
        result = load_scene(api, spec, manifest, receipt, generated / "aruco", -1, sleep=lambda _: None, asset_path=None)
        assert api.destroyed == [(15100, -1), (15120, -1)]
        assert len(result["created_ids"]) == len(manifest["entities"])
        assert set(result["created_ids"]) == {item["id"] for item in manifest["entities"]}
        assert len([call for call in api.created if call[0] == "new"]) == 2
        wall_call = next(call[1] for call in api.created if call[0] == "scale" and call[1]["copterID"] == 15000)
        assert wall_call["Scale"] == [4.5, 0.15, 2.5 / 3.0]
        static_call = next(call[1] for call in api.created if call[0] == "scale" and call[1]["copterID"] == 15100)
        assert static_call["Scale"] == [0.35, 0.25, 0.3]
        assert len(api.ext) == 2
        assert [call["ActExt"][:2] for call in api.ext] == [[0.6, 0.8], [0.6, 0.8]]
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
        failing_receipt = temp / "failed_receipt.json"
        failing_api = FailingApi()
        try:
            load_scene(failing_api, spec, manifest, failing_receipt, generated / "aruco", -1, sleep=lambda _: None, asset_path=None)
        except RuntimeError as exc:
            assert "injected SDK failure" in str(exc)
        else:
            raise AssertionError("injected SDK failure must propagate")
        assert failing_api.destroyed == [(item[1]["copterID"], -1) for item in failing_api.created]
        assert not failing_receipt.exists()
        failure = json.loads((temp / "load_failure_receipt.json").read_text(encoding="utf-8"))
        assert failure["load_result"] == "ROLLED_BACK"
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
