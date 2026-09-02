#!/usr/bin/env python3
"""Contracts for RflySim official-asset metadata normalization."""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import time
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Raw:
    def __init__(self, timestamp, pos=(4, 3, -2), attitude=(0, 0, 1), origin=(4, 3, -1.25), extent=(0.25, 0.5, 0.75)):
        self.timestmp = timestamp
        self.PosUE = pos
        self.angEuler = attitude
        self.boxOrigin = origin
        self.BoxExtent = extent
        self.hasUpdate = True


class FakeClient:
    def __init__(self, raws):
        self.raws = list(raws)
        self.requested = []
        self.initialized = False
        self.initialize_count = 0
        self.shutdown_count = 0

    def reqCamCoptObj(self, kind, object_id):
        self.requested.append((kind, object_id))

    def initUE4MsgRec(self):
        self.initialized = True
        self.initialize_count += 1

    def endUE4MsgRec(self):
        self.shutdown_count += 1

    def getCamCoptObj(self, kind, object_id):
        if not self.raws:
            return None
        return self.raws.pop(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-module", type=Path, required=True)
    parser.add_argument("--geometry-module", type=Path, required=True)
    parser.add_argument("--metadata-module", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    catalog_module = load_module("asset_catalog", args.catalog_module)
    load_module("calibration_geometry", args.geometry_module)
    metadata = load_module("object_metadata", args.metadata_module)
    candidate = catalog_module.load_catalog(args.catalog).assets[0]

    base = time.time()
    samples = [
        metadata.normalize_sample(Raw(10.0 + index * 0.1), received_at_unix_s=base + index * 0.1)
        for index in range(5)
    ]
    analysis = metadata.analyze_samples(candidate, samples, now=base + 0.5)
    assert analysis["evidence_state"] == "METADATA_MEASURED"
    assert analysis["raw_vendor"]["half_extent_m"] == [0.25, 0.5, 0.75]
    assert analysis["full_dimensions_m"] == [0.5, 1.0, 1.5]
    assert analysis["converted_enu"]["position_m"] == [3.0, 4.0, 2.0]
    assert analysis["converted_enu"]["ground_offset_m"] == 0.5
    assert "yaw_rad" in analysis["converted_enu"]
    assert analysis["sample_count"] == 5
    assert analysis["maximum_position_delta_m"] == 0.0
    assert analysis["maximum_extent_delta_m"] == 0.0
    static_samples = [
        metadata.normalize_sample(Raw(10.0), received_at_unix_s=base + index * 0.1)
        for index in range(3)
    ]
    assert metadata.analyze_samples(candidate, static_samples, now=base + 0.3)["evidence_state"] == "METADATA_MEASURED"
    profile = metadata.build_metadata_profile(candidate, analysis, {"run_id": "run-1", "stack_instance_id": "stack-1"})
    assert profile["schema_version"] == 1
    assert profile["evidence_state"] == "METADATA_MEASURED"
    assert profile["approved_roles"] == []
    assert profile["measurements"]["full_dimensions_m"] == [0.5, 1.0, 1.5]
    assert profile["provenance"]["run_id"] == "run-1"
    assert profile["commanded_geometry"]["scale"] == list(candidate.scale)
    assert profile["commanded_geometry"]["position_enu_m"] == list(candidate.position_enu)

    rejected_cases = [
        (samples[:2], "INSUFFICIENT_SAMPLES"),
        ([metadata.normalize_sample(Raw(base + value)) for value in (0.2, 0.1, 0.3)], "DECREASING_VENDOR_TIMESTAMPS"),
        ([metadata.normalize_sample(Raw(value), received_at_unix_s=base - 20 + value) for value in (0, 0.1, 0.2)], "STALE_FINAL_SAMPLE"),
        ([metadata.normalize_sample(Raw(base + value, extent=(0.25 + value, 0.5, 0.75))) for value in (0, 0.1, 0.2)], "INCONSISTENT_EXTENT"),
    ]
    for candidate_samples, reason in rejected_cases:
        result = metadata.analyze_samples(candidate, candidate_samples, now=base + 0.5)
        assert result["evidence_state"] == "REJECTED"
        assert reason in result["rejection_reasons"]

    invalid_raws = [
        Raw(base, extent=(0, 1, 1)),
        Raw(base, pos=(math.nan, 0, 0)),
        Raw(base, pos=(True, 0, 0)),
    ]
    for raw in invalid_raws:
        try:
            metadata.normalize_sample(raw)
        except metadata.MetadataValidationError:
            pass
        else:
            raise AssertionError("invalid raw metadata accepted")

    live_raws = [Raw(base + index * 0.1) for index in range(3)]
    client = FakeClient(live_raws)
    metadata.initialize_metadata_receiver(client)
    captured = metadata.record_candidate(client, candidate, sample_count=3, timeout_s=1, poll_s=0)
    assert len(captured) == 3
    assert client.requested == [(1, candidate.object_id)]
    assert client.initialized is True
    assert client.initialize_count == 1
    assert all(raw.hasUpdate is False for raw in live_raws)
    try:
        metadata.record_candidate(FakeClient([]), candidate, sample_count=3, timeout_s=0.01, poll_s=0)
    except metadata.MetadataCaptureError as exc:
        assert "timeout" in str(exc)
        assert exc.samples == []
    else:
        raise AssertionError("metadata timeout did not fail")

    print("asset calibration metadata: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
