# Competition Course V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task by task, with `test-driven-development` for every behavior change and `verification-before-completion` before success claims.

**Goal:** Add one deterministic, opt-in `competition_course_v2` RflySim development map with scored corridor geometry, static and moving obstacles, a configurable task slot, two ArUco landing pads, reproducible deploy/load tooling, live sensor evidence, and preservation of the protected `predicted_narrow_course` baseline.

**Architecture:** A versioned JSON file is the sole geometry/configuration source. Pure Python modules parse and validate it, generate deterministic terrain/evidence artifacts, and calculate dynamic motion. A repository-owned loader creates only receipt-owned RflySim entities, performs a reversible transaction for the fixed external ArUco texture, and registers the moving-obstacle controller with the existing lifecycle at process creation. The existing lifecycle gets one explicit course selector whose default remains `predicted_narrow_course`; no TF, flight, planner, PX4, MAVROS, Faster-LIO, or EGO math changes are permitted.

**Tech Stack:** Python 3.8, JSON, Pillow/OpenCV ArUco, RflySim `VisionCaptureApi`, PowerShell/batch entrypoints, existing manifest lifecycle helpers, ROS1 read-only topic probes, repository validation scripts.

## Global Constraints

- Work only on `feature/competition-map-v2`, based on `f23de934205b6776ef0531d46c26444bf9f7f65e`; do not push.
- Keep `predicted_narrow_course` the default and preserve its source, generation, deployment, loading, and flight behavior.
- Never create a shared UAV TF or change existing frame, localization, mission, planner, setpoint, sensor, PX4, MAVROS, Faster-LIO, EGO, or lifecycle stop semantics.
- Every live process/entity must be owned at creation and cleaned using the standard manifest/receipt path. Never clear numeric ID ranges or scan/kill by name.
- The external ClassID 43 texture transaction must verify the installed-file fingerprint, back up the exact original, replace atomically, and restore in `finally`; failure to restore is fail-closed.
- No full mission on the new course is required. Structural validation, live sensor validation, moving-object proof, and planner smoke are required. The old course regression remains required.

---

### Task 1: Establish the Competition Course V2 source contract

**Files:**
- Create: `config/maps/competition_course_v2.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py`
- Test: `tests/competition_course_v2_geometry_check.py`

**Step 1: Write failing geometry tests**

Cover strict schema parsing, ENU coordinates, three straight sections and two bends, wall tessellation error, unique IDs in `15000..15999`, dual spawn clearance, corridor widths/radii, static obstacle passable clearance, landing-pad spacing, valid dynamic pendulum parameters, valid ArUco IDs/sizes, and resolvable target placeholder metadata. Assert malformed/unknown fields fail closed.

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_geometry_check.py --project-root .
```

Expected: FAIL because the source and parser do not exist.

**Step 2: Add the single-source JSON spec**

Encode the approved layout and classification metadata:

```json
{
  "schema_version": 2,
  "map_id": "competition_course_v2",
  "coordinate_frame": "ENU",
  "base_scene": "SLAMScene",
  "object_id_range": [15000, 15999],
  "spawns": {
    "uav1": [2.0, -0.7, 0.0],
    "uav2": [2.0, 0.7, 0.0]
  }
}
```

Add the complete segments, wall geometry, two static obstacles, deterministic pendulum, mission target slot, two landing pads, and two `DICT_4X4_250` marker definitions. Mark every design value `OFFICIAL`, `PREDICTED`, or `CONFIGURABLE` through an explicit requirements section.

**Step 3: Implement pure geometry and validation**

Expose small deterministic functions:

```python
def load_spec(path): ...
def validate_spec(spec): ...
def build_wall_boxes(spec): ...
def build_entity_manifest(spec): ...
def pendulum_pose(dynamic_spec, elapsed_sec): ...
```

Reject duplicate/out-of-range IDs, corridor blockage, invalid marker/pendulum values, spawn intersections, invalid platform spacing, and unknown schema keys. Calculate arc wall chords using the configured maximum chord error.

**Step 4: Run focused tests and compile**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_geometry_check.py --project-root .
D:\PX4PSP\Python38\python.exe -m py_compile future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_geometry.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add config/maps/competition_course_v2.json future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py tests/competition_course_v2_geometry_check.py
git commit -m "map: define competition course v2 geometry"
```

---

### Task 2: Generate deterministic terrain, marker, and metadata artifacts

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_artifacts.py`
- Create: `scripts/generate_competition_course_v2.bat`
- Create: `tests/competition_course_v2_artifacts_check.py`
- Modify: `config/env_template.bat`

**Step 1: Write failing artifact tests**

Test two clean generations produce byte-identical structured metadata, preview, terrain input, and marker PNGs. Validate object counts/IDs/poses/sizes, marker dictionary/IDs/pixel border, source-spec SHA-256, and no timestamps or host paths in deterministic files.

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_artifacts_check.py --project-root .
```

Expected: FAIL because the generator does not exist.

**Step 2: Implement deterministic generation**

Generate only beneath the existing ignored artifact/log convention, including:

- `entity_manifest.json`
- `validation_report.json`
- `planning_points.json`
- `preview.svg`
- deterministic SLAMScene terrain files compatible with the current deploy path
- one generated PNG per ArUco marker using OpenCV `DICT_4X4_250`

Use canonical JSON (`sort_keys=True`, fixed separators/newline) and fixed raster dimensions. Do not embed generation time in deterministic outputs; keep run metadata separate.

**Step 3: Add the generator entrypoint and environment paths**

The batch file must use the repository Python convention, fail closed on missing Python/spec, accept an explicit output directory, and print the spec/output hashes. Add V2-only environment variables without changing V1 defaults.

**Step 4: Verify determinism**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_artifacts_check.py --project-root .
scripts\generate_competition_course_v2.bat
git diff --check
```

Expected: PASS and identical hashes for consecutive clean generations.

**Step 5: Commit**

```bash
git add config/env_template.bat scripts/generate_competition_course_v2.bat future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_artifacts.py tests/competition_course_v2_artifacts_check.py
git commit -m "map: generate deterministic competition course artifacts"
```

---

### Task 3: Add receipt-owned scene loading and reversible ArUco deployment

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_ue_loader.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_motion.py`
- Create: `scripts/deploy_competition_course_v2_terrain.bat`
- Create: `scripts/load_competition_course_v2.bat`
- Create: `tests/competition_course_v2_loader_check.py`
- Create: `tests/competition_course_v2_motion_check.py`

**Step 1: Write failing loader/motion tests**

Use fakes for filesystem, SDK, clock, and lifecycle registration. Cover:

- only receipt-recorded entity IDs are destroyed;
- SDK creation preserves spec pose/scale and collision-enabling command;
- wrong installed ArUco fingerprint fails before write;
- atomic backup/install/checksum/restore executes on success and all raised exceptions;
- restoration checksum mismatch makes the loader fail;
- two marker textures are loaded sequentially without claiming persistence until live proof;
- pendulum positions match amplitude/period/phase at quarter-period samples;
- controller registers PID/start-time/command fingerprint at creation and emits pose evidence;
- unowned controller or stale receipt fails closed.

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_loader_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_motion_check.py --project-root .
```

Expected: FAIL.

**Step 2: Implement the loader transaction**

Load the generated entity manifest, create walls/static objects/target/platforms via the stable SLAMScene primitive mechanism, and write a run receipt containing exact IDs and creation requests. Cleanup reads that receipt; it never derives a range.

Wrap ClassID 43 texture use:

```python
with installed_asset_transaction(source_png, installed_png, expected_sha256):
    api.sendUE4PosScale(...)
```

Use an adjacent temporary file plus `os.replace`, and restore the byte-exact backup in `finally`. The source/deployed/restore hashes enter run evidence.

**Step 3: Implement the deterministic motion controller**

At 20 Hz calculate:

```python
angle = amplitude_rad * sin(2.0 * pi * elapsed / period + phase)
y = pivot_y + length * sin(angle)
z = pivot_z - length * cos(angle)
```

Send explicit poses for entity `15120`, preserve collision geometry, and append bounded timestamped pose samples. Exit on the repository-owned stop signal. Registration occurs at creation through the existing stack registration helper.

**Step 4: Add deploy/load entrypoints**

Deployment must verify generated hashes before copying terrain files and use explicit source/destination arguments. Loading must require an active matching stack ID/manifest, start the controller through the owned launcher path, and emit a load receipt. Dry-run prints every target and performs no writes.

**Step 5: Run focused validation**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_loader_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_motion_check.py --project-root .
D:\PX4PSP\Python38\python.exe -m py_compile future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_ue_loader.py future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_motion.py
scripts\deploy_competition_course_v2_terrain.bat --dry-run
scripts\load_competition_course_v2.bat --dry-run
```

Expected: PASS; no external files or processes change during dry-run.

**Step 6: Commit**

```bash
git add scripts/deploy_competition_course_v2_terrain.bat scripts/load_competition_course_v2.bat future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_ue_loader.py future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_motion.py tests/competition_course_v2_loader_check.py tests/competition_course_v2_motion_check.py
git commit -m "map: load owned competition course entities"
```

---

### Task 4: Add explicit opt-in startup and sensor verification paths

**Files:**
- Create: `scripts/start_competition_course_v2_two_uav.bat`
- Modify: `scripts/live_stack_start.ps1`
- Modify: `scripts/run_live_fastlio_dual.bat`
- Modify: `scripts/wsl/stage7_live_fastlio_dual.sh`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_live_probe.py`
- Create: `tests/competition_course_v2_entrypoint_check.py`
- Create: `tests/competition_course_v2_live_probe_check.py`

**Step 1: Write failing contract tests**

Assert:

- `live_stack_start.ps1` accepts exactly `predicted_narrow_course` and `competition_course_v2`;
- omitted `-Course` still selects the original predicted-course launcher byte-for-byte in behavior;
- V2 selects only the new start wrapper;
- unsupported values fail before process creation;
- Stage 7 defaults to `lidar_only`, while explicit `full` passes through to the existing sensor bridge;
- the live probe is read-only and summarizes LiDAR/RGB/IMU/Faster-LIO/EGO without ROS publishers, services, parameters, arming, or mission commands;
- no protected TF/mission/launch files are modified.

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_entrypoint_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_live_probe_check.py --project-root .
```

Expected: FAIL.

**Step 2: Add the default-preserving course selector**

Add:

```powershell
[ValidateSet('predicted_narrow_course','competition_course_v2')]
[string]$Course = 'predicted_narrow_course'
```

Map it to an explicit launcher table. Preserve stage ordering, readiness, ownership, manifest schema, and stop behavior. The V2 wrapper reuses the existing two-UAV start chain with only spec-generated spawn/scene/load selection.

**Step 3: Add explicit full-sensor diagnostics**

Thread a single validated sensor-mode argument into Stage 7. Default stays `lidar_only`; `full` is permitted only when explicitly requested for no-arm RGB evidence. Do not change live flight entrypoints or protected sensor configuration.

**Step 4: Implement the read-only live probe**

Sample both UAVs for a bounded duration and report:

- LiDAR rate, point counts, finite bounds, and expected obstacle-region occupancy;
- actual discovered RGB topics, frame/rate/size, and saved frames;
- IMU rate/age;
- Faster-LIO odometry/cloud rate/age and finite values;
- EGO node/topic/odom/cloud/basic-output status;
- motion-controller pose samples and approximate amplitude/period;
- run/stack/spec/artifact hashes.

Write Markdown and JSON under ignored run artifacts. Do not infer ArUco visibility from topic activity: save the frame and record image-region contrast/metadata for later visual confirmation.

**Step 5: Run offline tests and lifecycle validation**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_entrypoint_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_live_probe_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
D:\PX4PSP\Python38\python.exe -m py_compile future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_live_probe.py
```

Expected: PASS.

**Step 6: Commit**

```bash
git add scripts/start_competition_course_v2_two_uav.bat scripts/live_stack_start.ps1 scripts/run_live_fastlio_dual.bat scripts/wsl/stage7_live_fastlio_dual.sh future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_live_probe.py tests/competition_course_v2_entrypoint_check.py tests/competition_course_v2_live_probe_check.py
git commit -m "map: add opt-in competition course live path"
```

---

### Task 5: Integrate structural validation and current documentation

**Files:**
- Create: `scripts/validate_competition_course_v2.ps1`
- Create: `docs/current/competition-map-v2.md`
- Modify: `scripts/README.md`
- Modify: `tests/docs_link_check.py` only if the current link-check inventory requires it
- Modify: `scripts/validate_repository.ps1` only if the repository convention requires registering the new focused validator

**Step 1: Write the validator as an orchestration layer**

It runs the geometry, artifact determinism, loader, motion, entrypoint, and live-probe offline checks; verifies generated hashes; performs deploy/load dry-runs; and clearly labels structural validation separately from live sensor, planner smoke, and full mission.

**Step 2: Document current truth**

Document status `DEVELOPMENT MAP`, exact layout and classifications, generation/deploy/load commands, opt-in startup, receipt cleanup, ArUco transaction/limitations, task placeholder, no standard QR requirement, and the fact that full new-map mission is not an acceptance gate. Keep live fields `PENDING LIVE VALIDATION` until evidence exists.

**Step 3: Update script inventory and links**

Register only the new stable entrypoints. Do not change infrastructure, TF, or old-map current-truth conclusions.

**Step 4: Run offline acceptance**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_competition_course_v2.ps1
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
git diff --check
git status --short
```

Expected: all exit 0; generated/log artifacts ignored; tracked diff limited to the task.

**Step 5: Commit**

```bash
git add scripts/validate_competition_course_v2.ps1 scripts/README.md docs/current/competition-map-v2.md tests/docs_link_check.py scripts/validate_repository.ps1
git commit -m "test: validate competition course generation"
```

---

### Task 6: Execute live map and sensor acceptance

**Files:**
- Create: run-scoped ignored artifacts under the repository convention
- Modify: `docs/current/competition-map-v2.md`
- Create: `docs/evidence/2026-08-25-competition-course-v2-live-validation.md`

**Step 1: Prove lifecycle preconditions before mutation**

Run doctor/status, locate the exact manifest if any, and execute standard stop DryRun if cleanup is needed. Record owned PID/PGID/start-time/fingerprint, stop order, and fail-closed conditions before requesting/using live execution authority. Abort on unknown processes, ownership mismatch, port conflict, or cleanup failure.

**Step 2: Generate and deploy deterministically**

Generate twice into separate clean directories and compare hashes. Run deploy dry-run, then deploy through the approved reversible path. Verify terrain destination hashes. Do not leave the ClassID 43 texture modified outside the loader transaction.

**Step 3: Start a clean V2 no-arm stack**

Start with explicit `-Course competition_course_v2`, wait for the existing READY result, inspect the matching manifest, load receipt, entity IDs, and controller ownership. Validate both spawn positions without arming.

**Step 4: Collect full-sensor evidence**

Run Stage 7 explicitly in `full` no-arm diagnostic mode and the live probe. Confirm both UAVs have valid LiDAR/RGB/IMU; visually inspect saved RGB frames for each ArUco marker; inspect multiple LiDAR samples for walls/static/moving object; verify controller `pose(t0) != pose(t1) != pose(t2)` and approximate configured amplitude/period. Confirm both Faster-LIO pipelines produce finite odometry/clouds.

If both distinct marker IDs cannot be shown simultaneously after sequential ClassID 43 creation, record the exact asset/API limitation and stop acceptance rather than claiming success.

**Step 5: Run EGO planner smoke**

Start the existing EGO chain with no mission changes. Use only an existing safe smoke input if the repository already provides one. Confirm both planners receive odometry/cloud and produce basic planning output or, if no safe existing input exists, report the strongest non-command readiness evidence without inventing a new mission.

**Step 6: Standard stop and clean proof**

Use manifest stop DryRun then Execute, and verify no owned orphan, no unknown project process, relevant ports free, controller exited, loaded receipt entities removed, and installed ArUco texture restored to the original SHA-256.

**Step 7: Update evidence and current truth**

Record stack/run IDs, reports/screenshots, hashes, topic names/rates, object pose samples, and acceptance results. Upgrade only proven fields from pending to live-verified.

---

### Task 7: Regress the protected old map and finalize

**Files:**
- Modify: `docs/current/competition-map-v2.md`
- Modify: `docs/evidence/2026-08-25-competition-course-v2-live-validation.md`

**Step 1: Verify the old offline pipeline**

```powershell
scripts\generate_predicted_narrow_course.bat
scripts\deploy_predicted_course_terrain.bat --dry-run
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: PASS with old artifacts/spec unchanged.

**Step 2: Run the old protected live regression**

From a proven clean state, omit `-Course` to prove the default still chooses `predicted_narrow_course`. Execute the accepted dual-UAV Stage 7/8 route with current run-scoped authorization, then confirm collision count 0, OFFBOARD loss 0, timeout 0, landing/disarm, standard clean stop, and no V2 controller/entity/asset residue.

**Step 3: Run final repository verification**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_competition_course_v2.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
git diff --check
git status --short --branch
```

Expected: all PASS and only intended tracked documentation changes remain.

**Step 4: Request code review and fix only verified issues**

Use `requesting-code-review`; validate any feedback before changing code. Re-run affected focused tests and the full offline acceptance after fixes.

**Step 5: Commit closure**

```bash
git add docs/current/competition-map-v2.md docs/evidence/2026-08-25-competition-course-v2-live-validation.md
git commit -m "docs: validate competition course v2 live"
```

Do not push. Report `COMPETITION MAP V2 READY` only if every mandatory source, generation, validation, deployment, live scene, dual sensor, dynamic obstacle, dual ArUco visibility, Faster-LIO, EGO smoke, old-map regression, cleanup, and Git criterion has fresh evidence. Otherwise report `COMPETITION MAP V2 BLOCKED` with the exact mandatory blocker and preserved artifacts.
