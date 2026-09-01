# Competition Course V2 Section A — Live Lifecycle Blocker (2026-09-01)

## Result

`BLOCKED_AT_LIVE_LIFECYCLE_GATE`

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
