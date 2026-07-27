# Stage 6B Simulation Vision Target Provider Design

## Scope

Stage 6B adds a simulation-vision target provider without changing the mission executor's target result contract. The first implementation uses deterministic simulated detections from fixture/config files, not camera image processing, so the mission can validate the perception boundary before RflySim camera topics and detector models are stable.

This stage intentionally moves faster than the earlier micro-stages: target fixture parsing, confidence filtering, schema normalization, ROS service compatibility, executor regression, validation, and documentation ship as one larger checkpoint.

## Architecture

Add a new provider script and config:

```text
config/stage6b_sim_vision.json
future_aircraft_ws/src/multi_uav_mission/scripts/sim_vision_target_provider.py
scripts/validate_stage6b.ps1
tests/fixtures/stage6b/
```

The provider reads simulated detections that represent the output of a future RflySim vision pipeline. It normalizes them to the Stage 6A target result schema:

```text
simulated detections
    -> validate camera/source metadata
    -> filter by requested target types and minimum confidence
    -> normalize target_id, target_type, uav, frame_id, position, confidence
    -> write target_results.json or serve ROS Trigger response
```

The existing `target_provider.py` remains the ideal provider. `sim_vision_target_provider.py` is a second provider backend with the same external result schema. The mission executor does not need a new CLI flag or event format.

## Interfaces

Simulation vision provider CLI:

```text
sim_vision_target_provider.py --config config/stage6b_sim_vision.json --target-types color_label,qr_code,thermal_source --min-confidence 0.6 --output target_results.json
sim_vision_target_provider.py --config config/stage6b_sim_vision.json --backend ros --service /mission/target_provider/query
```

Input config schema:

```json
{
  "source_mode": "sim_vision",
  "frame_id": "map",
  "default_min_confidence": 0.6,
  "detections": [
    {
      "detection_id": "cam_uav1_color_red_001",
      "target_id": "color_label_red",
      "target_type": "color_label",
      "uav": "uav1",
      "camera": "/uav1/rflysim/camera/front",
      "confidence": 0.92,
      "position": {"x": 3.18, "y": -0.42, "z": 1.02}
    }
  ]
}
```

Output schema remains compatible with Stage 6A:

```json
{
  "source_mode": "sim_vision",
  "frame_id": "map",
  "targets": [
    {
      "target_id": "color_label_red",
      "target_type": "color_label",
      "position": {"x": 3.18, "y": -0.42, "z": 1.02},
      "confidence": 0.92,
      "uav": "uav1"
    }
  ]
}
```

The executor's target validation must accept both `ideal` and `sim_vision` source modes. Event output keeps the same `target_detected` shape and records the provider `source_mode`.

## Error Handling

The provider exits non-zero for malformed JSON, missing `frame_id`, unsupported `source_mode`, duplicate `target_id` after filtering, missing target fields, non-numeric positions, confidence outside `[0, 1]`, unknown requested target types, or no detections passing the requested target type and confidence filters.

The ROS backend returns the same deterministic JSON payload through `std_srvs/Trigger`. If ROS packages are unavailable, the provider exits with a clear dependency error, matching the existing Stage 6A provider behavior.

The executor exits non-zero when target results use an unsupported source mode or invalid target schema.

## Testing

`scripts/validate_stage6b.ps1` is fully offline. It must:

- Run the simulation vision provider and compare `target_results.json` with a fixture.
- Run a negative low-confidence filter check and verify it fails cleanly.
- Generate the Stage 5B live mission plan.
- Run `mission_executor.py` with `--target-results` from the simulation vision provider.
- Compare `mission_events.jsonl`, `executor_trace.json`, and `score_summary.json` against Stage 6B fixtures.
- Run Stage 6A validation as a regression.

The validator must not start ROS, RflySim, PX4, MAVROS, WSL GUI, ego-swarm runtime, OpenCV, or model inference.

## Live Gate

After Stage 6B, a live simulation run can swap the target provider service from ideal data to simulated vision data without changing `mission_executor.py` invocation. Real camera and detector integration remains a later stage; this stage only locks the provider boundary and target result contract.
