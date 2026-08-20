# Smoother Tunnel Waypoint Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce tunnel waypoint hesitation by advancing course navigation when each aircraft is within 0.50 m of an intermediate goal.

**Architecture:** Keep the existing sampled centreline and UAV1-first tandem pipeline. Change only the course-mode navigation verification tolerance and lock that behavior into the existing Stage 8 course-plan contract.

**Tech Stack:** Python 3.8, generated JSON mission plans, focused script-based contract tests.

## Global Constraints

- Keep `SLAMScene` and `config/maps/predicted_narrow_course_v1.json` unchanged.
- Keep centreline sampling, tandem ordering, `max_vel=0.6`, and `max_acc=0.8` unchanged.
- Do not change EGO-Swarm, PX4, watchdog, geofence, takeoff, landing, or lifecycle behavior.
- Use `tolerance_m=0.50` for course-mode `verify_planned_navigation` actions.

---

### Task 1: Course Handoff Tolerance

**Files:**
- Modify: `tests/stage8_course_flight_plan_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py`

**Interfaces:**
- Consumes: `build_plan(config, course_spec)` from `stage7_flight_plan.py`.
- Produces: course-mode navigation actions whose `tolerance_m` is exactly `0.5`.

- [ ] **Step 1: Write the failing contract assertion**

Add after collecting `verify_actions`:

```python
assert all(abs(float(action["tolerance_m"]) - 0.5) <= 1e-9 for action in verify_actions)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run the existing `tests/stage8_course_flight_plan_check.py` command with the live config, course specification, and dual EGO launch arguments. Expected: failure because generated actions contain `tolerance_m=0.3`.

- [ ] **Step 3: Apply the minimal production change**

In the course-mode `verify_goal` helper, replace:

```python
tolerance_m=0.3,
```

with:

```python
tolerance_m=0.5,
```

- [ ] **Step 4: Verify GREEN and compilation**

Rerun the same focused contract command and run `python -m py_compile` on `stage7_flight_plan.py`. Expected: both commands exit 0.

- [ ] **Step 5: Review and commit**

Run `git diff --check`, confirm the diff contains only the assertion and tolerance change, then commit with `fix: smooth tunnel waypoint handoff`.

### Task 2: Live Confirmation

**Files:**
- Runtime artifacts only under `logs/stage7_live/<new-run-id>/`; no source edits.

**Interfaces:**
- Consumes: the currently active manifest-owned simulation stack and a fresh run-scoped readiness report.
- Produces: a new flight report and score summary.

- [ ] **Step 1: Confirm the active stack is healthy and both aircraft are disarmed**

Run `sim.ps1 status` and query both `/uavX/mavros/state` topics. Do not arm unless the new run readiness gates pass.

- [ ] **Step 2: Start the updated EGO/mission chain and obtain fresh readiness**

Use the existing manifest lifecycle and Stage 7 launch scripts. Do not use name-based process cleanup.

- [ ] **Step 3: Run the mission with explicit simulation gates**

Launch with `--allow-arm --simulation-only` only after current-run readiness PASS and policy `allow_arm=true` are confirmed.

- [ ] **Step 4: Inspect live evidence**

Confirm executor exit 0, both navigation/landing checks true, collision count 0, offboard loss count 0, and compare duration/visual hesitation with run `stage7-20260820T110453Z-2745`.
