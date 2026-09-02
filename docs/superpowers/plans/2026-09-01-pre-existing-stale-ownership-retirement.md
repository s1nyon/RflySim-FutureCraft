# Pre-existing Stale Ownership Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, DryRun-first, metadata-only recovery operation for a manifest whose stack is proven dead but whose recorded PID has been recycled by an unrelated process.

**Architecture:** A new lifecycle module captures one immutable Windows/WSL/process-port-ROS snapshot, derives a deterministic retirement plan and token, and never accepts a stop backend. Execute requires the DryRun token, recaptures the full snapshot twice, aborts on any mismatch, and only then moves dead/stale ownership entries into auditable manifest retirement metadata. Existing inspect, stop, and fresh-instance behavior remains unchanged.

**Tech Stack:** Python 3.8, PowerShell, existing lifecycle manifest/inspect/process-table modules, standalone contract tests.

## Global Constraints

- No process signal, close-window operation, task deletion, stack start, OFFBOARD, or arm action is permitted.
- Ordinary inspect/stop/fresh-instance retains fail-closed behavior for stale PID reuse.
- Retirement requires zero owned-live processes, zero owned WSL orphan/PGID members, zero unknown suspicious processes, all required ports proven free, and ROS/MAVROS/course proven inactive.
- Execute requires the exact DryRun plan token and must recapture state immediately before manifest mutation.
- Navigation, map, EGO, Faster-LIO, mission, and PBL-1 files remain unchanged.

---

### Task 1: Focused retirement contract

**Files:**
- Create: `tests/lifecycle_retire_stale_check.py`
- Modify: `scripts/validate_lifecycle.ps1`

**Interfaces:**
- Consumes: existing `new_manifest`, `register_process`, `inspect_stack`, and fake process-table contracts.
- Produces: executable expectations for `build_retirement_plan(...)` and `execute_retirement(...)`.

- [ ] Write tests A-I for exact-live denial, recycled Windows PID success with foreign survivor, absent PID retirement, other owned-live denial, WSL orphan denial, unknown denial, occupied-port denial, TOCTOU abort without manifest mutation, and clean post-retirement inspect.
- [ ] Assert the production source contains no stop backend, taskkill, Stop-Process, process-close, or WSL signal operation.
- [ ] Run the focused test and confirm it fails because the retirement module is absent.

### Task 2: Metadata-only retirement core and public entry

**Files:**
- Create: `scripts/lifecycle/stack_retire_stale.py`
- Create: `scripts/live_stack_retire_stale.ps1`
- Modify: `scripts/README.md`

**Interfaces:**
- `build_retirement_plan(manifest, win_table, wsl_table, ports_probe, ros_probe) -> RetirementPlan`
- `execute_retirement(manifest, ..., expected_plan_token, before_commit=None) -> RetirementPlan`
- DryRun prints a deterministic `plan_token`; Execute requires `-PlanToken`.

- [ ] Capture one immutable process snapshot and derive admission plus complete recorded/observed identity evidence.
- [ ] Deny every ambiguous or active-stack state and expose `planned_process_signals: []`.
- [ ] On Execute, compare the DryRun token, recapture immediately before mutation, compare again, then archive detailed provenance under `stop.retired_stale_ownership` and remove only the proved-dead/stale ownership entries.
- [ ] Keep the wrapper default DryRun and require `-Execute -PlanToken <token>` for mutation.
- [ ] Run the focused test until all A-I cases pass.

### Task 3: Documentation, regression, and real DryRun

**Files:**
- Modify: `docs/architecture/2026-08-08-live-stack-lifecycle-design.md`
- Modify: `docs/current/competition-roadmap.md`
- Modify: `docs/evidence/2026-09-01-v2-section-a-live-lifecycle-blocker.md`

- [ ] Document the explicit recovery entry without weakening default inspect/stop/fresh semantics.
- [ ] Run lifecycle, V2 navigation/map, Stage 7, and Stage 8 validators.
- [ ] Run retirement DryRun against `stack-20260831T173615Z-6d6e09b6` and verify PID 20072/svchost is metadata-only with zero signals.
- [ ] Commit and push the offline implementation, then stop for narrowly scoped retirement Execute authorization.
