# Simulation / Competition Course V2 Freeze & C++ Mission Handoff

Date: 2026-09-02
Status: **DOCUMENTATION FREEZE CLOSURE — READY FOR MAIN MERGE (not yet merged)**

This document freezes the simulation/infrastructure/map/navigation-baseline scope
that is ready to support the next development phase: **C++ Competition Mission**.
No new live execution was performed for this documentation closure; all statements
below are derived from the authoritative evidence already in the repository.

## Current Truth

```text
CURRENT PHASE:
Simulation baseline frozen.
Competition Course V2 frozen.
C++ Competition Mission development is next.

FROZEN:
- lifecycle / ownership
- Windows + WSL startup / stop chain
- PX4 SITL x2 / MAVROS x2 integration
- RflySim / CopterSim integration
- sensor (LiDAR / IMU) integration
- Faster-LIO integration
- EGO integration
- setpoint / control handoff baseline
- RViz diagnostic integration
- Competition Course V2 deployment / motion / world-state probes / readiness gate
- validation / evidence tooling

VALIDATED:
- Section A full flight chain: 3/3 independent fresh-instance PASS
  (endpoint reached, collision 0, watchdog/geofence 0, UAV2 violations 0,
  terminal settle / AUTO.LAND / disarm PASS, clean lifecycle closure each run)

KNOWN LIMITATION:
- Section A entrance wall clearance ~0.072 / 0.085 / 0.073 m (Run 1/2/3)
- target stable margin = 0.25 m (clearance_policy.lateral_margin_each_side_m)
- classified as planner / corridor-entry performance backlog, NOT an
  infrastructure / map / lifecycle / perception / control-chain blocker

RESIDUAL RISK (retained, not a current blocker):
- historical first full-Section-A intermittent event
  (~1.5 m/s overspeed, lateral oscillation, negative wall clearance,
  geofence/watchdog) — NOT reproduced in 3 consecutive fresh runs

DO NOT REOPEN INFRA unless:
- confirmed regression
- confirmed runtime bug
- C++ mission exposes a real interface defect
```

`FROZEN` means: no proactive refactor or optimization of these modules. A frozen
module may be reopened only for a confirmed regression, a real runtime bug, or an
interface defect exposed by C++ mission development.

## Frozen Simulation Baseline

Frozen scope (see "FROZEN" above) covers the complete stack used by the accepted
baselines: lifecycle/ownership manifest flow, Windows + WSL startup/stop chain,
PX4 SITL x2, MAVROS x2, RflySim/CopterSim integration, LiDAR/IMU sensor bridge,
Faster-LIO, EGO-Swarm, setpoint/control handoff, RViz diagnostic integration,
Competition Course V2 deployment and motion, world-state probes, `COURSE_READY`
gate, and validation/evidence tooling.

The protected PBL-1 (`predicted_narrow_course` dual-UAV `lidar_only` baseline),
`multi_uav_mission` Python/launch baseline, and lifecycle internals remain frozen
under the existing change-gated rules.

## Competition Course V2 — FROZEN

`competition_course_v2` map is **FROZEN**:

- fresh-startup validation complete (2 independent runs, probes A/B 40/40);
- world-state retention, dynamic pendulum geometry/motion, visual verification done;
- cross-instance receipt / lifecycle issues resolved;
- navigation development must not modify the map to make algorithms pass.

**Do not modify V2 geometry to compensate for navigation/planner deficiencies.**
If an official competition map revision is published later, a separate revision is
allowed based on the official requirement.

## Section A accurate conclusion

From `docs/evidence/2026-09-02-v2-section-a-repeatability-clearance-not-stable.md`:

| Run | stack / sim | flight chain | min wall clearance | collision/watchdog/UAV2 |
| --- | --- | --- | --- | --- |
| 1 | `stack-20260901T185525Z-19bc4644` / `px4-d85f016a6cda2715` | PASS | 0.072 m | 0 / 0 / 0 |
| 2 | `stack-20260902T034825Z-363300e9` / `px4-52b0b10efc975e0d` | PASS | 0.085 m | 0 / 0 / 0 |
| 3 | `stack-20260902T040228Z-33a4e2e7` / `px4-410ff97740b4a932` | PASS | 0.073 m | 0 / 0 / 0 |

Two statements are both true and must remain separated:

```text
SECTION A FLIGHT CAPABILITY REPEATABLE   (3/3 fresh flight-chain PASS)
SECTION A CLEARANCE NOT STABLE          (0/3 above 0.25 m stable margin)
```

The clearance limitation is classified as a
**known planner / corridor-entry performance limitation**. Evidence is consistent
with an initial corridor-entry / planner-goal geometry limitation (spawn → direct
long Section A goal → EGO initial trajectory biased toward the right wall), but the
root cause is not claimed to be absolutely proven.

## Historical intermittent failure (retained)

The first full Section A run exhibited ~1.5 m/s overspeed, large lateral oscillation,
negative wall clearance, and geofence/watchdog events. Status:

```text
Historical intermittent event
NOT reproduced in 3 consecutive independent fresh-instance runs
residual risk = retained
current infrastructure blocker = no
```

If it reappears, reopen RCA on that event only (task brief §17 window −3 s → +3 s).

## RViz position

```text
RViz = optional diagnostic observer
NOT a core READY dependency
```

- uav1 / uav2 / dual modes exist and are verified;
- the protected live path does not force RViz;
- enable it on demand for C++ mission / planner RCA;
- an RViz failure must not invalidate the core flight stack by itself.

## Next phase — C++ Competition Mission

### C++ package foundation and architecture status

`future_aircraft_ws/src/future_aircraft_mission/` is the **existing and intended
C++ competition mission package**; future development continues inside it.

```text
Existing C++ package foundation:  PRESENT (future_aircraft_mission)
Existing EgoSetpointBridge:        PRESENT / KEEP (EGO PositionCommand →
                                   MAVROS/PX4 setpoint handoff baseline module)
Broader Competition Mission
  architecture (VehicleInterface /
  EgoInterface / UavAgent /
  MissionManager):                NOT YET IMPLEMENTED
Next development:                 extend future_aircraft_mission incrementally
```

`EgoSetpointBridge` remains part of the current C++ baseline. It is not a
confirmed blocker and there is no reason to remove it when entering the new C++
phase; it may be reviewed or refactored later only if real mission requirements
or control evidence justify changes. Note that a future `EgoInterface`
(mission → EGO goal/control interface) and the existing `EgoSetpointBridge`
(EGO PositionCommand → MAVROS/PX4 setpoint handoff) can coexist; adding the
former does not make the latter obsolete.

The **broader Competition Mission architecture has not yet been designed or
implemented**. "The user starts from zero" means: the new mission modules will be
designed and implemented incrementally **by the user, inside the existing
`future_aircraft_mission` package** — it does not mean deleting the package,
re-running `catkin_create_pkg`, or rebuilding the project from scratch.

Milestone/architecture sketches below are **conceptual roadmap only**; no
implementation scaffold has been approved or created for this phase.

The next roadmap phase is **C++ Competition Mission Development**, in
`future_aircraft_ws/src/future_aircraft_mission/` (human-owned competition
behavior/control intent).

Initial milestone shape:

```text
VehicleInterface
    ↓
EgoInterface
    ↓
UavAgent
    ↓
MissionManager
    ↓
UAV1 C++ short-smoke baseline
```

First complete C++ capability:

```text
WAIT_READY → TAKEOFF → SEND_EGO_GOAL → WAIT_REACHED → AUTO.LAND → DISARM → FINISHED
```

**Conceptual roadmap only.** No implementation scaffold has been approved or
created for this phase. Future modules are designed incrementally **inside the
existing `future_aircraft_mission` package**; do not generate code from this
sketch without the user, and do not propose replacing the existing package.

Not in scope for the immediate milestone: CorridorCoordinator, TaskAllocator,
dual-UAV complete mission, vision mission.

## C++ architectural boundary (expected, not yet implemented)

```text
MissionManager
     │
     ├── UavAgent UAV1
     └── UavAgent UAV2
              │
              ├── VehicleInterface
              ├── EgoInterface
              ├── PerceptionInterface
              └── SafetyMonitor

CorridorCoordinator
     │
     └── controls high-level permission/order

TaskAllocator
     │
     └── future competition task assignment
```

Principle:

```text
C++ Mission decides WHAT to do.
EGO decides HOW to locally navigate.
```

The mission layer must not reimplement a local trajectory planner.

## Development boundary

- `future_aircraft_ws/src/future_aircraft_mission/` is the main C++ competition
  mission workspace.
- Infrastructure scripts stay as the stable base; do not invade/refactor lifecycle
  for C++ development.
- third-party planner/localization are not to be modified casually.

## AI-assisted C++ development policy

C++ competition mission is primarily written with the user, for C++/ROS/OOP/state
machine/multi-UAV coordination training. Default AI role:

```text
architecture guidance
API reminders
code review
bug diagnosis
test design
small/local code assistance
```

AI should not default to rewriting the whole mission package. Infrastructure /
tooling / validation automation remains agent-assisted.

## C++ Learning / Development Boundary

The user wants to train C++/ROS/OOP/state machine/multi-UAV mission design by
building this project hands-on. Development therefore continues from the
existing `future_aircraft_mission` package, while the **new mission modules are
designed and coded from zero by the user** (not generated by AI wholesale).

AI default role:

```text
architecture guidance
concept explanation
ROS/C++ API reminders
code review
debugging
test design
small/local code assistance
```

AI default does NOT:

```text
create a full mission package skeleton
write all headers/sources
generate the full MissionManager/UavAgent architecture
prebuild CMake/package scaffolding
```

unless the user explicitly asks later.

## Ready to Merge into Main

- source branch: `infra/rviz-live-handoff-20260825`
- merge source: current remote HEAD of `infra/rviz-live-handoff-20260825` at
  merge time (this document does not pin a SHA to avoid staleness)
- workspace: clean (documentation closure did not execute live runs)
- offline regression status: PASS at `f47a048`
  (`validate_competition_course_v2_navigation.ps1`, map, Stage 7/8, lifecycle,
  `git diff --check`)
- latest live repeatability: 3/3 fresh flight-chain PASS; 0/3 stable clearance
- known limitations: Section A entrance clearance; historical intermittent event
  retained as non-reproduced residual risk
- frozen scope: see above
- next phase: C++ Competition Mission

Recommended baseline tag (do not create yet):

```text
sim-v2-baseline-20260902
```

Semantics: frozen simulation + Competition Course V2 baseline immediately before
C++ Competition Mission development.

Recommended branch flow after merge:

```text
main
  ↓
feature/cpp-competition-mission
```

Do not keep long-term C++ development on `infra/rviz-live-handoff-20260825`;
keep one feature branch with logical commits rather than many small
`feature/vehicle-interface` style branches.
