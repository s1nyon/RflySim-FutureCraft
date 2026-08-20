# Coordinate-Verifiable Basic Course Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate, transactionally load, machine-verify, and complete one dual-UAV full flight on a new obstacle-free 1.5 m Z-shaped course without changing the protected PBL course by default.

**Architecture:** A new pure geometry package owns the ENU source, calibrated primitive transform, resolved walls, world/local routes, geofence, and deterministic artifacts. A separate transaction/verifier package loads only receipt-owned window-0 IDs and proves the measured scene; opt-in launcher parameters inject the new course and geofence into the existing protected flight chain while preserving all old defaults.

**Tech Stack:** Python 3.8, JSON, SHA-256, ROS1 Noetic, RflySim `UE4CtrlAPI`, Bash, Batch, PowerShell, existing Stage 7/8 validators.

## Global Constraints

- Keep `config/maps/predicted_narrow_course_v1.json` and its default PBL invocation byte-for-byte unchanged.
- Use course-world ENU metres as the design truth and convert to vendor NED only at the UE boundary.
- Use `SLAMScene`, existing verified flat-terrain bytes, RflySim window `0`, and object IDs `14000..14999`.
- Use one exact live-calibrated static primitive profile; do not assume native dimensions or claim metadata ClassID verification.
- Do not use `sendUE4PosScale2Ground`, range-wide clear, process-name killing, `wsl --shutdown`, implicit arming, or force retry.
- Do not add QR, color/thermal targets, cones, dynamic obstacles, ArUco precision landing, perception, or new coordination behavior.
- Preserve current takeoff altitude, navigation altitude, goal tolerance, watchdog, OFFBOARD, and AUTO.LAND semantics.
- One successful run is `FIRST LIVE PASS`, not a protected baseline.
- Live start, course removal/load, simulation arming/OFFBOARD, and stop execute require explicit operator authorization.

## File Structure and Parallelization

- Task 1 is the shared contract and must land first.
- Tasks 2 and 3 consume Task 1 and may run in parallel without editing the same files.
- Task 4 consumes Tasks 2 and 3 and is the only task allowed to modify the shared flight runner/launcher boundary.
- Task 5 integrates and performs offline/no-arm/live acceptance.

---

### Task 1: ENU Geometry, Calibrated Bounds, and Basic Course Schema

**Files:**
- Create: `config/maps/competition_basic_course_v1.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_geometry.py`
- Create: `tests/competition_basic_geometry_check.py`

**Interfaces:**
- Produces: `Vec3`, `LocalBounds`, `PrimitiveProfile`, `Pose`, `BoxObject`, `RouteSet`, `CourseModel` dataclasses.
- Produces: `load_course(path: Path) -> CourseModel`.
- Produces: `world_corners(local_bounds, actor_position, rpy, scale) -> tuple[Vec3, ...]` and `world_aabb(corners) -> tuple[Vec3, Vec3]`.
- Produces: `oriented_footprint(box: BoxObject) -> tuple[tuple[float, float], ...]`.
- Produces: `enu_to_ned(position: Vec3) -> Vec3`, `yaw_enu_to_ned(yaw: float) -> float`, and `wrap_angle(error: float) -> float`.
- Produces: `course_report(model: CourseModel) -> dict` containing source hash, measured design width, turn radius, route round-trip errors, geofence, IDs, and expected wall bounds.

- [ ] **Step 1: Write failing transformed-bounds and angle tests**

```python
def check_rotated_bounds(module):
    local = module.LocalBounds(
        origin=module.Vec3(0.1, -0.2, 0.5),
        half_extent=module.Vec3(0.5, 1.0, 1.5),
    )
    corners = module.world_corners(
        local, module.Vec3(10.0, 20.0, 1.5),
        module.Vec3(0.0, 0.0, math.pi / 2.0),
        module.Vec3(2.0, 1.0, 1.0),
    )
    minimum, maximum = module.world_aabb(corners)
    assert len(corners) == 8
    assert maximum.z - minimum.z == pytest.approx(3.0)
    assert module.wrap_angle(math.pi * 2.0 - 0.1) == pytest.approx(-0.1)
```

- [ ] **Step 2: Write failing schema, topology, route-frame, and clearance tests**

```python
model = module.load_course(spec)
assert model.course_name == "competition_basic_course_v1"
assert model.owned_id_range == (14000, 14999)
assert len(model.centreline) == 5
assert [item.kind for item in model.centreline] == ["line", "arc", "line", "arc", "line"]
assert model.clear_width_m == pytest.approx(1.5)
assert model.turn_radius_m == pytest.approx(1.65)
assert set(model.routes.local_by_uav) == {"uav1", "uav2"}
assert max(model.routes.round_trip_error_m.values()) <= 1e-9
assert min(module.measured_design_clearances(model)) >= 1.5 - 1e-6
```

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_basic_geometry_check.py --module future_aircraft_ws\src\multi_uav_mission\scripts\competition_basic_geometry.py --spec config\maps\competition_basic_course_v1.json
```

Expected: FAIL because the module and source spec do not exist.

- [ ] **Step 4: Implement the source JSON and pure geometry model**

The JSON must set `schema_version: 1`, `course_name`, `SLAMScene`, ENU metres,
ID range, primitive metadata profile, `clear_width_m: 1.5`,
`turn_radius_m: 1.65`, wall height `2.5`, two takeoff poses, two nominal landing
goals, five centreline elements, vehicle envelope, geofence margin, and exact
offline/live tolerances. The loader must reject unknown keys that affect
geometry, non-finite numbers, discontinuous segments, duplicate IDs, routes
outside the inflated corridor, and mismatched world/local round trips.

- [ ] **Step 5: Implement eight-corner bounds and oriented-polygon clearance**

```python
def world_corners(local_bounds, actor_position, rpy, scale):
    points = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                local = local_bounds.origin + local_bounds.half_extent * Vec3(sx, sy, sz)
                points.append(actor_position + rotate_rpy(local * scale, rpy))
    return tuple(points)
```

Dimension acceptance must compare scaled local oriented dimensions. World AABB
is diagnostic only; channel clearance uses oriented XY footprints.

- [ ] **Step 6: Run the focused test and verify GREEN**

Run the Step 3 command. Expected: `competition basic geometry: PASS`.

- [ ] **Step 7: Commit Task 1**

```powershell
git add config/maps/competition_basic_course_v1.json future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_geometry.py tests/competition_basic_geometry_check.py
git commit -m "feat: define coordinate-verifiable basic course"
```

---

### Task 2: Deterministic Artifacts, Routes, and Focused Validator

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_artifacts.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_flight_plan.py`
- Create: `tests/competition_basic_artifacts_check.py`
- Create: `tests/competition_basic_flight_plan_check.py`
- Create: `scripts/generate_competition_basic_course.bat`
- Create: `scripts/validate_competition_basic_course.ps1`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: Task 1 `CourseModel`, `load_course`, and `course_report`.
- Produces: `generate_artifacts(spec_path: Path, output_dir: Path) -> dict`.
- Produces: files `resolved_scene.json`, `navigation_routes.json`, `geofence.json`, `executor_plan.json`, `validation_report.json`, `course_preview.svg`, and `artifact_manifest.json`.
- Produces: `build_executor_plan(config: dict, model: CourseModel) -> dict` with existing `publish_planner_goal`/`verify_planned_navigation` pairs and final `set_mode: AUTO.LAND` actions.

- [ ] **Step 1: Write failing deterministic artifact tests**

```python
first = artifact_module.generate_artifacts(spec, output_a)
second = artifact_module.generate_artifacts(spec, output_b)
assert first == second
assert sorted(first["artifacts"]) == [
    "artifact_manifest.json", "course_preview.svg", "executor_plan.json",
    "geofence.json", "navigation_routes.json", "resolved_scene.json",
    "validation_report.json",
]
assert not (output_a / "SLAMScene.png").exists()
assert not (output_a / "planning_points.json").exists()
```

- [ ] **Step 2: Write failing executor-plan contract tests**

```python
plan = plan_module.build_executor_plan(config, model)
goals = [action for action in plan["actions"] if action["action"] == "publish_planner_goal"]
assert {goal["uav"] for goal in goals} == {"uav1", "uav2"}
assert plan["geofence"] == model.geofence.as_dict()
assert plan["course"]["spec_sha256"] == model.spec_sha256
assert plan_module.plan_world_local_round_trip_errors(plan, model) == {"uav1": 0.0, "uav2": 0.0}
assert [action["uav"] for action in plan["actions"] if action["action"] == "set_mode"] == ["uav1", "uav2"]
```

- [ ] **Step 3: Run focused tests and verify RED**

Run both new Python tests directly with `D:\PX4PSP\Python38\python.exe`.
Expected: FAIL because artifact and plan modules do not exist.

- [ ] **Step 4: Implement deterministic artifacts without terrain duplication**

Reuse pure SVG/JSON/hash helpers but do not write `SLAMScene.png/.txt`. Put the
expected existing terrain hashes in `resolved_scene.json` and verify them at
deployment. `navigation_routes.json` must store course-world ENU and per-UAV
spawn-relative local ENU side by side.

- [ ] **Step 5: Implement the protected executor adapter**

Match the existing `mission_executor.py` action schema exactly. Preserve both-
takeoff, UAV1-nav/UAV2-wait, UAV1-exit-hold, UAV2-nav, and dual AUTO.LAND order.
Do not import or modify `stage7_flight_plan.py` behavior for the PBL default.

- [ ] **Step 6: Add generation and aggregate validation wrappers**

`generate_competition_basic_course.bat --dry-run` prints source/output paths
and performs no writes. Execute mode writes only the generated course
directory. `validate_competition_basic_course.ps1` invokes Tasks 1/2 tests and
runs two temporary generations with byte-equal hashes.

- [ ] **Step 7: Run focused validator and verify GREEN**

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_competition_basic_course.ps1
```

Expected: `[PASS] competition basic course offline validation PASS`.

- [ ] **Step 8: Commit Task 2**

```powershell
git add future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_artifacts.py future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_flight_plan.py future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt tests/competition_basic_artifacts_check.py tests/competition_basic_flight_plan_check.py scripts/generate_competition_basic_course.bat scripts/validate_competition_basic_course.ps1
git commit -m "feat: generate basic course flight artifacts"
```

---

### Task 3: Receipt-Owned UE Transaction and Metadata Verification

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_verifier.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_ue_loader.py`
- Create: `tests/competition_basic_verifier_check.py`
- Create: `tests/competition_basic_ue_loader_check.py`
- Create: `scripts/load_competition_basic_course.bat`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`
- Modify: `scripts/validate_competition_basic_course.ps1`

**Interfaces:**
- Consumes: Task 1 `CourseModel`, bounds functions, oriented footprints, ENU/NED conversion.
- Produces: `VerificationTolerance`, `MeasuredObject`, `ObjectVerification`, and `SceneVerification` dataclasses.
- Produces: `verify_object(expected: BoxObject, samples: Sequence[MetadataSample], tolerance: VerificationTolerance) -> ObjectVerification`.
- Produces: `verify_scene(model: CourseModel, samples_by_id: Mapping[int, Sequence[MetadataSample]]) -> SceneVerification`.
- Produces: `build_commands(model: CourseModel) -> tuple[UECommand, ...]` and `execute_transaction(client, model, previous_receipt, output_path) -> dict`.

- [ ] **Step 1: Write failing verifier tests**

```python
result = module.verify_object(expected_wall, three_fresh_samples, tolerance)
assert result.passed
assert result.position_error_m <= 0.02
assert max(result.oriented_dimension_error_m) <= 0.02
assert result.wrapped_yaw_error_deg <= 1.0
assert abs(result.support_gap_m) <= 0.02

with pytest.raises(module.SceneVerificationError, match="minimum measured clear width"):
    module.verify_scene(model, samples_that_narrow_corridor)
```

- [ ] **Step 2: Write failing ownership, rollback, and window tests**

```python
with pytest.raises(ValueError, match="window 0"):
    module.validate_request(model, window_id=-1)
with pytest.raises(module.OwnershipError, match="receipt"):
    module.plan_removal(model, previous_receipt=None, observed_existing_ids={14001})
receipt = module.execute_transaction(fake_client_failing_on_second_create, model, clean_receipt, output)
assert receipt["state"] == "ROLLBACK_VERIFIED"
assert fake_client_failing_on_second_create.destroyed_ids == [14000]
```

- [ ] **Step 3: Run focused tests and verify RED**

Run the two new test files. Expected: FAIL because loader/verifier modules do
not exist.

- [ ] **Step 4: Implement metadata conversion and scene verification**

Adapt `scripts/calibration/object_metadata.py` sampling without copying its old
ground-offset math. Require three finite, stable, fresh samples. Compute eight
world corners, local oriented dimensions, wrapped yaw, design-plane support
gap, oriented wall polygons, and minimum polygon-to-polygon corridor width.

- [ ] **Step 5: Implement receipt-owned transaction state machine**

States are `DRY_RUN`, `REMOVE_VERIFIED`, `CREATING`, `LOADED_VERIFIED`,
`ROLLBACK_VERIFIED`, and `ROLLBACK_INCOMPLETE`. Previous deletion is allowed
only for exact IDs and hashes in a successful prior course receipt. Each
acknowledged current create is appended before the next command. Any failure
rolls back only that list and verifies absence before returning nonzero.

- [ ] **Step 6: Implement CLI and bounded batch wrapper**

DryRun is the default. Execute requires `--execute --window-id 0 --receipt-out`
and a matching validation/artifact manifest. The batch wrapper must never add
arming or process-control behavior.

- [ ] **Step 7: Run focused validator and Stage 8**

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_competition_basic_course.ps1
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: both PASS; old PBL DryRun output and tests remain valid.

- [ ] **Step 8: Commit Task 3**

```powershell
git add future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_verifier.py future_aircraft_ws/src/multi_uav_mission/scripts/competition_basic_ue_loader.py future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt tests/competition_basic_verifier_check.py tests/competition_basic_ue_loader_check.py scripts/load_competition_basic_course.bat scripts/validate_competition_basic_course.ps1
git commit -m "feat: verify basic course UE transactions"
```

---

### Task 4: Opt-In Live Stack and Flight Runner Integration

**Files:**
- Create: `scripts/start_competition_basic_course_two_uav.bat`
- Create: `scripts/run_live_competition_basic_course_flight.bat`
- Create: `tests/competition_basic_launch_check.py`
- Create: `tests/competition_basic_runner_check.py`
- Modify: `scripts/live_stack_start.ps1`
- Modify: `scripts/wsl/stage7_live_slam_ego_swarm_flight.sh`
- Modify: `scripts/validate_competition_basic_course.ps1`

**Interfaces:**
- Consumes: Task 2 `executor_plan.json`, `geofence.json`, hashes; Task 3 `LOADED_VERIFIED` receipt.
- Produces: `live_stack_start.ps1 -Course predicted|competition-basic`, default `predicted`.
- Produces: flight-runner options `--course-spec`, `--executor-plan`, `--geofence`, and `--course-receipt`, whose defaults preserve the current PBL invocation.
- Produces: provenance rejection unless stack ID, simulation instance, source hash, plan hash, geofence hash, and receipt agree.

- [ ] **Step 1: Write failing default-equivalence and opt-in tests**

```python
predicted = run_dry("scripts/live_stack_start.ps1")
explicit = run_dry("scripts/live_stack_start.ps1", "-Course", "predicted")
assert normalize(predicted.stdout) == normalize(explicit.stdout)

basic = run_dry("scripts/live_stack_start.ps1", "-Course", "competition-basic")
assert "start_competition_basic_course_two_uav.bat" in basic.stdout
assert "predicted_narrow_course_v1.json" not in basic.stdout
```

- [ ] **Step 2: Write failing runner injection tests**

```python
text = runner.read_text()
assert '--course-spec' in text
assert '--executor-plan' in text
assert '--geofence' in text
assert '--course-receipt' in text
assert 'require_matching_course_provenance' in text
assert '--min-x -1 --max-x 17 --min-y -2 --max-y 7' not in selected_basic_path(text)
```

- [ ] **Step 3: Run focused tests and verify RED**

Run the two new test files. Expected: FAIL because opt-in wrappers/options do
not exist.

- [ ] **Step 4: Implement the opt-in start selector with unchanged default**

The selector only chooses generation/load/start wrapper and `COURSE_READY`
receipt expectations. Keep lifecycle creation-time ownership, manifest schema,
health gates, and stop behavior untouched. Unknown course values fail before
mutation.

- [ ] **Step 5: Parameterize runner provenance and watchdog geofence**

Resolve all four paths before creating the run directory. Read bounds from the
generated geofence, pass them to setpoint bridge, watchdog, recorder, and
executor, and reject any mismatch before arming. Preserve current values when
the new options are omitted.

- [ ] **Step 6: Add basic-course wrapper and DryRun output**

The wrapper supplies exact generated paths and requires the current stack/run
context. It forwards `--allow-arm --simulation-only` only when explicitly
present; DryRun never calls live tools.

- [ ] **Step 7: Run new validator, lifecycle offline validator, and Stage 8**

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_competition_basic_course.ps1
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: all PASS, including default predicted-course equivalence.

- [ ] **Step 8: Commit Task 4**

```powershell
git add scripts/start_competition_basic_course_two_uav.bat scripts/run_live_competition_basic_course_flight.bat scripts/live_stack_start.ps1 scripts/wsl/stage7_live_slam_ego_swarm_flight.sh scripts/validate_competition_basic_course.ps1 tests/competition_basic_launch_check.py tests/competition_basic_runner_check.py
git commit -m "feat: add opt-in basic course live path"
```

---

### Task 5: Integration Review and FIRST LIVE PASS

**Files:**
- Modify: `docs/current/competition-roadmap.md`
- Create after success: `docs/evidence/2026-08-20-competition-basic-course-first-live-pass.md`

**Interfaces:**
- Consumes: Tasks 1–4 complete commits and artifacts.
- Produces: offline validation evidence, `LOADED_VERIFIED` receipt, run-scoped flight artifacts, and truthful current-state documentation.

- [ ] **Step 1: Request independent code and spec compliance review**

Review must check old PBL byte/default preservation, source-to-local coordinate
round trips, receipt-only deletion, rollback verification, no hidden arming,
and exact live authorization points. Fix all high-severity findings before live.

- [ ] **Step 2: Run final offline gates**

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_competition_basic_course.ps1
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
powershell.exe -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
cmd.exe /d /c scripts\generate_competition_basic_course.bat --dry-run
cmd.exe /d /c scripts\load_competition_basic_course.bat --dry-run
```

Expected: all exit 0; DryRuns list only IDs `14000..14999`, window `0`, and no
arming/process-stop operation.

- [ ] **Step 3: Inspect current live state and present authorization evidence**

Run `./sim.ps1 status` and the start DryRun. Present stale/unknown ownership,
target stack action, course transaction IDs, stop plan, and fail-closed
conditions. Do not mutate until the operator authorizes start/load.

- [ ] **Step 4: Start a fresh stack and perform no-arm verification**

After explicit authorization, start with `-Course competition-basic -Execute`,
generate/load the transaction, and require a `LOADED_VERIFIED` receipt with the
current stack/simulation/source hashes. On failure, stop and preserve evidence.

- [ ] **Step 5: Establish current-run flight readiness**

Run dual Faster-LIO, current-run sensor readiness, dual EGO, and topic probe.
Require identity/schema/freshness/isolation/stationary stability and all five
topology gates PASS within the current readiness window.

- [ ] **Step 6: Obtain explicit simulation arming authorization and fly once**

```bat
scripts\run_live_competition_basic_course_flight.bat --allow-arm --simulation-only
```

No automatic retry. Any collision, route rejection, watchdog event, OFFBOARD
loss, timeout, or provenance mismatch ends the attempt and returns to evidence-
guided diagnosis.

- [ ] **Step 7: Verify FIRST LIVE PASS artifacts**

Require both UAVs OFFBOARD/arm/takeoff, every generated goal confirmation,
separate exit holds, both AUTO.LAND/disarm, `success=true`, zero unexpected
OFFBOARD loss/timeouts, and recorded wall clearance above the inflated vehicle
envelope. All artifacts must match the load receipt's stack, instance, and hash.

- [ ] **Step 8: Document evidence and remaining repeatability risk**

Update the roadmap to `FIRST LIVE PASS`, not `DONE` or protected baseline.
Record commands, commits, hashes, receipt, readiness, score, rollback/stop
outcome, and the deferred three-fresh-run promotion requirement.

- [ ] **Step 9: Commit Task 5**

```powershell
git add docs/current/competition-roadmap.md docs/evidence/2026-08-20-competition-basic-course-first-live-pass.md
git commit -m "docs: record basic course first live pass"
```
