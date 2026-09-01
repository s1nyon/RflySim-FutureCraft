# Competition Course V2 Navigation Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a repeatable UAV1 Section A navigation baseline with LiDAR-driven EGO avoidance, terminal settle, AUTO.LAND/disarm, continuous UAV2 isolation monitoring, and provenance-labelled collision/clearance evidence.

**Architecture:** Keep the V2 map JSON authoritative, derive both runtime entities and navigation geometry from it, and add one opt-in single-UAV runner around the existing dual sensor/Faster-LIO/EGO infrastructure. Extend the protected executor only through default-off settle and disarm verification fields; collect simulator truth in independent read-only evaluation processes that never publish planner/control data.

**Tech Stack:** Python 3.8, JSON, ROS1 Noetic, MAVROS, Faster-LIO, EGO-Swarm, RflySim UE API, PowerShell, Windows batch, WSL bash.

## Global Constraints

- Work on `infra/rviz-live-handoff-20260825`; do not push without explicit permission.
- Do not modify lifecycle, ownership, spawn attestation, cleanup, PX4, MAVROS, EGO/Faster-LIO internals or parameters, shared TF, mission C++, PBL-1 route, or dual-UAV behavior.
- `config/maps/competition_course_v2.json` is the only runtime geometry truth; navigation config contains no duplicated map coordinates.
- Planner decisions use only Mid360 → Faster-LIO/local map → EGO; simulator/spec truth is evaluation-only and publishes no ROS topic.
- Every production behavior starts with a focused failing test and completes a RED → GREEN cycle.
- Existing Stage 7/8 plans omit all new executor fields and retain byte-equivalent behavior.
- Any real stack start/stop/fresh-instance, OFFBOARD, or arm waits for a separate Red-Zone authorization Gate.
- Stop after UAV1 Section A; do not continue Corner A, Section B/C, UAV2 flight, or dual-UAV navigation.

---

### Task 1: Harden V2 runtime manifest authority

**Files:**
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_ue_loader.py`
- Modify: `tests/competition_course_v2_loader_check.py`
- Modify: `scripts/validate_competition_course_v2.ps1`

**Interfaces:**
- Consumes: `load_spec(path)` and `build_entity_manifest(spec)`.
- Produces: `validated_runtime_entities(spec, generated_manifest) -> list[dict]`; live load and dry-run both invoke this boundary before using entity payloads.

- [ ] **Step 1: Add RED tests for tampered generated payloads.**

  Extend the fake-SDK test so a manifest retaining the correct `spec_sha256` but changing an entity center, scale, ID, or adding an entity raises `ValueError`. Invoke `main([...,'--dry-run'])` against a tampered artifact and assert the same fail-closed result. The production mutation caught is “loader trusts payload because only its spec hash matches.”

- [ ] **Step 2: Run the loader check and observe the expected RED failure.**

  Run:

  ```powershell
  python tests/competition_course_v2_loader_check.py --project-root .
  ```

  Expected: FAIL because tampered entity payload currently reaches `load_scene`/dry-run.

- [ ] **Step 3: Implement full parity and derive runtime entities.**

  Add this boundary:

  ```python
  def validated_runtime_entities(spec, generated_manifest):
      expected = {
          "map_id": spec["map_id"],
          "coordinate_frame": "ENU",
          "spec_sha256": spec["spec_sha256"],
          "owned_cleanup": "receipt_only",
          "entities": build_entity_manifest(spec),
      }
      if generated_manifest != expected:
          raise ValueError("generated entity manifest does not match spec-derived payload")
      return expected["entities"]
  ```

  Import `build_entity_manifest`, make `main(argv=None)` testable, call parity before the dry-run branch, and make `load_scene` use the returned derived list rather than indexing the supplied artifact directly. Keep the generated manifest only as parity/debug evidence. Remove the duplicate `_create_marker` `asset_transaction` assignment.

- [ ] **Step 4: Run focused and complete V2 validation to GREEN.**

  ```powershell
  python tests/competition_course_v2_loader_check.py --project-root .
  powershell -ExecutionPolicy Bypass -File scripts/validate_competition_course_v2.ps1
  ```

  Expected: both exit 0; dry-run still reports all spec-derived IDs.

- [ ] **Step 5: Review and commit Gate 0.**

  ```powershell
  git diff --check
  git add future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_ue_loader.py tests/competition_course_v2_loader_check.py scripts/validate_competition_course_v2.ps1
  git commit -m "fix(map): harden competition course runtime manifest contract"
  ```

---

### Task 2: Add canonical transform and isolated UAV1 plans

**Files:**
- Create: `config/competition_course_v2_navigation.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_plan.py`
- Create: `tests/competition_course_v2_navigation_plan_check.py`

**Interfaces:**
- Produces: `world_to_local_xy(point, spawn, yaw_deg)`, `local_to_world_xy(point, spawn, yaw_deg)`, `build_plan(live_config, map_spec, nav_config, profile)`.
- Profiles: `short_smoke` and `full_section_a`.
- Plan metadata: `map_contract`, `navigation_contract`, `evaluation_contract`, and ordered single-UAV actions.

- [ ] **Step 1: Write RED transform tests with hand-derived literals.**

  Cover yaw `0/+90/-90/180°`, non-zero spawn translation, round trip, and current V2 endpoint `(7.0,0.7)`. Each expected value is a literal, not computed by the helper under test.

- [ ] **Step 2: Write RED plan tests.**

  Assert:

  - config has thresholds/timeouts/profile offsets but no `20.5`, `22.0`, or `23.0` map coordinates;
  - `short_smoke` target is `section_a.start + 0.75 m` along-track and is geometrically before both Section A obstacles;
  - `full_section_a` publishes exactly one planner goal at the spec-derived endpoint;
  - no UAV2 action calls set_mode/arming, publishes a goal, or verifies navigation;
  - stages are `preflight`, `takeoff`, `v2_navigation`, `terminal_settle`, `landing`, `report`;
  - terminal verify uses point distance with `tolerance_m=0.25`, `maximum_speed_mps=0.15`, `settle_duration_s=3.0`, and no `progress_mode=course_s`;
  - landing sets `require_disarmed=true` and a bounded `disarm_timeout_s`;
  - map SHA, section name, obstacle names and clearance policy are metadata derived from the map spec.

- [ ] **Step 3: Run plan tests and observe RED.**

  ```powershell
  python tests/competition_course_v2_navigation_plan_check.py --project-root .
  ```

  Expected: FAIL because the plan module/config do not exist.

- [ ] **Step 4: Implement the rigid transform and minimum plan builder.**

  Use:

  ```python
  local_x = cos(yaw) * dx + sin(yaw) * dy
  local_y = -sin(yaw) * dx + cos(yaw) * dy
  ```

  Derive the short goal by normalized Section A direction and validate its along-track relation to every obstacle tagged `segment=section_a`. Build geofence XY from transformed takeoff-area/Section A bounds plus a configured safety margin; use configured z bounds. Reuse topic names from `config/stage7_live_slam_ego_swarm.json` and generate actions only for UAV1.

- [ ] **Step 5: Run plan test and dry-run executor validation to GREEN.**

  ```powershell
  python tests/competition_course_v2_navigation_plan_check.py --project-root .
  python future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_plan.py --config config/stage7_live_slam_ego_swarm.json --map-spec config/maps/competition_course_v2.json --navigation-config config/competition_course_v2_navigation.json --profile short_smoke --output generated/competition_course_v2_navigation/short_smoke_plan.json
  python future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_plan.py --config config/stage7_live_slam_ego_swarm.json --map-spec config/maps/competition_course_v2.json --navigation-config config/competition_course_v2_navigation.json --profile full_section_a --output generated/competition_course_v2_navigation/full_section_a_plan.json
  ```

  Expected: exit 0; both plans validate, and only map-derived geometry appears.

- [ ] **Step 6: Review and commit transform/plan.**

  ```powershell
  git diff --check
  git add config/competition_course_v2_navigation.json future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_plan.py tests/competition_course_v2_navigation_plan_check.py
  git commit -m "feat(nav): add v2 single-uav plan and coordinate contract"
  ```

---

### Task 3: Add opt-in executor settle and disarm verification

**Files:**
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py`
- Create: `tests/mission_executor_terminal_contract_check.py`
- Modify: `tests/stage8_landing_disarm_check.py`

**Interfaces:**
- `verify_planned_navigation` optional fields: `settle_duration_s`, `maximum_speed_mps`.
- AUTO.LAND `call_service` optional fields: `require_disarmed`, `disarm_timeout_s`.
- New evidence events: `terminal_settle_confirmed`, `disarm_confirmed`; old actions/events remain unchanged.

- [ ] **Step 1: Write RED settle state-machine tests.**

  Stream real fake-cache odometry/planner messages and cover immediate old behavior, continuous stable success, speed reset, position reset, intermittent non-accumulation, timeout, and planner command accumulation while settling. The tests use short real monotonic windows (`0.05–0.20 s`) and fail against the current immediate-return implementation.

- [ ] **Step 2: Write RED opt-in disarm tests.**

  Extend the existing landing fake to cover low altitude while armed (not complete), low altitude followed by disarm (complete plus `disarm_confirmed`), disarm timeout, and unchanged old-plan low-altitude behavior.

- [ ] **Step 3: Run executor tests and observe RED.**

  ```powershell
  python tests/mission_executor_terminal_contract_check.py --executor-module future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
  python tests/stage8_landing_disarm_check.py --executor-module future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
  ```

  Expected: new settle/disarm assertions fail for missing opt-in contracts; existing legacy assertions remain green.

- [ ] **Step 4: Implement minimal backward-compatible settle logic.**

  Keep point-goal and `course_s` predicates unchanged. When `settle_duration_s` is absent, return immediately as before. When present, require position confirmation and speed limit continuously, reset `settle_started_at=None` on either violation, and continue counting planner cache sequence changes until success/timeout. Validate positive finite values.

- [ ] **Step 5: Implement minimal disarm logic.**

  With `require_disarmed=true`, record the first low-altitude/touchdown observation, then wait at most `disarm_timeout_s` for `armed=false`; never return while still armed. Return landing confirmation plus a separate `disarm_confirmed` verification event. Without the field, preserve current low-altitude-or-low-disarmed behavior.

- [ ] **Step 6: Add single-UAV takeoff stage compatibility.**

  Treat stage `takeoff` equivalently to legacy `multi_takeoff` only for altitude verification and `takeoff_setpoint_published`; do not alter Stage 7/8 action generation.

- [ ] **Step 7: Run focused tests to GREEN.**

  ```powershell
  python tests/mission_executor_terminal_contract_check.py --executor-module future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
  python tests/stage8_landing_disarm_check.py --executor-module future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
  python tests/stage8_course_progress_verify_check.py --executor-module future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py --course-spec config/maps/predicted_narrow_course_v1.json
  ```

  Expected: exit 0, including legacy progress/landing behavior.

- [ ] **Step 8: Review and commit executor contract.**

  ```powershell
  git diff --check
  git add future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py tests/mission_executor_terminal_contract_check.py tests/stage8_landing_disarm_check.py
  git commit -m "feat(executor): add opt-in settle and disarm verification"
  ```

---

### Task 4: Add read-only runtime recorder and provenance-safe report

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_recorder.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_report.py`
- Create: `tests/competition_course_v2_navigation_report_check.py`

**Interfaces:**
- Recorder output: JSONL with `uav1_odom`, `uav2_state_sample`, `planner_command`, and `registered_cloud_roi` records; it publishes/calls no ROS interface.
- Existing `flight_event_recorder.py --crash-listen` supplies authoritative RflySim collision events.
- Report input: plan, mission events/trace, recorder JSONL, flight event JSONL, watchdog logs, spec.
- Report output explicitly labels every metric source as `measured`, `derived`, `simulator_evaluation`, or `unavailable`.

- [ ] **Step 1: Write RED pure-analysis tests.**

  Fixtures must prove: UAV2 any armed/OFFBOARD sample fails; sample count/interval/first/final states are retained; endpoint settle/disarm events are mandatory; synthetic `min_uav_distance=0.85` is ignored; trajectory progress passes static/dynamic regions; oriented wall/static clearances subtract UAV radius; missing crash transport produces `collision_count.value=null` and `source=unavailable`; authoritative crash JSONL yields a measured count; unavailable synchronized pendulum pose produces `dynamic_clearance_m.value=null`; truth provenance fields are explicit.

- [ ] **Step 2: Run report test and observe RED.**

  ```powershell
  python tests/competition_course_v2_navigation_report_check.py --project-root .
  ```

  Expected: FAIL because recorder/report modules do not exist.

- [ ] **Step 3: Implement pure geometry/report analysis.**

  Convert local odometry to world with the canonical inverse. Project trajectory onto Section A for progress history and region passage. Compute signed clearance to spec-derived oriented wall boxes and static obstacle boxes, subtracting `vehicle_envelope.horizontal_diameter/2`. Never synthesize a collision count or dynamic clearance.

- [ ] **Step 4: Implement the read-only ROS recorder.**

  Subscribe to UAV1 MAVROS odom, UAV1 PositionCommand, UAV1 registered cloud, and UAV2 MAVROS state. Sample cached UAV2 state at a configured interval throughout the active process. For registered clouds, record bounded point counts/centroids in spec-derived local static and pendulum sweep ROIs. Write `runtime_decision_source=lidar_driven`; open no publishers and call no services.

- [ ] **Step 5: Run report tests to GREEN.**

  ```powershell
  python tests/competition_course_v2_navigation_report_check.py --project-root .
  ```

  Expected: exit 0 with provenance and unavailable semantics verified.

- [ ] **Step 6: Review and commit evidence tooling.**

  ```powershell
  git diff --check
  git add future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_recorder.py future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_report.py tests/competition_course_v2_navigation_report_check.py
  git commit -m "feat(nav): add v2 runtime evidence reporting"
  ```

---

### Task 5: Add opt-in runner and offline validation entrypoint

**Files:**
- Create: `scripts/run_competition_course_v2_navigation.bat`
- Create: `scripts/wsl/competition_course_v2_navigation.sh`
- Create: `scripts/validate_competition_course_v2_navigation.ps1`
- Create: `tests/competition_course_v2_navigation_entrypoint_check.py`
- Modify: `scripts/README.md`

**Interfaces:**
- Runner flags: `--profile short_smoke|full_section_a`, `--stack-id`, `--manifest`, `--dry-run`, and for live only `--allow-arm --simulation-only`.
- Uses current run-scoped readiness and identity; no fallback to stale `current_run.env` identity.
- Starts UAV1 setpoint bridge/watchdog, read-only V2 recorder, and existing flight event recorder; UAV2 gets no bridge command and is only monitored.

- [ ] **Step 1: Write RED runner contract tests.**

  Execute `--dry-run` and assert exact ordered phases, no arming request, explicit profile, current stack/instance requirements, recorder/report paths, and only UAV1 control components. Assert missing live arm flags fail before WSL launch. Check the WSL script is LF-only and contains no broad kill, lifecycle mutation, EGO parameter override, obstacle truth command, or `min_uav_distance` acceptance.

- [ ] **Step 2: Run entrypoint test and observe RED.**

  ```powershell
  python tests/competition_course_v2_navigation_entrypoint_check.py --project-root .
  ```

  Expected: FAIL because V2 entrypoints do not exist.

- [ ] **Step 3: Implement the Windows fail-closed wrapper.**

  Dry-run prints the sequence and exits without starting WSL. Live execution requires all explicit flags/identity arguments and delegates to the WSL script without changing existing launch/lifecycle files.

- [ ] **Step 4: Implement the WSL runner.**

  Validate current sensor readiness, map ID/SHA, stack ID and simulation instance before any arm path. Start only project-owned child processes with existing `stack_register` at creation; reuse the existing safety cleanup pattern to request UAV1 AUTO.LAND on mission failure, never force-disarm UAV2. Run plan generation, mission executor, recorder/report, and preserve partial artifacts on every failure.

- [ ] **Step 5: Implement the focused validator and run GREEN.**

  ```powershell
  python tests/competition_course_v2_navigation_entrypoint_check.py --project-root .
  powershell -ExecutionPolicy Bypass -File scripts/validate_competition_course_v2_navigation.ps1
  ```

  Expected: exit 0; generated short/full plans and report fixtures validate.

- [ ] **Step 6: Review and commit runner/tooling.**

  ```powershell
  git diff --check
  git add scripts/run_competition_course_v2_navigation.bat scripts/wsl/competition_course_v2_navigation.sh scripts/validate_competition_course_v2_navigation.ps1 tests/competition_course_v2_navigation_entrypoint_check.py scripts/README.md
  git commit -m "feat(nav): add v2 section-a runner and validation"
  ```

---

### Task 6: Gate 2 protected regression and offline handoff

**Files:**
- Modify: `docs/current/competition-roadmap.md`
- Modify only after evidence changes truth: `.agents/AGENT2READ.md`

**Interfaces:**
- Produces: a fresh offline verification record and exact Red-Zone live proposal.

- [ ] **Step 1: Run all focused V2 checks.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/validate_competition_course_v2_navigation.ps1
  powershell -ExecutionPolicy Bypass -File scripts/validate_competition_course_v2.ps1
  ```

- [ ] **Step 2: Run protected Stage 7 and Stage 8 regressions.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/validate_stage7.ps1
  powershell -ExecutionPolicy Bypass -File scripts/validate_stage8.ps1
  ```

  Expected: both exit 0 without modifying old plans/configs.

- [ ] **Step 3: Compare legacy plan artifacts.**

  Regenerate the existing Stage 7 and Stage 8 dry-run plans and assert no new settle/disarm fields appear unless explicitly requested. Confirm the synthetic generic distance event is absent from the V2 report path.

- [ ] **Step 4: Inspect current live state read-only.**

  Use `sim.ps1 status`/`live_stack_inspect.ps1` only. Because the computer reboot left no active stack and ROS master, record Gate 3 as requiring a new authorized V2 stack rather than reusing stale readiness.

- [ ] **Step 5: Record the offline implementation state only after fresh verification.**

  ```powershell
  git diff --check
  git status --short
  ```

  Keep current truth at `implementation/offline ready; live pending authorization`; do not claim navigation PASS. Commit only the resulting authoritative documentation delta, without rewriting earlier implementation commits.

---

### Task 7: Red-Zone live gates and closure evidence

**Files:**
- Create after runs: `docs/evidence/2026-09-01-competition-course-v2-uav1-section-a-navigation.md`
- Modify after evidence: `docs/current/competition-roadmap.md`
- Modify after evidence: `.agents/AGENT2READ.md`

**Interfaces:**
- Consumes: authorized V2 stack, run-scoped readiness, V2 runner, recorder/report.
- Produces: `CLOSED`, `PARTIAL`, or `BLOCKED` with exact run IDs and metric provenance.

- [ ] **Step 1: Present Red-Zone authorization packet and stop.**

  Show exact start/stop/fresh/flight commands, start/fresh DryRun, stack and simulation IDs, inspect output, owned Windows PID and WSL PID/PGID entries with creation grants/fingerprints, stop order, and fail-closed cases. Obtain explicit user authorization before any live mutation/OFFBOARD/arm.

- [ ] **Step 2: Start/inspect the explicit V2 stack and run Gate 3 no-arm.**

  Validate UAV1 MAVROS/odom/Faster-LIO/registered cloud/EGO topics/PositionCommand path and derived V2 goal frame. Confirm sampled UAV2 state is disarmed/non-OFFBOARD. Any stale/unknown identity stops the run.

- [ ] **Step 3: Run one `short_smoke`.**

  Require takeoff, goal/PositionCommand/PX4 movement, terminal settle, AUTO.LAND and disarm. On failure diagnose transform → EGO acceptance → PositionCommand → bridge → MAVROS → PX4 without EGO tuning.

- [ ] **Step 4: Run one `full_section_a` diagnostic.**

  Require one endpoint goal, static/dynamic passage, LiDAR temporal evidence, planner commands, endpoint settle, landing/disarm, continuous UAV2 isolation, no watchdog/geofence/executor error, simulator crash evidence, and derived wall/static clearance.

- [ ] **Step 5: Run 3 consecutive fresh-instance full diagnostics.**

  Keep map/config/planner/Faster-LIO/thresholds unchanged. Any failure resets the counter after RCA. Each stop uses only the authorized owned manifest and fails closed on mismatch.

- [ ] **Step 6: Write truthful closure evidence and final commits.**

  `CLOSED` requires all five flight successes and sufficient collision evidence. Otherwise write `PARTIAL` or `BLOCKED` with the missing layer. Run final focused/Stage 7/8/map validators, inspect the complete diff, request code review, fix Critical/Important findings, and commit docs without pushing.
