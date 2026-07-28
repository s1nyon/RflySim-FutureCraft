# Stage 6B Simulation Vision Target Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simulation-vision target provider that emits the existing Stage 6A target result schema, and make the mission executor accept that provider output without changing downstream mission behavior.

**Architecture:** Keep the current ideal target provider intact and add a second provider backend for simulated vision detections. Both providers normalize to the same `target_results.json` contract, and the executor only learns about source mode and filtering differences through validation and event metadata. Validation stays offline and regression-focused.

**Tech Stack:** Python 3 standard library, optional ROS1 `rospy` and `std_srvs`, PowerShell validation, JSON/JSONL fixtures, existing Stage 5B/5E mission chain.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Stage 6B offline validation must not start RflySim, ROS, PX4, MAVROS, WSL GUI, ego-swarm runtime, OpenCV, or model inference.
- Keep `/uav1` and `/uav2` as the only supported UAV ids.
- Preserve Stage 5A `mission_events.jsonl` compatibility.
- Keep the Stage 6A ideal target provider unchanged.
- The first Stage 6B provider source mode is `sim_vision`.

---

### Task 1: Stage 6B Validation Harness

**Files:**
- Create: `scripts/validate_stage6b.ps1`
- Create: `tests/stage6b_ros_bridge_check.py`
- Create directory: `tests/fixtures/stage6b`

**Interfaces:**
- Consumes: `target_provider.py`, `sim_vision_target_provider.py`, `mission_executor.py`, `live_mission_contract.py`, Stage 6A validation, Stage 6B fixtures.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage6b.ps1`

- [ ] **Step 1: Write the failing validation**

Create `scripts/validate_stage6b.ps1` so it requires:

```text
config/stage5_behavior_tree.json
config/stage5_live_mission.json
config/stage6b_sim_vision.json
future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
future_aircraft_ws/src/multi_uav_mission/scripts/sim_vision_target_provider.py
future_aircraft_ws/src/multi_uav_mission/scripts/target_provider.py
scripts/validate_stage6a.ps1
tests/fixtures/stage6b/expected_target_results.json
tests/fixtures/stage6b/expected_executor_trace.json
tests/fixtures/stage6b/expected_mission_events.jsonl
tests/fixtures/stage6b/expected_score_summary.json
```

The validator should:

1. Run `sim_vision_target_provider.py` in dry-run mode with `--target-types color_label,qr_code,thermal_source --min-confidence 0.6`.
2. Compare the generated `target_results.json` against `tests/fixtures/stage6b/expected_target_results.json`.
3. Run a negative low-confidence case and confirm the provider exits non-zero when every detection is filtered out.
4. Generate the Stage 5B mission plan with `live_mission_contract.py`.
5. Run `mission_executor.py` with `--target-results` pointing to the Stage 6B provider output.
6. Compare executor trace, mission events, and score summary against fixtures.
7. Re-run `scripts/validate_stage6a.ps1` as a regression gate.

- [ ] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6b.ps1
```

Expected: FAIL because the Stage 6B provider, fixtures, and validation helper do not exist yet.

### Task 2: Simulation Vision Provider

**Files:**
- Create: `config/stage6b_sim_vision.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/sim_vision_target_provider.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `load_config(path: Path) -> dict`, `build_results(config: dict, target_types: list[str], min_confidence: float) -> dict`
- Produces: `target_results.json` and optional ROS `std_srvs/Trigger` service output

- [ ] **Step 1: Add simulation-vision config**

Create three deterministic detections in `config/stage6b_sim_vision.json`:

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
    },
    {
      "detection_id": "cam_uav2_qr_gate_001",
      "target_id": "qr_code_gate",
      "target_type": "qr_code",
      "uav": "uav2",
      "camera": "/uav2/rflysim/camera/front",
      "confidence": 0.88,
      "position": {"x": 4.62, "y": 0.36, "z": 1.10}
    },
    {
      "detection_id": "cam_uav1_thermal_001",
      "target_id": "thermal_source_1",
      "target_type": "thermal_source",
      "uav": "uav1",
      "camera": "/uav1/rflysim/camera/down",
      "confidence": 0.81,
      "position": {"x": 5.41, "y": -0.18, "z": 1.00}
    }
  ]
}
```

- [ ] **Step 2: Implement provider CLI**

Implement deterministic filtering by requested target types and minimum confidence. The provider must:

1. Validate config structure and `source_mode == "sim_vision"`.
2. Validate each detection has `detection_id`, `target_id`, `target_type`, `uav`, `camera`, `confidence`, and `position`.
3. Filter detections by `--target-types` and `--min-confidence`.
4. Normalize output to the Stage 6A schema with `source_mode`, `frame_id`, and `targets`.
5. Reject empty results after filtering with a non-zero exit code.

- [ ] **Step 3: Add ROS Trigger service mode**

Add `--backend ros --service /mission/target_provider/query` and serve the normalized JSON through `std_srvs/Trigger` in `response.message`.
Install the new script through `catkin_install_python(PROGRAMS ...)`.

### Task 3: Executor Compatibility for `sim_vision`

**Files:**
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py`
- Modify: `tests/stage6a_ros_bridge_check.py`

**Interfaces:**
- Consumes: `--target-results target_results.json` with `source_mode` equal to `ideal` or `sim_vision`
- Produces: `target_detected` events with provider metadata preserved

- [ ] **Step 1: Extend target result validation**

Update `validate_target_results` so it accepts `source_mode` values `ideal` and `sim_vision`. Keep the existing field validation for `targets[*]`.

- [ ] **Step 2: Preserve provider source mode in events**

When `CollaborativeTargetWork` emits `target_detected`, include the provider `source_mode` for every target. Keep the existing event shape and add only the new metadata field.

- [ ] **Step 3: Broaden the ROS bridge check**

Update `tests/stage6a_ros_bridge_check.py` or add Stage 6B assertions so the fake ROS service payload can use `source_mode == "sim_vision"` and still flow through `_call_service` without schema loss.

### Task 4: Fixtures, Docs, and Regression Gate

**Files:**
- Create: `tests/fixtures/stage6b/expected_target_results.json`
- Create: `tests/fixtures/stage6b/expected_executor_trace.json`
- Create: `tests/fixtures/stage6b/expected_mission_events.jsonl`
- Create: `tests/fixtures/stage6b/expected_score_summary.json`
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: deterministic Stage 6B provider output and executor output
- Produces: documented Stage 6B validation and live provider command

- [ ] **Step 1: Generate fixtures**

Run the Stage 6B provider and executor once with the exact command sequence the validator will use, then save the stable outputs into `tests/fixtures/stage6b`.

- [ ] **Step 2: Update docs**

Document:

1. The Stage 6B validation command.
2. The Stage 6B provider command.
3. The fact that `sim_vision` is still a boundary contract, not real detector inference.

- [ ] **Step 3: Verify and commit**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6b.ps1
```

Expected: PASS.

Commit with a message like:

```text
feat: add stage 6b simulation vision provider
```

## Self-Review

- Spec coverage: Covers validation harness, simulation-vision provider, executor compatibility, fixtures, docs, and Stage 6A regression.
- Placeholder scan: No TBD or TODO placeholders are present.
- Type consistency: `sim_vision` is the only new source mode; executor target result handling stays compatible with the Stage 6A schema.

