# Faster Tandem Tunnel Flight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fly the existing tunnel route at 0.6 m/s with UAV1 leading UAV2 by a nominal 1.1 m.

**Architecture:** Uniformly sample the existing line/arc centreline by arc length, then generate pipelined planner actions with UAV1 one sample ahead. Keep landing goals, safety gates, and core planners unchanged; expose the higher limits through the existing dual launch arguments.

**Tech Stack:** Python 3 flight-plan generator, ROS1 XML launch, existing Python contract test.

## Global Constraints

- UAV1 enters before UAV2.
- Nominal shared-route spacing is 1.1 m and must remain within 0.9-1.35 m in the generated route.
- EGO defaults are 0.6 m/s and 0.8 m/s^2.
- Do not modify PX4, EGO core, lifecycle, watchdog, geofence, or arming behavior.

---

### Task 1: Contract the tandem plan and speed

**Files:**
- Modify: `tests/stage8_course_flight_plan_check.py`
- Test: `tests/stage8_course_flight_plan_check.py`

**Interfaces:**
- Consumes: `stage7_flight_plan.build_plan(config, course)` and `rflysim_ego_swarm_dual.launch`.
- Produces: assertions for 0.6/0.8 launch defaults, sampled route spacing, and UAV1-leading pipelined action order.

- [ ] **Step 1: Replace the old all-UAV1-then-all-UAV2 assertions**

Assert that shared goals are uniformly sampled, that each pipeline cycle publishes UAV1 sample `n+1` before UAV2 sample `n`, and that world-frame sample gaps are between 0.9 m and 1.35 m.

- [ ] **Step 2: Add launch-limit assertions**

```python
assert float(launch_args["max_vel"]) == 0.6
assert float(launch_args["max_acc"]) == 0.8
```

- [ ] **Step 3: Run the focused contract and verify RED**

Run the existing `tests/stage8_course_flight_plan_check.py` command with its four required paths. Expected: FAIL because the current plan groups all UAV1 actions first and launch defaults remain 0.3/0.5.

### Task 2: Implement uniform sampling and pipelined dispatch

**Files:**
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch`
- Test: `tests/stage8_course_flight_plan_check.py`

**Interfaces:**
- Produces: `_sample_centreline(course, target_spacing_m=1.1) -> list[list[float]]` and unchanged public `build_plan(config, course) -> dict`.

- [ ] **Step 1: Sample lines and arcs by cumulative arc length**

Compute each segment length, choose `ceil(total_length / 1.1)` equal intervals, and evaluate every sample on the original line or directed arc. Preserve the exact start and end points.

- [ ] **Step 2: Generate pipelined actions**

Dispatch and verify UAV1's first shared point. For each later shared point, publish UAV1 point `n` and UAV2 point `n-1` before verifying both. After UAV2 reaches the final shared point, send each vehicle to its existing landing platform.

- [ ] **Step 3: Raise launch defaults**

Set `max_vel=0.6` and `max_acc=0.8` in `rflysim_ego_swarm_dual.launch`.

- [ ] **Step 4: Run the focused contract and verify GREEN**

Run only `tests/stage8_course_flight_plan_check.py` with the production module, active config, course spec, and dual launch. Expected: `stage8 course flight plan: PASS`.

- [ ] **Step 5: Review diff and commit**

Commit only the focused test, flight-plan generator, launch defaults, and this plan.
