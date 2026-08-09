# Future Aircraft Sim Project Structure Optimization Design

**Date:** 2026-08-10

**Status:** Approved design; implementation not started

**Scope:** Repository organization, ROS workspace ownership, external dependency management, runtime cleanup, and a unified simulation command

**Protected baseline:** PBL-1 and the live-stack lifecycle validated on 2026-08-08

## 1. Objective

Restructure `future_aircraft_sim` so that:

- the existing live simulation lifecycle remains stable and auditable;
- the user has a clear ROS package for new competition-task development;
- Agents have clear ownership of simulator startup, maps, adapters, diagnostics, and maintenance;
- third-party algorithms are versioned and reproducible;
- obsolete scaffolding and runtime debris no longer mislead developers or Agents;
- simulation startup, inspection, shutdown, build, validation, and log maintenance have one discoverable entry point.

This is a boundary and tooling cleanup, not an algorithm rewrite.

## 2. Hard Constraints

1. Do not modify the behavior of the existing Python files in `multi_uav_mission`.
2. Do not delete or relocate scripts that directly participate in the current live chain unless compatibility and regression evidence prove the replacement.
3. Preserve both `.vscode` configurations and place them under version control.
4. Preserve all current uncommitted user C++ work.
5. Preserve all 21 current local modifications to `ego-planner-swarm` before moving, recloning, or cleaning that checkout.
6. Keep lifecycle fail-closed semantics. No name-based process killing, WSL-wide shutdown, automatic force retry, or implicit arming may be introduced.
7. Do not move `logs/` or `generated/` to a different runtime path during this restructuring because the validated live chain contains many direct references to those locations.
8. Do not run a full simulation flight automatically as part of the restructuring.

## 3. Target Repository Structure

```text
future_aircraft_sim/
├── AGENTS.md
├── README.md
├── sim.ps1
├── config/
├── future_aircraft_ws/
│   └── src/
│       ├── multi_uav_mission/
│       └── future_aircraft_mission/
├── third_party/
│   └── ego-planner-swarm/
├── scripts/
│   ├── lifecycle/
│   ├── wsl/
│   └── README.md
├── tests/
├── docs/
│   ├── architecture/
│   ├── current/
│   ├── decisions/
│   ├── evidence/
│   ├── incidents/
│   ├── reference/
│   └── superpowers/
├── logs/
├── generated/
├── .vscode/
└── .worktrees/
```

`logs/`, `generated/`, build products, caches, and worktrees remain ignored runtime state. The directory tree describes ownership and purpose; it does not authorize moving protected live files merely for visual consistency.

## 4. ROS Workspace Design

### 4.1 `multi_uav_mission`

`multi_uav_mission` remains the protected, live-validated baseline package. Its existing Python scripts and launch behavior remain in place. This task must not refactor, split, rename, or behaviorally edit those Python components.

### 4.2 `future_aircraft_mission`

A new Catkin package, `future_aircraft_mission`, becomes the primary location for user-authored and AI-assisted competition-task code. The current uncommitted C++ `ego_setpoint_bridge` sources and their build dependencies move into this package without semantic rewriting.

The corresponding uncommitted CMake and package-manifest changes are transferred out of `multi_uav_mission`, returning that package's build metadata to its protected baseline.

### 4.3 Deferred packages

The following package boundaries are reserved but are not created as empty scaffolds:

- `rflysim_support`: future simulator-only ROS adapters;
- `future_aircraft_bringup`: future launch and parameter composition shared by simulation and hardware profiles;
- `future_aircraft_interfaces`: future custom messages or services, only when a real cross-package interface requires them.

Creating these packages is triggered by a concrete feature, not by this cleanup alone.

### 4.4 Ownership

- User-owned by default: `future_aircraft_mission` competition behavior and control logic.
- Agent-owned by default: simulation orchestration, maps, simulator adapters, diagnostics, maintenance scripts, and their tests.
- Change-gated shared boundary: ROS interfaces, launch composition, package manifests, and any file that can affect PBL-1.
- Frozen unless regression evidence exists: lifecycle internals and the current Python baseline.

The ownership boundary is documented in `AGENTS.md` and the concise Agent entry guide.

## 5. Third-Party Dependency Design

### 5.1 Placement

`ego-planner-swarm` remains a separate Catkin overlay and moves from ignored `external/ego-planner-swarm` to:

```text
third_party/ego-planner-swarm
```

It is not placed inside `future_aircraft_ws/src` because it is an independently built upstream workspace with its own messages and dependency graph.

### 5.2 Version control

The selected model is a team fork referenced as a Git submodule at an exact commit. The expected build overlay remains:

```text
ROS Noetic
→ third_party/ego-planner-swarm/devel
→ future_aircraft_ws
```

### 5.3 Loss-prevention sequence

Before changing the current checkout:

1. record its upstream commit, status, remotes, and full diff;
2. export the 21-file compatibility patch and checksums to a safe location in the main repository;
3. create a dedicated compatibility branch in the EGO repository;
4. commit the compatibility changes locally;
5. push that commit to the team fork only after explicit push authorization;
6. add the fork as `third_party/ego-planner-swarm` submodule and pin the commit;
7. update active code, configuration, tests, and documentation references;
8. rebuild and validate the new location;
9. remove the old checkout only after all earlier steps pass.

If the fork or push authorization is unavailable, implementation stops after the patch is safely exported. A parent repository must not record a submodule commit that other clones cannot fetch.

## 6. Unified Simulation Command

The repository root gains a thin PowerShell entry point:

```powershell
.\sim.ps1 <command> [options]
```

It delegates to validated scripts and must not duplicate lifecycle ownership or stop logic.

### 6.1 Commands

```powershell
.\sim.ps1 start
.\sim.ps1 start -Execute
.\sim.ps1 start -Profile base -Execute
.\sim.ps1 status
.\sim.ps1 stop
.\sim.ps1 stop -Execute
.\sim.ps1 build
.\sim.ps1 validate -Suite core
.\sim.ps1 doctor
.\sim.ps1 clean-logs
.\sim.ps1 clean-logs -Execute
```

### 6.2 Startup profiles

- `base`: map generation/loading, RflySim3D, two CopterSim instances, PX4, ROS master, and two MAVROS namespaces.
- `dev` (default): `base`, dual sensor bridge, Faster-LIO readiness, and EGO-Swarm. It stops before mission execution, OFFBOARD, or arming.

No automatic flight profile is added. Simulation flight continues to use the explicit protected command with `--allow-arm --simulation-only` and current-instance readiness gates.

### 6.3 Command safety

- State-changing `start`, `stop`, and `clean-logs` default to DryRun and require `-Execute`.
- `status` is read-only.
- The wrapper identifies the active manifest. Multiple active stacks, unknown ownership, stale identity, or port ambiguity cause a fail-closed error.
- The wrapper never performs name-based cleanup, WSL distribution shutdown, implicit fresh retry, or forced fallback.
- `stop -Execute` delegates to `end_live_stack.ps1` for Stage 7 cleanup, manifest stop, and final clean verification.
- `clean-logs` never touches an active stack or curated evidence.

### 6.4 Validation suites

- `mission`: focused build/tests for `future_aircraft_mission`.
- `core`: Stage 6C, 6D, 7, and 8.
- `lifecycle`: the lifecycle validator.
- `all`: every retained focused validator.

Both VS Code task sets expose equivalent commands while continuing to support opening either the repository root or `future_aircraft_ws` as the workspace.

## 7. Cleanup Policy

### 7.1 Delete

- runtime contents under `logs/` after evidence curation;
- all `__pycache__/` directories and `.pyc` files;
- the clean, merged `.worktrees/stage6d-odometry-stream` through `git worktree remove`, followed by its merged local branch;
- ignored `.superpowers/sdd/` scratch reports;
- `future_aircraft_ws/src/.gitkeep`;
- `scripts/patch_stage4_cmake.ps1`;
- `scripts/kill_all.bat`;
- `scripts/record_logs.bat`;
- `scripts/validate_stage0.ps1`;
- the superseded `docs/prompts/2026-08-03-continue-stage8-static-map.md`.

These tracked files remain recoverable from Git history.

### 7.2 Preserve

- all lifecycle implementation and public wrappers;
- all WSL scripts used by the current live chain;
- all Stage 7/8 live and diagnostic entries;
- `cleanup_sim_stack.ps1` and `restart_live_stack.ps1` as fail-fast safety tombstones;
- lifecycle, Stage 6C/6D/7/8 validators;
- the Stage 3→5→6 validation dependency chain;
- Stage 1, Stage 2/2.1, and Stage 4 focused diagnostic validators;
- all current Python tests and fixtures;
- both `.vscode` configurations;
- `future_aircraft_ws/.catkin_workspace` and the Catkin top-level `src/CMakeLists.txt`;
- `generated/`, including terrain backup and map-deployment products.

No validator is deleted solely because its stage number is old. Call relationships and diagnostic value determine retention.

### 7.3 Evidence curation

Before clearing raw logs, copy the following small artifacts from each of the three accepted PBL-1 runs into `docs/evidence/pbl1/<run-id>/` after checking for secrets and machine-specific data:

- `sensor_readiness.json`
- `flight_report.json`
- `score_summary.json`
- `provenance.json`
- `executor_trace.json`
- `mission_events.jsonl`
- `slam_ego_swarm_smoke_report.json`

Do not retain the large Faster-LIO, EGO, or watchdog raw logs in Git.

## 8. Documentation Design

- `README.md`: project purpose, current stable capability, quick start, and links only; it must not remain a chronological incident log.
- `AGENTS.md`: hard safety rules, protected baseline, ownership boundaries, and required entry points.
- `.agents/AGENT2READ.md`: concise current truth and task-routing guide.
- `.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md`: retained as the toolchain boundary reference.
- `docs/current/`: current roadmap and active engineering state.
- `docs/architecture/`: lifecycle and repository architecture.
- `docs/evidence/`: compact milestone evidence.
- `docs/incidents/`: resolved failures and reusable diagnostic lessons.
- `docs/decisions/`: accepted engineering decisions.
- `docs/reference/competition-guide-2026.pdf`: the official competition guide, moved from the repository root with references updated.
- `docs/superpowers/`: retained at its conventional location for design and implementation-plan records.

`scripts/README.md` classifies every script as one of:

- public entry;
- protected internal;
- focused diagnostic;
- hazard-disabled;
- historical compatibility.

## 9. Error Handling and Rollback

- Destructive cleanup is always the final phase, never a prerequisite for validation.
- Every move first creates or verifies a recoverable source: Git history, patch file, fork commit, or curated evidence copy.
- Missing submodules produce an actionable `doctor` error; commands do not silently clone or update dependencies.
- A dirty EGO submodule blocks update/replacement operations.
- A failed build or validator leaves the old path and runtime data intact.
- Ambiguous active stack state blocks start/stop selection.
- No cleanup command runs against unresolved paths or an active manifest.
- Each implementation phase is reviewed independently so it can be reverted without rolling back unrelated user work.

## 10. Validation Plan

The minimum validation sequence is:

1. verify root Git status and preserve pre-existing user changes;
2. verify the EGO fork commit is fetchable and the submodule is pinned and clean;
3. build the EGO workspace;
4. build `future_aircraft_mission`;
5. run `sim.ps1 doctor`;
6. run DryRun contracts for `start`, `status`, `stop`, and log cleanup;
7. run `scripts/validate_lifecycle.ps1`;
8. run Stage 6C, 6D, 7, and 8 validators;
9. confirm no active reference to `external/ego-planner-swarm` remains;
10. confirm existing `multi_uav_mission` Python behavior files have no task diff;
11. inspect the final repository diff and submodule state.

Because the dependency path participates in the live overlay, a later no-arm run is recommended before declaring live parity. Full flight is not automatically authorized or required for the repository-structure commit; if not performed, the handoff must state that live parity remains unverified.

## 11. Implementation Order

```text
Preserve user work and EGO patches
→ establish fork and pinned submodule
→ create future_aircraft_mission and transfer C++ work
→ implement sim.ps1 and DryRun tests
→ organize documentation and add script index
→ delete confirmed obsolete scaffolding
→ curate compact PBL-1 evidence
→ clean logs, caches, and merged worktree
→ run the complete offline validation sequence
→ inspect and commit only intended changes
```

Suggested implementation commits keep dependency migration, ROS package boundaries, unified tooling, and documentation/runtime cleanup separate.

## 12. Success Criteria

The restructuring is complete when:

- the existing Python baseline has no behavior change;
- current user C++ work exists in `future_aircraft_mission` and builds to its current intended level;
- EGO is fetched from the team fork as a pinned, reproducible submodule;
- one documented root command covers dry-run startup, status, shutdown, build, validation, diagnostics, and log cleanup;
- live lifecycle safety tests and core offline validators pass;
- obsolete scaffolding, stale caches, raw logs, and the merged worktree are removed;
- current docs no longer mix resolved incidents with active blockers;
- another developer or Agent can identify ownership, build order, public commands, and safety gates without reading historical plans.
