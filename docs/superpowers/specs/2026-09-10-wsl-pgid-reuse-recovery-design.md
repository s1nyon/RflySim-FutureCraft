# WSL PGID Reuse Recovery Design

Date: 2026-09-10
Status: APPROVED DESIGN — implementation pending

## Problem

An unfinished stack manifest records a WSL process with PID and PGID 737 from
2026-09-09. After WSL restarted, an unrelated VS Code shell created on
2026-09-10 reused both numbers. Its start time and command line do not match the
recorded sensor bridge.

The current lifecycle implementation checks whether any process occupies the
recorded PGID before giving the mismatched leader identity precedence. It
therefore classifies the unrelated group as `owned_orphan`. Stale retirement
then fails closed, and stop DryRun misleadingly lists PGID signals even though
Execute's member-level identity verification would not signal the foreign
process. The manifest cannot reach clean closure through the supported flow.

This is a recovery-path classification defect. It does not invalidate normal
live starts or clean stops, and it is separate from the EGO/PX4 flight chain.

## Selected Design

Give a present leader's identity result precedence over PGID membership:

1. If the recorded PID exists and PID + start time + command line match, classify
   it as `owned_and_alive`.
2. If the recorded PID exists but identity does not match, classify it as
   `stale_pid_reuse`, even when a process group with the same numeric PGID exists.
3. Only when the recorded PID is absent and the recorded PGID still has members
   classify the entry as `owned_orphan`.
4. If neither PID nor PGID exists, classify it as `owned_but_exited`.

This ordering matches process-group semantics: a newly created group normally
uses its leader PID as its PGID. A present, mismatched process at that leader PID
is positive evidence of numeric identity reuse. A genuine orphan is the case in
which the original leader is absent while surviving members retain its PGID.

Apply the same ordering to inspect, stop planning/execution admission, and
metadata-only stale retirement so all three public lifecycle operations agree.

## Scope

Modify only:

- `scripts/lifecycle/stack_inspect.py`
- `scripts/lifecycle/stack_stop.py`
- `scripts/lifecycle/stack_retire_stale.py`
- their focused lifecycle tests
- lifecycle/current evidence documentation required to record the confirmed fix

Do not change manifest schema, process registration, launcher behavior, stop
signal order, health gates, simulation startup, C++ mission, EGO, Faster-LIO,
MAVROS, PX4, or arming policy.

## Safety Behavior

- A mismatched PID/PGID occupant is never granted ownership.
- Stop DryRun reports refusal and plans no signal for that entry.
- Stop Execute retains its final identity re-verification and does not signal the
  foreign process.
- Stale retirement remains metadata-only and records `signal_sent=false`.
- A true orphan group remains stoppable only through manifest ownership and the
  existing member-verification rules.
- Unknown or suspicious processes, occupied required ports, ROS activity, and
  snapshot ambiguity continue to fail closed.

## Testing

Use test-driven development. Add a foreign WSL process whose PID and PGID equal
the recorded leader but whose start time and command line differ.

Required assertions:

1. Inspect reports one `stale_pid_reuse`, zero `owned_orphan`, and fail-closed.
2. Stop DryRun reports identity refusal and contains no planned signal for the
   reused PGID.
3. Stop Execute sends no backend signal and leaves the foreign process intact.
4. Stale retirement is eligible when all other admission gates are clean,
   executes metadata-only, and leaves the foreign process intact.
5. Existing genuine-orphan behavior remains unchanged.
6. `scripts/validate_lifecycle.ps1`, `scripts/validate_stage7.ps1`, and
   `scripts/validate_stage8.ps1` pass.

After offline validation, run retirement DryRun against
`stack-20260909T073830Z-51e7b3ef`, verify zero planned process signals, execute
with the exact token, complete a zero-action clean stop, and inspect the result.
Only then resume the requested NO-ARM EGO live validation.

## Rollback

Revert this design's lifecycle, test, and documentation commit. The existing
fail-closed behavior will return; no manifest schema or external runtime asset
requires migration.
