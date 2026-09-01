# Competition Course V2 Section A — Live Lifecycle Blocker (2026-09-01)

## Result

`BLOCKED_AT_LIVE_LIFECYCLE_GATE`

Implementation update: `RECOVERY_DRYRUN_READY / RETIREMENT_EXECUTION_PENDING`.
This evidence is intentionally not marked RESOLVED until the authorized
metadata transaction succeeds and ordinary inspect returns clean.

The V2 Section A implementation and offline regressions are ready, but no
current-instance no-arm or armed flight was started after the host reboot.

## Read-only evidence

`powershell -ExecutionPolicy Bypass -File sim.ps1 status` inspected the current
manifest `stack-20260831T173615Z-6d6e09b6` and reported:

- `owned_and_alive=0`
- `owned_but_exited=25`
- `stale_pid_reuse=1`
- `unknown_suspicious=0`
- `ports_occupied_by_unknown=0`
- ROS master, both MAVROS connections, and course readiness are false
- UDP 14600/14601/14610/14611 and TCP 11311 are free

The stale entry is the manifest-owned RflySim3D PID `20072`, created at
`2026-08-31T17:36:17Z`. A read-only CIM query shows PID `20072` is now
`C:\Windows\System32\svchost.exe -k GraphicsPerfSvcGroup -s GraphicsPerfSvc`,
created at `2026-09-01 16:20:33`. This is PID reuse, not an owned RflySim
process, and it must not be terminated.

`scripts\live_stack_fresh_instance.ps1 -DryRun` repeated the inspect and exited
fail closed before stop/start. It touched no process and changed no scheduled
task. `scripts\live_stack_start.ps1 -Course competition_course_v2 -DryRun`
successfully described a hypothetical new V2 stack, but it was not executed.

## Offline state

The following remained PASS after the final handoff/evidence hardening:

- `scripts\validate_competition_course_v2_navigation.ps1`
- `scripts\validate_stage7.ps1`
- `scripts\validate_stage8.ps1`
- `scripts\validate_competition_course_v2.ps1`

The final targeted code review found no remaining high-confidence defect in
setpoint-source handoff, strict disarm confirmation, planner-goal correlation,
or run-scoped executor ownership.

## Required safe next action

Resolve or explicitly retire the stale *manifest context* through the protected
lifecycle procedure. Do not kill PID `20072`, do not run a name-based cleanup,
and do not bypass inspect. After inspect returns clean, generate a new V2 stack
with `-Course competition_course_v2`, inspect its actual PID/PGID ownership, and
then resume at the no-arm gate.

## Explicit recovery implementation

The repository now provides `scripts\live_stack_retire_stale.ps1`, backed by
`scripts\lifecycle\stack_retire_stale.py`. Default execution is DryRun. A real
transaction requires `-Execute -PlanToken <exact-dry-run-token>` and performs a
second complete snapshot immediately before the atomic manifest update.

The admission contract denies retirement if any owned process, WSL PGID/orphan,
unknown suspicious process, required-port activity, ROS/MAVROS/course activity,
or probe ambiguity exists. The operation has no stop backend and records
`signal_sent=false` for each archived ownership entry.

The real DryRun for this manifest reports `eligible=true`, 0 owned-alive, 0
owned-orphan, 0 unknown suspicious, all five required ports free, and all ROS
activity false. For PID `20072`, it records RflySim3D fingerprint
`a59267ae8330c287` versus observed `svchost.exe` fingerprint
`9db7da97ed447310`; planned process signals are `NONE`. No manifest mutation has
yet been authorized or executed.
