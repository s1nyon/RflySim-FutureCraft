# Competition Course V2 Section A — Live Lifecycle Blocker (2026-09-01)

## Result

`RESOLVED`

Resolution: `STALE OWNERSHIP METADATA RETIRED / POST-INSPECT CLEAN / FRESH DRYRUN PASS`.

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

## Resolution evidence

The user authorized only the metadata retirement for
`stack-20260831T173615Z-6d6e09b6`. The first Execute attempt aborted atomically
with `state changed after admission; manifest unchanged`. Read-only comparison
showed the changing occupant was the WSL snapshot command itself: its ephemeral
`ps -eo pid=,ppid=,pgid=,lstart=,args=` process reused historical WSL PID `374`
between admission snapshots. The parser now excludes only that exact observer
command; a focused test reproduces the observer snapshot condition, and full
`validate_lifecycle.ps1` remains PASS.

The same authorized plan token
`34ae397fd8a96e657ed161c1b6b68ec9ebc05b3d712098f285f293b2419cfa83`
then committed the metadata-only transaction. At commit time PID `20072` was
absent, so its audit record says `recorded_pid_absent`; the earlier svchost PID
reuse remains preserved above as historical admission evidence. The operation:

- retired 26 dead ownership entries into `stop.retired_stale_ownership`;
- recorded `signal_sent=false` for every entry and for the transaction summary;
- invoked no Windows/WSL stop backend and sent no process signal;
- did not start a stack, enter OFFBOARD, arm, or fly.

Post-transaction ordinary inspect reported:

- `fail_closed=false`
- `owned_and_alive=0`, `owned_but_exited=0`, `owned_orphan=0`
- `stale_pid_reuse=0`, `orphans=0`, `unknown_suspicious=0`
- `ports_occupied_by_unknown=0`; UDP 14600/14601/14610/14611 and TCP 11311 free

`scripts\live_stack_fresh_instance.ps1 -DryRun` then exited 0 with the same
clean summary and explicitly reported that no process or scheduled task was
touched. The lifecycle stale ownership blocker is therefore resolved.

## Explicit recovery implementation

The repository now provides `scripts\live_stack_retire_stale.ps1`, backed by
`scripts\lifecycle\stack_retire_stale.py`. Default execution is DryRun. A real
transaction requires `-Execute -PlanToken <exact-dry-run-token>` and performs a
second complete snapshot immediately before the atomic manifest update.

The admission contract denies retirement if any owned process, WSL PGID/orphan,
unknown suspicious process, required-port activity, ROS/MAVROS/course activity,
or probe ambiguity exists. The operation has no stop backend and records
`signal_sent=false` for each archived ownership entry.

The pre-execution DryRun reported `eligible=true`, 0 owned-alive, 0
owned-orphan, 0 unknown suspicious, all five required ports free, and all ROS
activity false. For PID `20072`, the historical DryRun recorded RflySim3D
fingerprint `a59267ae8330c287` versus observed `svchost.exe` fingerprint
`9db7da97ed447310`; planned process signals were `NONE`.

## Next protected gate

Generate a fresh V2 stack with `-Course competition_course_v2`, inspect its
actual PID/PGID ownership, and resume at the no-arm gate. Stack start,
OFFBOARD, arm, and flight are not authorized by this retirement transaction
and require their own Red-Zone presentation and explicit approval.
