# Future Aircraft Sim Stage 3 Logging and Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first repeatable logging and scoring pipeline: `mission_events.jsonl` input, `score_summary.json` output, timestamped log directories, and validation fixtures.

**Architecture:** Keep Stage 3 independent of live ROS so it can be tested before flight. A pure Python CLI under `future_aircraft_ws/src/multi_uav_mission/scripts` parses JSONL mission events and computes success/failure, timing, min distance, OFFBOARD loss, collision/timeout flags, and target count. Batch wrappers create log directories and run the scorer.

**Tech Stack:** Python 3 standard library, PowerShell validation, Windows batch wrappers, JSONL logs, JSON summaries.

## Global Constraints

- Do not require ROS to validate Stage 3.
- Preserve Stage 0/1/2 launch scripts.
- Output summary path must be deterministic when passed explicitly.
- Scoring must fail clearly on malformed JSONL or missing required fields.

---

### Task 1: Stage 3 Validation

**Files:**
- Create: `scripts/validate_stage3.ps1`

**Interfaces:**
- Consumes: Stage 3 files and fixture.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage3.ps1`.

- [x] **Step 1: Write failing validation**
- [x] **Step 2: Confirm validation fails before Stage 3 files exist**

### Task 2: Scoring Tool and Fixture

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/package.xml`
- Create: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py`
- Create: `tests/fixtures/stage3/mission_events.jsonl`
- Create: `tests/fixtures/stage3/expected_score_summary.json`

**Interfaces:**
- Consumes: JSONL events with `time`, `event`, and optional `uav`, `distance_m`, `target_id`, `target_type` fields.
- Produces: summary JSON with `success`, `failure_reasons`, `mission_start_time`, `mission_end_time`, `duration_s`, `min_uav_distance_m`, `offboard_loss_count`, `collision_count`, `timeout_count`, `targets_detected_count`.

- [x] **Step 1: Implement parser and scoring behavior**
- [x] **Step 2: Validate fixture output matches expected summary**

### Task 3: Log Directory and Docs

**Files:**
- Modify: `scripts/record_logs.bat`
- Create: `scripts/create_log_run.bat`
- Modify: `README.md`
- Modify: `agent2Read.md`

**Interfaces:**
- Consumes: `logs` directory.
- Produces: timestamped log run directories and documented scoring command.

- [x] **Step 1: Add log directory creation command**
- [x] **Step 2: Document Stage 3 commands**
- [x] **Step 3: Add task-book execution record**
- [x] **Step 4: Run Stage 0/1/2/3 validation**

## Self-Review

- Spec coverage: Covers Stage 3 minimal logs and scoring, not live ROS bag recording.
- Placeholder scan: Scoring has concrete input/output fields and fixture-based validation.
- Risk note: Live rosbag integration remains a later step once the ROS launch is live-validated.
