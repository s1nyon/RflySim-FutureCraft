# Competition Course V2 — MAP READY (fresh-startup closure)

Date: 2026-09-01 (Asia/Shanghai)
Branch: `infra/rviz-live-handoff-20260825`
Head commits at closure: `10fe558` (helpers), `354d5a6` (start-batch block
parsing fix), `7bb5d38` (dynamic acceptance contract fix), `0145e0b` (closure
plan and runtime contract docs).

Status: **MAP READY — CLOSED**

Two independent fresh RflySim startup runs satisfied the acceptance contract
defined in
[`../current/2026-09-01-competition-course-v2-fresh-startup-closure-plan.md`](../current/2026-09-01-competition-course-v2-fresh-startup-closure-plan.md):

```text
offline validation PASS
fresh startup #1: probes + visuals PASS
fresh startup #2: probes + visuals PASS
no manual hot reload
no cross-instance receipt cleanup
no selected-course Destroy/Create race
COURSE_READY depends on world-state evidence
```

This supersedes the withdrawn acceptance in
[`2026-09-01-competition-course-v2-map-acceptance.md`](2026-09-01-competition-course-v2-map-acceptance.md)
(already marked `SUPERSEDED BY FRESH-START FAILURE`).

## Authoritative inputs

- Single source: `config/maps/competition_course_v2.json`
- Final spec SHA-256: `6ce845ddb7269898929acfd5be17a11c18e0f7eb79be11c873bbb09a94fd9b69`
- Map: `competition_course_v2`, base scene `SLAMScene`
- Expected entities per manifest: 40 (22 walls, arena/substrate, 2 static
  obstacles, pendulum, target slot, 2 landing platforms, 2 ArUco markers)

## Fresh run #1

- Stack: `stack-20260901T103159Z-8f44a047`
- Simulation instance: `px4-5b85f20c86d288ef`
- `COURSE_READY=true` with detail `competition course v2 retained; world-state probe A/B PASS; run-scoped receipt`
- Probe A: **PASS**, 40/40 observed, missing `[]`, errors `[]`
  - pendulum dimensions `[0.25, 0.2, 0.7]` m (spec Scale, no native-size regression)
  - pendulum Y motion range `0.8297` m, samples 63
- Probe B: **PASS**, 40/40 observed, missing `[]`, errors `[]`
  - pendulum Y motion range `1.0667` m, samples 62
- Motion controller: PID `15608` registered at creation, scale
  `[0.25, 0.2, 0.2333]` (z = 0.7 / 3 native), 400 recorded samples
- Load receipt: stack/instance scoped, `selected_course_destroy=false`,
  `static_passes=2`, `static_settle_seconds=0.3`
- Transition receipt: destroyed only `predicted_narrow_course` (34 IDs),
  preserved `competition_course_v2` (40 IDs)
- Artifacts:
  - `logs/live_stack/stack-20260901T103159Z-8f44a047/competition_course_v2/probe_A.json`
  - `logs/live_stack/stack-20260901T103159Z-8f44a047/competition_course_v2/probe_B.json`
  - `logs/live_stack/stack-20260901T103159Z-8f44a047/competition_course_v2/load_receipt.json`
  - `logs/live_stack/stack-20260901T103159Z-8f44a047/competition_course_v2/transition_receipt.json`
  - `logs/live_stack/stack-20260901T103159Z-8f44a047/map_acceptance/{overview_god_view,entrance_uav1_view,obstacle_pendulum_view}.png`
- Visual acceptance: user confirmed (`尺寸均正常`)

## Fresh run #2

- Stack: `stack-20260901T104544Z-833460ff`
- Simulation instance: `px4-fb04034ec43fccc0`
- `COURSE_READY=true` with the same world-state retention detail
- Probe A: **PASS**, 40/40 observed, missing `[]`, errors `[]`
  - pendulum dimensions `[0.25, 0.2, 0.7]` m
  - pendulum Y motion range `0.8195` m, Z `0.1607` m, samples 63
- Probe B: **PASS**, 40/40 observed, missing `[]`, errors `[]`
  - pendulum Y motion range `1.0782` m, Z `0.1607` m, samples 63
- Motion controller: PID `10756` registered at creation, scale
  `[0.25, 0.2, 0.2333]`, 400 recorded samples
- Load receipt: stack/instance scoped, `selected_course_destroy=false`,
  `static_passes=2`
- Transition receipt: destroyed only `predicted_narrow_course` (34 IDs),
  preserved `competition_course_v2` (40 IDs)
- Artifacts:
  - `logs/live_stack/stack-20260901T104544Z-833460ff/competition_course_v2/probe_A.json`
  - `logs/live_stack/stack-20260901T104544Z-833460ff/competition_course_v2/probe_B.json`
  - `logs/live_stack/stack-20260901T104544Z-833460ff/competition_course_v2/load_receipt.json`
  - `logs/live_stack/stack-20260901T104544Z-833460ff/competition_course_v2/transition_receipt.json`
  - `logs/live_stack/stack-20260901T104544Z-833460ff/map_acceptance/{overview_god_view,entrance_uav1_view,obstacle_pendulum_view}.png`
- Visual acceptance: user confirmed (`效果不错，可以结束地图开发了`)

## Runtime contract evidence (both runs)

- Selected V2 course is never destroyed by transition; cleanup only destroys
  inactive predicted IDs.
- Normal load is an idempotent upsert (`sendUE4PosScale` create/update) with two
  static passes; `load_receipt.json` lives under
  `logs/live_stack/<stack_id>/competition_course_v2/` and binds `stack_id`,
  `simulation_instance_id`, `spec_sha256`, `created_at`.
- Cross-instance receipts never drive destroy/create.
- Pendulum is created at `pendulum_pose(t=0)`; every motion update keeps the
  spec-derived SDK Scale; retention probes verify dimensions and motion.
- `COURSE_READY=true` only after world-state retention probes A and B PASS.
- Live stack ownership inspection for both runs: `fail_closed=false`,
  `unknown_suspicious=0`, no unknown port owners.

## Additional fixes landed during closure

- `7bb5d38 fix(map): separate dynamic motion from static retention checks` —
  generic retention no longer pins the moving pendulum to its t=0 centre;
  dynamic acceptance is owned by `evaluate_dynamic()` (dimensions, sample count,
  motion range, sweep envelope).
- `354d5a6 fix(map): repair v2 start batch block parsing` — unescaped
  parentheses in dry-run echo lines broke cmd's multi-line block parsing and
  made the live start batch exit 0 without launching the stack.
- `10fe558 chore(map): add map acceptance view and capture helpers` — background
  launcher and RflySim3D `HighResShot` view/capture helpers used for evidence.

## Boundary

This closes the **map milestone only**. No EGO, mission, OFFBOARD, arm or
Navigation was started in either fresh run. The next stage is Competition Course
V2 Navigation Baseline, resuming from current-instance no-arm → short smoke →
Section A, and it must not be described as started until then.
