# Competition Course V2 Map Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce fresh offline and no-arm live evidence that the Competition Course V2 specification, preview, RflySim scene, vehicle views, and sensor observations agree.

**Architecture:** Preserve the existing single-source V2 JSON and recovered accepted-arena layout. Add focused behavior tests around the real RflySim conversion/loader boundary and conservative free-space validation, then use the existing manifest lifecycle for map-only and sensor-only acceptance.

**Tech Stack:** Python 3.8, JSON, SVG, OpenCV, PowerShell/batch, RflySim UE API, ROS1 Noetic.

## Global Constraints

- Do not modify TF, PX4/MAVROS lifecycle, process ownership, EGO/Faster-LIO parameters, mission logic, OFFBOARD, takeoff, or landing behavior.
- Keep `predicted_narrow_course` the default; V2 remains explicit opt-in.
- Never arm, start OFFBOARD, start EGO, or execute a mission in this plan.
- Stop on unknown/stale lifecycle ownership or any unsafe live precondition.
- End immediately after C2; navigation belongs to the next baseline.

---

### Task 1: Complete deterministic transform and geometry contracts

**Files:**
- Create: `tests/competition_course_v2_transform_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_geometry.py`
- Modify: `tests/competition_course_v2_geometry_check.py`
- Modify: `scripts/validate_competition_course_v2.ps1`

**Interfaces:**
- Consumes: `competition_course_v2.json`, `build_entity_manifest`, and the actual loader fake-SDK boundary.
- Produces: a machine-readable route/free-space geometry report and focused transform test coverage.

- [ ] Write transform and free-space tests that fail because the dedicated report/contract is missing.
- [ ] Run the focused tests and confirm the expected RED failures.
- [ ] Implement the smallest pure geometry/report additions; keep conversion formulas centralized at the existing boundary.
- [ ] Run the focused tests and complete validator to GREEN.
- [ ] Generate artifacts twice and inspect the deterministic top-down preview.

### Task 2: Pass Gate B and prepare bounded live acceptance

**Files:**
- Modify: `docs/current/competition-map-v2.md`
- Create only if needed: project-owned read-only screenshot/evidence helper and focused test.

**Interfaces:**
- Consumes: structural report, entity manifest, preview, current lifecycle inspect/dry-run output.
- Produces: Gate B result and an exact safe C1/C2 command/evidence sequence.

- [ ] Run V2 validator, repository/docs checks, and relevant Stage 7/8 offline regressions.
- [ ] Inspect preview semantics and compare manifest centres/yaws/scales against the source.
- [ ] Inspect current host/WSL lifecycle state without mutation; fail closed on unknown ownership.
- [ ] Record Gate B and live preconditions in run-scoped evidence.

### Task 3: Execute C1 map-only and C2 no-arm sensor acceptance

**Files:**
- Create: minimal run-scoped ignored artifacts.
- Create: `docs/evidence/2026-09-01-competition-course-v2-map-acceptance.md`
- Modify: `docs/current/competition-map-v2.md`
- Modify: `.agents/AGENT2READ.md`
- Modify: `docs/current/competition-roadmap.md`

**Interfaces:**
- Consumes: explicit V2 lifecycle start, load receipt, scene/motion evidence, dual sensor/Faster-LIO stack.
- Produces: C1/C2 evidence and either truthful `MAP READY` or `BLOCKED` status.

- [ ] Start explicit V2 no-arm stack only after safe preconditions pass.
- [ ] Capture minimal map-only scene evidence for spawns, headings, course, obstacles, and landing area.
- [ ] Start full sensor diagnostics and Faster-LIO only; collect dual RGB/LiDAR/IMU/odometry evidence.
- [ ] Verify visual accessibility and point-cloud geometry rather than topic activity alone.
- [ ] Use only authorized manifest lifecycle cleanup and verify restoration/ownership state.
- [ ] Update current truth, run fresh final verification, review diff, and create logical commits without pushing.
