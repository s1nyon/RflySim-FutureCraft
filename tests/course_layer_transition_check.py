#!/usr/bin/env python3
"""Focused exact-ID ownership tests for project course transitions."""

import argparse
import json
import sys
import tempfile
from pathlib import Path


class FakeApi:
    def __init__(self):
        self.destroyed = []

    def sendUE4Destroy(self, object_id, window_id):
        self.destroyed.append((object_id, window_id))


def expect_error(function, needle):
    try:
        function()
    except ValueError as exc:
        assert needle in str(exc), (needle, str(exc))
    else:
        raise AssertionError("expected ValueError containing {!r}".format(needle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from course_layer_transition import build_transition_plan, execute_transition

    declared = {
        "predicted_narrow_course": [12001, 12002],
        "competition_course_v2": [15001, 15002],
    }
    plan = build_transition_plan("competition_course_v2", declared)
    assert plan["selected_course"] == "competition_course_v2"
    assert plan["destroy_ids"] == [12001, 12002, 15001, 15002]
    assert 9999 not in plan["destroy_ids"]
    reverse = build_transition_plan("predicted_narrow_course", declared)
    assert reverse["destroy_ids"] == plan["destroy_ids"]

    expect_error(lambda: build_transition_plan("unknown", declared), "unknown selected course")
    expect_error(lambda: build_transition_plan("competition_course_v2", {
        "predicted_narrow_course": [12001], "competition_course_v2": [12001]
    }), "declared by multiple courses")
    expect_error(lambda: build_transition_plan("competition_course_v2", {
        "predicted_narrow_course": [True], "competition_course_v2": [15001]
    }), "integer")
    expect_error(lambda: build_transition_plan("competition_course_v2", {
        "predicted_narrow_course": [12001, 12001], "competition_course_v2": [15001]
    }), "duplicate")

    plan["source_hashes"] = {
        "predicted_narrow_course": "a" * 64,
        "competition_course_v2": "b" * 64,
    }
    with tempfile.TemporaryDirectory() as temp:
        receipt_path = Path(temp) / "transition_receipt.json"
        api = FakeApi()
        receipt = execute_transition(api, plan, receipt_path, window_id=-1)
        assert api.destroyed == [(12001, -1), (12002, -1), (15001, -1), (15002, -1)]
        assert receipt["cleanup_policy"] == "exact_declared_ids"
        assert receipt["destroy_requested_ids"] == plan["destroy_ids"]
        assert receipt["command_status"] == "COMMANDS_SENT"
        assert receipt["selected_course"] == "competition_course_v2"
        assert receipt["source_hashes"] == plan["source_hashes"]
        assert receipt["window_id"] == -1
        assert receipt["timestamp_utc"].endswith("Z")
        assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt

    print("course_layer_transition_check: PASS")


if __name__ == "__main__":
    main()
