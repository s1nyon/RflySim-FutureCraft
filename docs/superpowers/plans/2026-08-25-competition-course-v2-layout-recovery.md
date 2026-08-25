# Competition Course V2 Layout Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebase Competition Course V2 onto the accepted predicted-course arena, guarantee mutually exclusive project course layers and conservative obstacle clearance, and emit deterministic geometry/evaluation artifacts before any further live run.

**Architecture:** Keep `competition_course_v2.json` as the single ENU source of truth. Pure Python geometry functions normalize the arena, course, obstacles, clearance windows, and evaluation semantics; a standalone transition helper destroys only exact IDs declared by tracked project specs before either course is loaded. Artifact generation derives the UE manifest, spawn arguments, dimensioned SVG, and evaluation reference from the same model.

**Tech Stack:** Python 3.8-compatible standard library, existing OpenCV ArUco dependency, RflySim `UE4CtrlAPI`, Windows batch/PowerShell, repository script-style tests.

## Global Constraints

- Base infrastructure remains `f23de934205b6776ef0531d46c26444bf9f7f65e`; do not modify TF, Faster-LIO, EGO, MAVROS, PX4, mission, lifecycle ownership, or readiness.
- `predicted_narrow_course` remains the default.
- V2 remains opt-in and uses the accepted arena at ENU `x ~= 13.5..39.3 m`, not the native near-origin region.
- Destroy only exact entity IDs derived from tracked map specs.
- Vehicle diameter is `0.45 m`, margin is `0.25 m` each side, and minimum passable gap is `1.00 m`.
- Pendulum acceptance requires a continuous `>=1.50 s` window with a `>=1.00 m` free-side gap.
- RflySim truth is evaluation-only, ROS explains runtime behavior, and RViz is visualization-only.
- This plan is offline-only. Stop before any live stack.

---

### Task 1: Rebase the source and spawn contract

**Files:**
- Create: `tests/competition_course_v2_substrate_check.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_spawn_args.py`
- Modify: `config/maps/competition_course_v2.json`
- Modify: `config/env_template.bat`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py`
- Modify: `scripts/start_competition_course_v2_two_uav.bat`
- Modify: `tests/competition_course_v2_geometry_check.py`
- Modify: `tests/competition_course_v2_entrypoint_check.py`

**Interfaces:**
- Consumes: accepted values from `predicted_narrow_course_v1.json`.
- Produces: `spawn_environment(spec: dict) -> Dict[str, str]` with the three `STAGE2_*` launch strings; import `Dict` from `typing` for Python 3.8 compatibility.

- [ ] **Step 1: Write the failing substrate test**

Assert exact equality with the accepted substrate:

```python
assert v2["takeoff_area"]["bounds"] == predicted["takeoff_zone"]["bounds"]
assert v2["spawns"] == {
    "uav1": [16.0, -0.7, 0.0],
    "uav2": [16.0, 0.7, 0.0],
}
assert v2["spawn_yaw_deg"] == {"uav1": 0.0, "uav2": 0.0}
assert v2["course"][0]["start"] == [18.5, 0.0]
assert v2["course"][-1]["end"] == [29.3, 4.9]
assert v2["landing"]["bounds"] == [29.3, 34.3, 2.9, 6.9]
assert min(p[0] for p in v2["spawns"].values()) >= 13.5
```

Compare arena floor, boundary, ceiling, surface, centerline, and landing geometry by name/center/size; IDs may differ.

- [ ] **Step 2: Verify RED**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_substrate_check.py --project-root .
```

Expected: FAIL because V2 still uses spawn `x=2` and corridor entry `x=5`.

- [ ] **Step 3: Rewrite only the V2 spec**

Copy the accepted arena geometry and add:

```json
"spawn_yaw_deg": {"uav1": 0.0, "uav2": 0.0},
"clearance_policy": {
  "vehicle_diameter_m": 0.45,
  "lateral_margin_each_side_m": 0.25,
  "minimum_passable_gap_m": 1.0,
  "minimum_dynamic_safe_window_sec": 1.5,
  "sampling_hz": 120.0
}
```

Assign unique V2-owned IDs to copied arena/surface entities.

- [ ] **Step 4: Derive launch arguments from the spec**

Implement:

```python
def spawn_environment(spec):
    ordered = [spec["spawns"][name] for name in ("uav1", "uav2")]
    yaws = [spec["spawn_yaw_deg"][name] for name in ("uav1", "uav2")]
    return {
        "STAGE2_POS_X_STR": ",".join(_fmt(p[1]) for p in ordered),
        "STAGE2_POS_Y_STR": ",".join(_fmt(p[0]) for p in ordered),
        "STAGE2_YAW_STR": ",".join(_fmt(90.0 - yaw) for yaw in yaws),
    }
```

The CLI prints only three allow-listed `set KEY=value` lines. Remove V2 spawn duplication from `env_template.bat`.

- [ ] **Step 5: Verify GREEN**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_substrate_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_geometry_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_entrypoint_check.py --project-root .
```

Expected derived NED launch values: lateral `-0.7,0.7`, forward `16,16`, yaw `90,90`.

- [ ] **Step 6: Commit**

```bash
git add config/maps/competition_course_v2.json config/env_template.bat future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_spawn_args.py scripts/start_competition_course_v2_two_uav.bat tests/competition_course_v2_substrate_check.py tests/competition_course_v2_geometry_check.py tests/competition_course_v2_entrypoint_check.py
git commit -m "map: rebase competition course on accepted arena"
```

### Task 2: Enforce mutually exclusive course layers

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/course_layer_transition.py`
- Create: `tests/course_layer_transition_check.py`
- Create: `scripts/transition_project_course_layer.bat`
- Modify: `scripts/start_predicted_course_two_uav.bat`
- Modify: `scripts/start_competition_course_v2_two_uav.bat`
- Modify: `scripts/validate_competition_course_v2.ps1`
- Modify: `tests/competition_course_v2_entrypoint_check.py`

**Interfaces:**
- Produces: `build_transition_plan(selected: str, declared_ids: Mapping[str, Iterable[int]]) -> dict` and `execute_transition(api, plan: dict, receipt_path: Path, window_id: int) -> dict`.

- [ ] **Step 1: Write failing exact-ID tests**

```python
plan = build_transition_plan("competition_course_v2", {
    "predicted_narrow_course": [12001, 12002],
    "competition_course_v2": [15001, 15002],
})
assert plan["destroy_ids"] == [12001, 12002, 15001, 15002]
assert 9999 not in plan["destroy_ids"]
```

Also reject duplicate/overlapping declarations, malformed IDs, and unknown selected names. Assert the reverse transition and receipt content.

- [ ] **Step 2: Verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\course_layer_transition_check.py --project-root .
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement transition planning and execution**

Build exact ID sets from the two tracked specs. Send one `sendUE4Destroy` per sorted exact ID. Atomically write a receipt containing selected course, exact destroyed IDs, source hashes, window ID, and `cleanup_policy="exact_declared_ids"`. Import the SDK only in execute mode.

- [ ] **Step 4: Integrate both explicit entrypoints**

Call `transition_project_course_layer.bat <selected>` after scene readiness and before the selected loader. Dry-run prints exact IDs and performs no SDK import. Do not duplicate ID lists in batch files.

- [ ] **Step 5: Verify GREEN and old-map protection**

```powershell
D:\PX4PSP\Python38\python.exe tests\course_layer_transition_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_entrypoint_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

- [ ] **Step 6: Commit**

```bash
git add future_aircraft_ws/src/multi_uav_mission/scripts/course_layer_transition.py tests/course_layer_transition_check.py scripts/transition_project_course_layer.bat scripts/start_predicted_course_two_uav.bat scripts/start_competition_course_v2_two_uav.bat scripts/validate_competition_course_v2.ps1 tests/competition_course_v2_entrypoint_check.py
git commit -m "map: enforce exclusive project course layers"
```

### Task 3: Enforce conservative geometric clearance

**Files:**
- Create: `tests/competition_course_v2_clearance_check.py`
- Modify: `config/maps/competition_course_v2.json`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py`
- Modify: `tests/competition_course_v2_geometry_check.py`

**Interfaces:**
- Produces: `static_clearance_reports(spec)`, `turn_clearance_reports(spec)`, `spawn_clearance_report(spec)`, and `pendulum_clearance_report(spec)`.

- [ ] **Step 1: Write failing numerical tests**

For a line segment normal `(nx, ny)` use:

```python
half_lateral = abs(nx) * size_x / 2 + abs(ny) * size_y / 2
offset = dot(center - segment_start, normal)
left_gap = width / 2 - (offset + half_lateral)
right_gap = (offset - half_lateral) + width / 2
```

Assert `0.99 m` fails and `1.00 m` passes. Assert turn clearance equals `(width-diameter)/2-chord_error`. Sample the pendulum at 120 Hz as a circular period and reject a longest safe interval below `1.50 s`. Reject spawns outside the safety-expanded takeoff free space or facing away from the entry.

- [ ] **Step 2: Verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_clearance_check.py --project-root .
```

- [ ] **Step 3: Implement minimal report functions**

Use projected rectangle extents, unrounded acceptance floats, circular safe-window merging, explicit segment-name validation, and error messages naming obstacle, segment, actual gap, and required gap.

- [ ] **Step 4: Apply the conservative profile**

Use these initial values, subject to the validator:

```text
static A: section_a, center [20.5, 0.60], lateral size 0.25 m
static B: section_b, center [23.35, 2.40], lateral size 0.20 m
pendulum: section_c, pivot [27.0, 4.9, 2.4], lateral size 0.20 m,
          length 1.2 m, amplitude 30 deg, period 6.0 s
```

Never weaken the `1.00 m` or `1.50 s` gates to make the profile pass.

- [ ] **Step 5: Verify GREEN**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_clearance_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_geometry_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_motion_check.py --project-root .
```

- [ ] **Step 6: Commit**

```bash
git add config/maps/competition_course_v2.json future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py tests/competition_course_v2_clearance_check.py tests/competition_course_v2_geometry_check.py
git commit -m "map: enforce conservative course clearance"
```

### Task 4: Generate a dimensioned top-down preview

**Files:**
- Create: `tests/competition_course_v2_preview_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_artifacts.py`
- Modify: `tests/competition_course_v2_artifacts_check.py`

**Interfaces:**
- Produces: `build_preview_svg(spec: dict, entities: List[dict], reports: dict) -> str`; import `List` from `typing` for Python 3.8 compatibility.

- [ ] **Step 1: Write the failing SVG test**

Parse XML and require groups `arena`, `centerline`, `walls`, `spawns`, `camera_axes`, `static_obstacles`, `pendulum_sweep`, `task_zone`, `landing`, `dimensions`, and `legend`. Require the spec hash, Section A/B/C labels, actual gaps, safe-window duration, and spawn coordinates.

- [ ] **Step 2: Verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_preview_check.py --project-root .
```

- [ ] **Step 3: Implement preview generation**

Render normalized polygons, safety-expanded spawn disks, heading/camera arrows, translucent pendulum sweep, and dimension lines. Escape text and format every float deterministically.

- [ ] **Step 4: Verify deterministic output**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_preview_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_artifacts_check.py --project-root .
```

Generate twice and require byte-identical SVG/hash manifests.

- [ ] **Step 5: Perform offline visual review**

Inspect the SVG for a shared entry view, no near-origin geometry, generous static bypasses, pendulum sweep contained in Section C, and landing pads beyond the exit. Label this evidence `OFFLINE VISUAL REVIEW`.

- [ ] **Step 6: Commit**

```bash
git add future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_artifacts.py tests/competition_course_v2_preview_check.py tests/competition_course_v2_artifacts_check.py
git commit -m "map: add dimensioned competition course preview"
```

### Task 5: Emit the evaluation reference

**Files:**
- Create: `tests/competition_course_v2_evaluation_reference_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_artifacts.py`
- Modify: `tests/competition_course_v2_artifacts_check.py`
- Modify: `docs/current/competition-map-v2.md`

**Interfaces:**
- Produces: `build_evaluation_reference(spec, entities, reports) -> dict` and `evaluation_reference.json`.

- [ ] **Step 1: Write the failing contract test**

Require exact spec hash; cumulative `course_s` for all five elements; wall/static polygons; pendulum truth and safe windows; two landing polygons; target truth; clearance policy; and metric IDs for takeoff, entry, segment completion, wall/static/dynamic clearance, inter-UAV distance, collision, OFFBOARD loss, target error, landing error, and localization error.

Assert:

```python
assert all(metric["primary_evidence"] != "rviz" for metric in reference["metrics"])
```

- [ ] **Step 2: Verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_evaluation_reference_check.py --project-root .
```

- [ ] **Step 3: Implement the pure builder**

Use Euclidean line length and `abs(sweep)*radius` arc length. Emit evidence planes `map_spec`, `rflysim_ground_truth`, `ros_runtime`, and `derived_offline`. Set `ground_truth_transport="NOT_AUDITED_IN_MAP_TASK"` instead of inventing a topic/API.

- [ ] **Step 4: Update current documentation**

State that RViz is not a score source, the map side of the measurement contract is implemented, and the full evaluator/GT bridge remains a later task.

- [ ] **Step 5: Verify GREEN**

```powershell
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_evaluation_reference_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\competition_course_v2_artifacts_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
```

- [ ] **Step 6: Commit**

```bash
git add future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_artifacts.py tests/competition_course_v2_evaluation_reference_check.py tests/competition_course_v2_artifacts_check.py docs/current/competition-map-v2.md
git commit -m "map: publish competition evaluation reference"
```

### Task 6: Complete offline acceptance and stop at the live gate

**Files:**
- Modify: `scripts/validate_competition_course_v2.ps1`
- Modify: `scripts/README.md`
- Modify: `docs/current/competition-map-v2.md`
- Modify: `.agents/AGENT2READ.md`

**Interfaces:**
- Produces: one truthful offline acceptance statement; live remains pending.

- [ ] **Step 1: Add all focused tests to the V2 validator**

Run substrate, transition, geometry, clearance, motion, loader, entrypoint, preview, artifacts, live-probe normalization, and evaluation-reference checks. Generate twice and compare complete artifact hashes.

- [ ] **Step 2: Run complete offline validation**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_competition_course_v2.ps1
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 3: Review protected scope**

```powershell
git diff --name-only f23de934205b6776ef0531d46c26444bf9f7f65e
```

Confirm no TF launch, odom/cloud adapter, mission, EGO submodule, Faster-LIO, MAVROS, PX4, lifecycle internals, or default map selection changed.

- [ ] **Step 4: Record exact Current Truth**

```text
Competition Course V2 offline geometry: PASS
Course-layer exclusivity contract: PASS
Minimum static gap: >=1.00 m
Pendulum predicted safe window: >=1.50 s
Map-only live visual review: NOT RUN IN OFFLINE RECOVERY
LiDAR/RGB visibility: NOT RE-VALIDATED AFTER REVISION
Faster-LIO/EGO smoke: NOT RUN AFTER REVISION
Competition evaluator: NOT IMPLEMENTED
```

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_competition_course_v2.ps1 scripts/README.md docs/current/competition-map-v2.md .agents/AGENT2READ.md
git commit -m "docs: record competition map offline recovery"
```

- [ ] **Step 6: Stop before live**

Report the SVG path, exact clearances, safe-window duration, validation results, commits, and remaining map-only live gate. Do not start a stack until the human accepts the revised preview.
