# WSL PGID Reuse Recovery Design

Date: 2026-09-10
Status: IMPLEMENTED AND LIVE VALIDATED (identity precedence);
        EXEC-SESSION MATCHER HARDENED AND OFFLINE VALIDATED (review pass 2)

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

1. If the recorded PID exists and either the exact recorded identity matches or
   a known WSL exec-session identity matches, classify it as
   `owned_and_alive`. The exec-session exception requires the same PID, a start
   time within five seconds, and a role-specific current-argv fragment.
2. If the recorded PID exists but neither identity rule matches, classify it as
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

The role-specific exec exception was added after the first live implementation
correctly rejected the foreign PID 737 but also exposed legitimate in-place argv
transforms used by the frozen FAST-LIO, sensor bridge, MAVROS, and EGO launchers.
It does not weaken the original reuse case: the foreign VS Code shell has both a
different start time and no sensor-bridge argv fragment.

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

## Review Pass 2: Conjunctive Exec-Session Fingerprints

### Finding

The first implementation of the exec-session exception was too wide. Every role
matched on a single generic fragment (`mavros`, `px4-mavlink`, `--copter-id N`,
`tail -f /dev/null`) and the stop path reused the same matcher. A foreign
process that reused a recorded PID/PGID inside the five second window and
happened to carry such a generic token would have been treated as owned and
would have received PID/PGID signals.

### Empirical Basis For The New Rules

Both facts below were measured on this host with throwaway probe processes (no
project process was started, and each probe was killed by explicit PID):

1. `setsid nohup bash -lc '<...>; <cmd>'` and `bash -lic '<...>; <cmd>`
   (with and without a TTY) **exec** the final command in place: the recorded
   PID/PGID keeps running but its live argv becomes only `<cmd>`. The recorded
   MAVROS launcher therefore shows up as the `roslaunch` argv, and the SITL
   wrapper session shows up as only `tail -f /dev/null`.
2. `RFLY_STACK_ID` exported by the SITL wrapper (`generate_sitl_wrapper.ps1`)
   survives that exec and is readable from `/proc/<pid>/environ` by
   `scripts/wsl/live_stack_wsl_ops.sh marker <pid> <stack_id>`, which returns 0
   only for the exact stack id (verified with a probe marker and a wrong-id
   control).

### Implemented Rules

`scripts/lifecycle/stack_inspect.py` now stores one `WslSessionFingerprint` per
role. A match requires **all** of:

1. `ownership.granted == "at_creation"` (spawn-attested entries keep their own
   marker plus recorded-identity path and never inherit this exception);
2. the recorded PID is still alive at exactly that number;
3. the start time is inside the five second window;
4. every role-specific argv regex matches the whitespace-normalized,
   lowercased live argv:

   | role | required argv evidence (all must match) |
   | --- | --- |
   | `wsl:mavros_uav1/2` | `rflysim_mavros_px4.launch` + `uav_namespace:=uav1/2` |
   | `wsl:px4_mavlink_uav1/2` | `px4-mavlink` + `--instance 1/2` |
   | `wsl:sensor_bridge_uav1/2` | `rflysim_sensor_bridge.py` + `--copter-id 1/2` |
   | `wsl:stage2_launcher`, `wsl:fastlio_session` | launcher script name + `scripts/wsl/` |
   | `wsl:roscore` | `roscore` + `/opt/ros/noetic/` |
   | `wsl:fastlio`, `wsl:ego_swarm_session`, `wsl:rviz_session` | `roslaunch` + the specific launch file |
   | `wsl:px4_build_session` | keepalive argv **plus** requirement 5 |

5. marker-backed roles additionally require the launcher-inherited
   `RFLY_STACK_ID` marker to equal this manifest's `stack_id`, read through
   `scripts/wsl/live_stack_wsl_ops.sh marker`. The SITL wrapper session is the
   only such role, because its exec'd argv is the generic keepalive command and
   no argv-only rule can ever be specific for it.

All three public operations use the same rule:
`stack_inspect.inspect_stack`, `stack_stop.plan_stop/execute_stop` (leader and
per-member verification), and `stack_retire_stale.build_retirement_plan`. A
missing/ambiguous marker probe fail-closes: the entry becomes `stale_pid_reuse`
(inspect), is refused with no planned signal (stop), or is retired
metadata-only with `signal_sent=false` (stale retirement).

### Coverage

`tests/lifecycle_inspect_check.py` adds conjunction counterexamples (UAV1 entry
with UAV2 argv, a foreign `mavros_node` argv, a foreign script with
`--copter-id 1`, swapped `--instance`, spawn-attested entry with a perfect
argv, out-of-window start time) plus positive cases for every launcher exec
shape. `tests/lifecycle_stop_check.py` adds the marker-denied build session
(DryRun plans nothing, Execute reaches no backend, clean=false) and the MAVROS
UAV1/UAV2 swap (no signal). `tests/lifecycle_retire_stale_check.py` adds the
marker-owned (never retired) and marker-unverifiable (metadata-only, keepalive
survives) build-session cases.

### Live Status

Offline only. `scripts/validate_lifecycle.ps1`, `scripts/validate_stage7.ps1`
and `scripts/validate_stage8.ps1` pass on this change. The hardened matcher has
not yet been exercised against a running stack; the next authorized no-arm
live run must confirm that every registered role still classifies as
`owned_and_alive` (and that no role fail-closes) before this patch is treated
as live-validated.
