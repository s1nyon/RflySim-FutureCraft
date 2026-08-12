# Coordinate-Verified Course Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a coordinate-trustworthy foundation consisting of correct UE world-bound mathematics, a seven-asset self-verifying showcase, and a balanced Z-shaped L0 course generated at 1.8 m and 1.5 m clear widths.

**Architecture:** Pure geometry modules calculate transformed world bounds, support-face alignment, Z-course geometry, and offline validation. Live adapters remain thin: they issue bounded window-0 commands, capture official metadata, verify the measured scene against the resolved scene, and roll back only transaction-owned IDs on failure. The new course is introduced beside the protected `predicted_narrow_course_v1`; replacement of the default live course occurs only after the new L0 live gate passes.

**Tech Stack:** Python 3.8, JSON, deterministic SVG/JSON artifacts, official `UE4CtrlAPI`, PowerShell validators, existing manifest lifecycle, Git worktrees.

## Global Constraints

- Use ENU metres as the only design truth; convert to NED only at the UE API boundary.
- Do not modify installed RflySim, CopterSim, Firmware, `28com_sim`, or UE assets.
- Keep `SLAMScene`; do not change the map during dynamic loading.
- Use only official RflySim models and documented official image mechanisms.
- Never call `sendUE4PosScale2Ground` for coordinate-verified entities.
- Restrict live scene mutation to RflySim window `0` and declared project-owned IDs.
- ClassIDs `500`, `750`, and `1000` are excluded from generation and loading.
- Hard tolerances are xy `0.02 m`, support gap `0.02 m`, dimensions `0.02 m` per axis, and yaw `1 degree`.
- Require at least three fresh, stable metadata samples for every live static entity.
- No OFFBOARD, arming, mission execution, global process kill, WSL shutdown, or automatic forced retry.
- Do not claim `SENSOR_VERIFIED` or `MISSION_READY` in this foundation plan.
- Preserve the current predicted-course implementation until the new L0 course is live-verified.

---

### Task 1: Correct World-Bound and Support-Alignment Mathematics

**Files:**
- Create: `scripts/calibration/ue_world_geometry.py`
- Modify: `scripts/calibration/object_metadata.py`
- Modify: `tests/asset_calibration_metadata_check.py`
- Create: `tests/ue_world_geometry_check.py`
- Modify: `scripts/validate_asset_calibration.ps1`

**Interfaces:**
- Consumes: attribute-compatible metadata samples and `asset_catalog.Vec3`; `ue_world_geometry.py` must not import `object_metadata.py`, avoiding a module cycle.
- Produces: `WorldBounds(minimum: Vec3, maximum: Vec3, centre: Vec3, dimensions: Vec3)`, `world_bounds_from_sample(sample) -> WorldBounds`, `support_face_z(bounds, face) -> float`, and `aligned_actor_z(sample, target_support_z, child_face="bottom") -> float`.
- Later tasks rely on these functions without duplicating coordinate conversion or box-origin arithmetic.

- [ ] **Step 1: Write failing transformed-bound tests**

Create `tests/ue_world_geometry_check.py` with exact live-derived fixtures. Include:

```python
pillar = MetadataSample(
    timestamp=10.0, received_at_unix_s=20.0,
    pos_vendor=Vec3(-5.0, 11.0, -3.53),
    attitude_vendor=Vec3(0.0, 0.0, math.pi / 2.0),
    box_origin_vendor=Vec3(0.0, 0.0, -0.75),
    half_extent_vendor=Vec3(0.25, 0.25, 0.75),
)
bounds = module.world_bounds_from_sample(pillar)
assert_vec(bounds.minimum, (10.75, -5.25, 3.53), 1e-6)
assert_vec(bounds.maximum, (11.25, -4.75, 5.03), 1e-6)
assert math.isclose(module.support_face_z(bounds, "bottom"), 3.53)
assert math.isclose(module.aligned_actor_z(pillar, 0.0), 0.0)
```

Also cover the carton-origin fixture, ring target with a negative ENU local z offset, yaw `0`, yaw `pi/2`, and nonzero roll/pitch. Calculate all eight transformed corners in the expected fixture so the test would fail if the implementation merely swaps axes or uses `origin.z ± extent.z` without rotation.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\ue_world_geometry_check.py --module scripts\calibration\ue_world_geometry.py --metadata-module scripts\calibration\object_metadata.py
```

Expected: FAIL because `ue_world_geometry.py` and its public functions do not exist.

- [ ] **Step 3: Implement the pure world-bound module**

Implement immutable `WorldBounds` and these pure operations:

```python
def vendor_actor_pose_to_enu(sample: MetadataSample) -> Tuple[Vec3, Vec3]: ...
def vendor_local_box_to_enu(sample: MetadataSample) -> Tuple[Vec3, Vec3]: ...
def rotation_matrix_enu(roll_rad: float, pitch_rad: float, yaw_rad: float): ...
def world_bounds_from_sample(sample: MetadataSample) -> WorldBounds: ...
def support_face_z(bounds: WorldBounds, face: str) -> float: ...
def aligned_actor_z(sample: MetadataSample, target_support_z: float, child_face: str = "bottom") -> float: ...
```

Construct local corners as `origin ± extent`, rotate every corner, then add the actor position. Reject non-finite data and unsupported faces with `WorldGeometryError`. Do not use Euler shortcuts for the general path.

- [ ] **Step 4: Replace the incorrect metadata ground-offset calculation**

In `analyze_samples`, calculate the median sample, call `world_bounds_from_sample`, and emit:

```json
"world_bounds_enu": {
  "minimum_m": [0, 0, 0],
  "maximum_m": [0, 0, 0],
  "centre_m": [0, 0, 0],
  "dimensions_m": [0, 0, 0]
},
"placement_plane_gap_m": 0.0
```

Define `placement_plane_gap_m = world_bounds.minimum.z - placement_plane_z`. Keep the old `ground_offset_m` key only if repository compatibility search finds a consumer; if retained, set it equal to the corrected gap and mark it deprecated in the module docstring.

- [ ] **Step 5: Extend metadata regression tests**

Update `tests/asset_calibration_metadata_check.py` to assert the actor position, local origin, world bounds, and corrected plane gap separately. Add a regression assertion that the old expression `local_origin_z - extent_z - plane_z` would produce a different result for the live pillar fixture.

- [ ] **Step 6: Add the focused test to the aggregate validator and run GREEN**

Add the new test invocation to `scripts/validate_asset_calibration.ps1`, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
```

Expected: all asset calibration tests PASS and `git diff --check` exits `0`.

- [ ] **Step 7: Commit Task 1**

```powershell
git add scripts/calibration/ue_world_geometry.py scripts/calibration/object_metadata.py tests/ue_world_geometry_check.py tests/asset_calibration_metadata_check.py scripts/validate_asset_calibration.ps1
git commit -m "fix: compute UE object bounds in world coordinates"
```

---

### Task 2: Replace the Showcase with Seven Support-Aware Assets

**Files:**
- Modify: `config/calibration/official_asset_showcase_v1.json`
- Modify: `scripts/calibration/showcase_geometry.py`
- Create: `scripts/calibration/showcase_verifier.py`
- Modify: `scripts/calibration/ue_asset_loader.py`
- Modify: `scripts/calibration/calibration_cli.py`
- Modify: `scripts/calibration/showcase_artifacts.py`
- Modify: `tests/asset_showcase_geometry_check.py`
- Modify: `tests/asset_showcase_cli_check.py`
- Create: `tests/asset_showcase_verifier_check.py`
- Modify: `scripts/validate_asset_calibration.ps1`
- Modify: `docs/runbooks/official-asset-metadata-calibration.md`

**Interfaces:**
- Consumes: Task 1 `world_bounds_from_sample`, `support_face_z`, `aligned_actor_z`; official metadata receiver helpers.
- Produces: `verify_showcase(client, spec, placements, samples=3, timeout_s=5.0) -> dict`, and CLI commands `showcase-load --execute` and `showcase-verify --execute` that emit run-scoped evidence.
- Uses floor object ID `12780` as the declared support in the current predicted course, but obtains the floor top from live metadata instead of assuming `z=0`.

- [ ] **Step 1: Write failing branded-asset exclusion tests**

Change geometry expectations to the exact approved station set:

```python
EXPECTED = (
    ("pillar_813", 13000, (10.5, -4.5, 0.0)),
    ("box_815", 13001, (10.5, -1.5, 0.0)),
    ("box_818", 13002, (10.5, 1.5, 0.0)),
    ("ring_target_150", 13006, (12.5, -4.5, 0.0)),
    ("quad_target_151", 13007, (12.5, -1.5, 0.0)),
    ("aruco_custom_43", 13008, (12.5, 1.5, 0.0)),
    ("luminous_light_60", 13009, (12.5, 4.5, 0.0)),
)
assert not {500, 750, 1000} & {p.class_id for p in placements}
assert [p.object_id for p in placements] == [13000, 13001, 13002, 13006, 13007, 13008, 13009]
assert spec.support_object_id == 12780
assert spec.support_face == "top"
```

The asymmetric rows intentionally keep every station more than `3.0 m` from both current UAV spawn centres `(16.0,-0.7)` and `(16.0,0.7)`, while making each ID recoverable from xy coordinates.

- [ ] **Step 2: Run the geometry test and verify RED**

Run the existing showcase geometry command. Expected: FAIL because the configuration still requires ten stations and includes the three cartons.

- [ ] **Step 3: Update the showcase schema and resolver**

Add `support_object_id`, `support_face`, `excluded_class_ids`, `legacy_cleanup_ids`, and exact seven stations to the JSON. Require `legacy_cleanup_ids == [13003, 13004, 13005]` and `excluded_class_ids == [500, 750, 1000]`. Make `resolve_showcase` reject any excluded ClassID and require the seven exact ID/key/xy associations. A normal transaction rollback removes only the seven placement IDs; the explicit migration/remove operation enumerates the seven placement IDs plus the three legacy cleanup IDs.

Preserve measured dimensions and add measured local box origin in vendor coordinates for each retained asset. This is calibration evidence used to form the initial actor-z command; live verification remains authoritative.

- [ ] **Step 4: Write failing support-alignment and rollback tests**

Create a fake metadata client that returns:

- support ID `12780` with measured world top `0.15 m`;
- seven child samples whose initial local box origins match live evidence;
- one variant whose measured bottom is `0.05 m` above support;
- one timeout variant.

Assert:

```python
commands = loader.build_supported_showcase_commands(spec, placements, support_sample, child_samples)
assert all(command.fit_ground is False for command in commands)
assert all(abs(verifier.measured_support_gap(item)) <= 0.02 for item in passing_items)
assert failed_receipt["state"] == "ROLLED_BACK"
assert failed_receipt["removed_ids"] == [13000, 13001, 13002, 13006, 13007, 13008, 13009]
```

Also assert rollback never destroys `12780`, any ID outside the showcase set, or a full reserved range.

- [ ] **Step 5: Run verifier tests and verify RED**

Expected: FAIL because support-aware command construction, verification, and transactional rollback do not exist.

- [ ] **Step 6: Implement support-aware placement**

Add `SupportedPlacementCommand` containing expected ENU actor pose, NED command pose, scale, support ID, support top, and expected dimensions. Build commands in dependency order:

1. initialize the metadata receiver once;
2. request and validate three samples for support ID `12780`;
3. calculate measured support top;
4. calculate each child actor z using its calibrated local box and `aligned_actor_z`;
5. call `sendUE4PosScale`, never `sendUE4PosScale2Ground`;
6. close the receiver in `finally`.

Keep the existing repeat count of three. Enforce `window_id == 0`, exact allowed IDs, excluded ClassIDs, and positive repeat in both CLI and loader boundaries.

- [ ] **Step 7: Implement live verification and rollback**

For every child, capture three new samples and report actor xy error, yaw error, dimension error, support gap, stability deltas, and pass/fail. A transaction succeeds only if every check passes. On failure, call `sendUE4Destroy` three times for each of the seven showcase IDs and emit `ROLLED_BACK` with per-object errors.

The receipt must include catalog SHA, showcase SHA, stack ID, simulation-instance ID, git commit supplied by CLI arguments, support metadata, all commands, all measurements, and `arming_request=false`, `map_change=false`.

- [ ] **Step 8: Extend the CLI and artifact contracts**

Add required provenance arguments for live execution:

```text
--stack-id
--simulation-instance-id
--git-commit
--output
```

DryRun does not create a UE client or output directory. `--execute` requires all provenance arguments and writes a receipt atomically. Add `showcase-verify` as a read-only live command; it must never reposition an object.

- [ ] **Step 9: Update the runbook and run GREEN**

Document the seven retained models, three excluded branded ClassIDs, floor support ID, no-ground-fit rule, and automatic pass criteria. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
```

Expected: PASS with no live mutation.

- [ ] **Step 10: Commit Task 2**

```powershell
git add config/calibration/official_asset_showcase_v1.json scripts/calibration/showcase_geometry.py scripts/calibration/showcase_verifier.py scripts/calibration/ue_asset_loader.py scripts/calibration/calibration_cli.py scripts/calibration/showcase_artifacts.py tests/asset_showcase_geometry_check.py tests/asset_showcase_cli_check.py tests/asset_showcase_verifier_check.py scripts/validate_asset_calibration.ps1 docs/runbooks/official-asset-metadata-calibration.md
git commit -m "feat: verify showcase placement against measured support"
```

---

### Task 3: Generate the Balanced Z-Shaped L0 Course in Two Width Profiles

**Files:**
- Create: `config/maps/coordinate_verified_course_v1.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_geometry.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_artifacts.py`
- Create: `tests/verified_course_geometry_check.py`
- Create: `tests/verified_course_artifacts_check.py`
- Modify: `scripts/validate_stage8.ps1`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: no live state; the course source JSON and a width profile name.
- Produces: `load_verified_course(path, profile) -> VerifiedCourse`, `resolve_l0(course) -> ResolvedScene`, and deterministic JSON/SVG/validation artifacts.
- Later tasks consume `ResolvedEntity` records with explicit support relationships and expected world bounds.

- [ ] **Step 1: Write failing topology/profile tests**

Define and assert these exact centreline elements:

```text
S1 line: (6.0, 0.0) -> (13.0, 0.0), length 7.0 m
T1 arc: centre (13.0, 1.65), centreline radius 1.65 m, 90 degrees
S2 line: (14.65, 1.65) -> (14.65, 6.65), length 5.0 m
T2 arc: centre (16.30, 6.65), centreline radius 1.65 m, 90 degrees
S3 line: (16.30, 8.30) -> (23.30, 8.30), length 7.0 m
```

Assert takeoff bounds `[0.0, 6.0, -2.5, 2.5]`, takeoff poses `(2.0,-0.6,0.0)` and `(2.0,0.6,0.0)`, landing bounds `[23.3,30.3,5.3,11.3]`, platform centres `(26.8,7.4)` and `(26.8,9.2)`, and platform spacing `1.8 m`.

For `development`, every channel element must resolve to clear width `1.8 m`; for `competition`, `1.5 m`. Assert identical centreline and task-zone coordinates between profiles. Assert no entity category equals `ceiling`.

- [ ] **Step 2: Run the topology tests and verify RED**

Expected: FAIL because the new config and modules do not exist.

- [ ] **Step 3: Implement the versioned source schema**

Store topology once and width values under:

```json
"width_profiles": {"development": 1.8, "competition": 1.5}
```

Reserve a new non-overlapping course transaction range `14000..14999`. Declare structural official UE command type `1000813` (catalog ClassID `813`) with calibrated native full dimensions `[1.0, 1.0, 3.0]` and local box origin evidence. Declare a floor support whose designed top face is ENU `z=0`, wall height `2.5 m`, and wall thickness `0.15 m`. Resolve the root floor actor z from its calibrated local top-face offset so that its world top is exactly `z=0`; all other structural z values derive from that support.

- [ ] **Step 4: Implement pure centreline and wall generation**

Generate walls from line/arc offsets using the selected clear width and wall half-thickness. Tessellate arcs with maximum chord error `0.02 m`. Place structural actors by aligning their measured bottom to floor top `z=0`, rather than setting actor z to zero. Use stable IDs derived from ordered semantic roles, not random iteration order.

Reject unknown profiles, width greater than `1.8 m`, competition width other than `1.5 m`, inner turn radius greater than `1 m`, scored segment shorter than `3 m`, duplicate IDs, ceiling objects, or bounds outside the declared arena. Explicitly assert derived inner radii `0.75 m` for development and `0.90 m` for competition.

- [ ] **Step 5: Implement L0 clearance and reachability validation**

Inflate walls by the configured UAV horizontal radius `0.225 m` plus safety margin `0.10 m`. Rasterize at `0.05 m` resolution and prove a path from each takeoff pose through all three scored segment gates to each landing approach. Report minimum analytic channel width and minimum raster clearance separately.

L0 contains no task targets or obstacles. The report must explicitly say `difficulty_level=L0` and must not imply higher-level coverage.

- [ ] **Step 6: Implement deterministic artifacts**

Generate:

- `resolved_scene.json` with support graph and expected bounds;
- `channel_local_geometry.json` with segment frames and gates;
- `course_preview.svg` with exact dimensions and profile label;
- `validation_report.json`;
- `artifact_manifest.json` containing source-spec SHA and resolved-scene SHA.

Run generation twice in separate temporary directories and assert byte-identical outputs for the same profile.

- [ ] **Step 7: Add both profiles to Stage 8 validation and run GREEN**

Add focused tests and generation checks to `scripts/validate_stage8.ps1` without removing the protected V1 tests. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
D:\PX4PSP\Python38\python.exe tests\script_inventory_check.py --project-root .
```

Expected: old predicted course and both new L0 profiles PASS.

- [ ] **Step 8: Commit Task 3**

```powershell
git add config/maps/coordinate_verified_course_v1.json future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_geometry.py future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_artifacts.py tests/verified_course_geometry_check.py tests/verified_course_artifacts_check.py scripts/validate_stage8.ps1 scripts/README.md
git commit -m "feat: generate coordinate-verified Z course foundation"
```

---

### Task 4: Add Transactional L0 UE Loading and Live Coordinate Verification

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_ue_loader.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_live_verifier.py`
- Create: `tests/verified_course_ue_loader_check.py`
- Create: `tests/verified_course_live_verifier_check.py`
- Modify: `scripts/validate_stage8.ps1`
- Create: `docs/runbooks/coordinate-verified-course.md`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: Task 3 `ResolvedScene`, Task 1 world-bound functions, official UE metadata API.
- Produces: DryRun-first `generate`, `load`, `verify`, and `remove` CLI operations for transaction range `14000..14999`.
- Live success receipt state is at most `LOADED_VERIFIED`.

- [ ] **Step 1: Write failing command and transaction tests**

Assert that DryRun lists every command in support dependency order, with window `0`, normal position/scale API, exact source/resolved hashes, `map_change=false`, and `arming_request=false`. Assert nonzero/negative window IDs fail before client creation.

Use a fake client to assert:

- only IDs present in the resolved transaction are destroyed;
- no loop destroys the full `14000..14999` range;
- floor/supports load before walls/platforms;
- each command is sent three times;
- `sendUE4PosScale2Ground` and map-change commands are never called.

- [ ] **Step 2: Run loader tests and verify RED**

Expected: FAIL because the loader does not exist.

- [ ] **Step 3: Implement DryRun-first transactional loading**

Require a previously generated validation report whose source and resolved
hashes match. A live load requires explicit `--execute`, `--stack-id`,
`--simulation-instance-id`, `--git-commit`, and `--output`.

Place entities in topological support order. After placing a support, capture
three samples and calculate its actual support face. Recalculate dependent actor
poses from that measured support before sending their commands.

- [ ] **Step 4: Write failing live-verification tests**

Fixtures must cover:

- all entities within tolerance -> `LOADED_VERIFIED`;
- one wall xy error `0.021 m` -> rollback;
- support gap `0.021 m` -> rollback;
- dimension-axis error `0.021 m` -> rollback;
- yaw error `1.01 degree` -> rollback;
- missing or stale sample -> rollback;
- duplicate/unexpected ID -> rollback;
- rollback failure -> state `ROLLBACK_INCOMPLETE` and nonzero exit.

- [ ] **Step 5: Implement full-scene verification**

Verify per-object bounds, support gaps, dimensions, actor xy, yaw, sample
stability, and exact expected IDs. Reconstruct measured wall polygons and report
minimum measured clear width. Re-run the inflated L0 reachability check against
measured geometry.

Write the receipt atomically only after verification or rollback completes. A
successful command-send phase without verification is `LOAD_UNVERIFIED`, never
success.

- [ ] **Step 6: Implement bounded rollback and remove**

Rollback/remove enumerates only IDs stored in the resolved scene and repeats
each destroy three times on window `0`. After removal, clear each target's
update flag, request fresh metadata, and require no fresh response within the
bounded timeout before reporting absence. Never treat a stale cached sample as
presence or absence. Never clear the map or scan/delete an entire range.

- [ ] **Step 7: Document the no-arm live gate**

The runbook must require:

- manifest-owned RflySim3D and `SLAMScene` command line;
- `fail_closed=false`, no stale/unknown process, and no unknown required ports;
- run-scoped `GUI_READY=true` and `COURSE_READY=true` health files;
- DryRun receipt review before `--execute`;
- no flight during L0 coordinate acceptance.

Document that inspect's ROS `course_ready` publisher probe is a separate planner-topic condition and does not replace the run-scoped UE course-load health file.

- [ ] **Step 8: Add aggregate validation and run GREEN**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
```

Expected: PASS with no live state changes.

- [ ] **Step 9: Commit Task 4**

```powershell
git add future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_ue_loader.py future_aircraft_ws/src/multi_uav_mission/scripts/verified_course_live_verifier.py tests/verified_course_ue_loader_check.py tests/verified_course_live_verifier_check.py scripts/validate_stage8.ps1 docs/runbooks/coordinate-verified-course.md scripts/README.md
git commit -m "feat: verify live Z course geometry transactionally"
```

---

### Task 5: Review, Integrate, and Perform the First No-Arm Live Acceptance

**Files:**
- Modify only if evidence requires correction: files introduced in Tasks 1–4.
- Produce ignored run evidence under: `logs/live_stack/<stack_id>/coordinate_verified_course/`
- Produce ignored generated artifacts under: `generated/coordinate_verified_course_v1/`

**Interfaces:**
- Consumes: completed Tasks 1–4 and the current lifecycle manifest.
- Produces: an integration-ready feature branch and either a `LOADED_VERIFIED` L0 development receipt or a precise failure/rollback report; merging and worktree cleanup occur only through the repository's finishing workflow.

- [ ] **Step 1: Request independent code review**

Review the full feature range against the approved design. Critical and Important findings block merge. Require special review of frame conversion, transformed bounds, ID containment, window containment, rollback, provenance, and test realism.

- [ ] **Step 2: Run final offline verification on the feature branch**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
git diff --check
```

Expected: all exit `0`. Worktree-only submodule initialization failures are reported as environment gaps, but merged-main verification must pass before cleanup.

- [ ] **Step 3: Apply the repository finishing workflow**

Use `finishing-a-development-branch` to present the supported integration choices. If the user selects local integration, fast-forward the approved feature branch to `main` without pulling or pushing, rerun the five commands from Step 2 in the main checkout, then remove only the superpowers-owned feature worktree and delete the merged feature branch. Do not delete a worktree or branch before merged-main verification passes.

- [ ] **Step 4: Remove the currently incorrect showcase transaction**

Inspect the active manifest first. Run showcase-remove DryRun, confirm exact IDs `13000,13001,13002,13006,13007,13008,13009` plus legacy branded IDs `13003,13004,13005` are the only targets, then execute removal on window `0`. Query all ten legacy IDs and require absence. Do not stop or restart the stack merely to remove them.

- [ ] **Step 5: Generate and review L0 development artifacts**

Generate `coordinate_verified_course_v1/development/L0/seed-0`, review source and resolved hashes, exact wall commands, support graph, path report, and `GENERATED_VALID` state.

- [ ] **Step 6: Run no-arm live load and automatic verification**

If the current stack still passes ownership and health gates, execute the new loader with width profile `development`, level `L0`, seed `0`, window `0`, and current stack/simulation provenance. Otherwise stop and request a separately authorized fresh stack; do not infer permission to restart.

Success requires `LOADED_VERIFIED`, every per-entity error within tolerance, measured minimum width at least `1.8 m - 0.02 m`, measured reachability PASS, and zero rollback actions. Visual inspection is optional and cannot substitute for these checks.

- [ ] **Step 7: Preserve evidence and hand off**

Report commands, commit, stack/simulation IDs, generated and measured hashes, maximum xy/support/dimension/yaw errors, measured minimum width, reachability result, and any remaining risk. Leave the verified no-arm stack running for operator appearance review unless the user requests manifest-owned shutdown.

---

## Deferred Follow-Up Plans

This foundation deliberately defers:

- L1 official cone/post/gate candidate calibration and randomized static obstacles;
- L2 swinging-hanger actuation and full-period swept-volume verification;
- L3 colored/QR/thermal target observation models;
- L4 seed suites and 1.5 m competition stress runs;
- distinct simultaneous ArUco image deployment;
- LiDAR/RGB sensor verification and all flight/mission acceptance.

Each deferred item receives its own design-aligned plan after the L0 foundation reaches `LOADED_VERIFIED`.
