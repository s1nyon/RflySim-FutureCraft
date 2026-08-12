#!/usr/bin/env python3
"""Normalize and evaluate RflySim asset metadata without granting role approval."""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence

from asset_catalog import AssetCandidate, Vec3, profile_id
from calibration_geometry import ned_to_enu


class MetadataValidationError(ValueError):
    """Raised when a vendor metadata sample is malformed."""


class MetadataCaptureError(RuntimeError):
    """Raised when bounded live metadata capture cannot complete."""


@dataclass(frozen=True)
class MetadataSample:
    timestamp: float
    received_at_unix_s: float
    pos_vendor: Vec3
    attitude_vendor: Vec3
    box_origin_vendor: Vec3
    half_extent_vendor: Vec3


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetadataValidationError("{} must be numeric".format(label))
    result = float(value)
    if not math.isfinite(result):
        raise MetadataValidationError("{} must be finite".format(label))
    return result


def _vec3(value, label, positive=False):
    if value is None or len(value) != 3:
        raise MetadataValidationError("{} must contain three values".format(label))
    result = Vec3(*(_number(item, label) for item in value))
    if positive and min(result) <= 0.0:
        raise MetadataValidationError("{} must be positive".format(label))
    return result


def normalize_sample(raw, received_at_unix_s: float = None) -> MetadataSample:
    return MetadataSample(
        timestamp=_number(getattr(raw, "timestmp", None), "timestamp"),
        received_at_unix_s=_number(
            time.time() if received_at_unix_s is None else received_at_unix_s,
            "received_at_unix_s",
        ),
        pos_vendor=_vec3(getattr(raw, "PosUE", None), "PosUE"),
        attitude_vendor=_vec3(getattr(raw, "angEuler", None), "angEuler"),
        box_origin_vendor=_vec3(getattr(raw, "boxOrigin", None), "boxOrigin"),
        half_extent_vendor=_vec3(getattr(raw, "BoxExtent", None), "BoxExtent", positive=True),
    )


def _median_vec(samples, field):
    values = [getattr(sample, field) for sample in samples]
    return Vec3(
        *(statistics.median(getattr(value, axis) for value in values) for axis in ("x", "y", "z"))
    )


def _maximum_delta(samples, field):
    values = [getattr(sample, field) for sample in samples]
    return max(
        max(getattr(item, axis) for item in values) - min(getattr(item, axis) for item in values)
        for axis in ("x", "y", "z")
    )


def analyze_samples(
    candidate: AssetCandidate,
    samples: Sequence[MetadataSample],
    position_tolerance_m: float = 0.02,
    extent_tolerance_m: float = 0.01,
    stale_after_s: float = 2.0,
    now: float = None,
) -> Dict[str, object]:
    reasons = []
    if len(samples) < 3:
        reasons.append("INSUFFICIENT_SAMPLES")
    timestamps = [sample.timestamp for sample in samples]
    if any(second <= first for first, second in zip(timestamps, timestamps[1:])):
        reasons.append("NON_MONOTONIC_TIMESTAMPS")
    now = time.time() if now is None else float(now)
    if not samples or now - samples[-1].received_at_unix_s > stale_after_s:
        reasons.append("STALE_FINAL_SAMPLE")
    position_delta = _maximum_delta(samples, "pos_vendor") if samples else 0.0
    extent_delta = _maximum_delta(samples, "half_extent_vendor") if samples else 0.0
    if position_delta > position_tolerance_m:
        reasons.append("INCONSISTENT_POSITION")
    if extent_delta > extent_tolerance_m:
        reasons.append("INCONSISTENT_EXTENT")
    median_pos = _median_vec(samples, "pos_vendor") if samples else Vec3(0, 0, 0)
    median_attitude = _median_vec(samples, "attitude_vendor") if samples else Vec3(0, 0, 0)
    median_origin = _median_vec(samples, "box_origin_vendor") if samples else Vec3(0, 0, 0)
    median_extent = _median_vec(samples, "half_extent_vendor") if samples else Vec3(0, 0, 0)
    return {
        "converted_enu": {
            "box_origin_m": list(ned_to_enu(median_origin)),
            "position_m": list(ned_to_enu(median_pos)),
        },
        "evidence_state": "REJECTED" if reasons else "METADATA_MEASURED",
        "full_dimensions_m": [2.0 * value for value in median_extent],
        "maximum_extent_delta_m": extent_delta,
        "maximum_position_delta_m": position_delta,
        "raw_vendor": {
            "attitude_rad": list(median_attitude),
            "box_origin_m": list(median_origin),
            "half_extent_m": list(median_extent),
            "position_m": list(median_pos),
            "timestamps": timestamps,
            "received_at_unix_s": [sample.received_at_unix_s for sample in samples],
        },
        "rejection_reasons": reasons,
        "sample_count": len(samples),
    }


def build_metadata_profile(candidate: AssetCandidate, analysis: Dict[str, object], provenance: Dict[str, object]) -> Dict[str, object]:
    return {
        "approved_roles": [],
        "class_id": candidate.class_id,
        "evidence_state": analysis["evidence_state"],
        "measurements": analysis,
        "object_id": candidate.object_id,
        "official_source": candidate.official_source,
        "profile_id": profile_id(candidate),
        "provenance": dict(provenance),
        "schema_version": 1,
        "variant": candidate.variant,
    }


def record_candidate(client, candidate: AssetCandidate, sample_count: int, timeout_s: float, poll_s: float = 0.01) -> List[MetadataSample]:
    if sample_count < 1 or timeout_s <= 0.0:
        raise ValueError("sample_count and timeout_s must be positive")
    client.reqCamCoptObj(1, candidate.object_id)
    client.initUE4MsgRec()
    deadline = time.monotonic() + timeout_s
    samples: List[MetadataSample] = []
    while len(samples) < sample_count and time.monotonic() < deadline:
        raw = client.getCamCoptObj(1, candidate.object_id)
        if raw is not None and getattr(raw, "hasUpdate", False):
            samples.append(normalize_sample(raw))
            raw.hasUpdate = False
        if poll_s > 0.0:
            time.sleep(poll_s)
    if len(samples) != sample_count:
        raise MetadataCaptureError("metadata capture timeout for {}".format(candidate.key))
    return samples
