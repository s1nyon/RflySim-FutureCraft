# Infrastructure Recovery and Closure — 2026-08-25

Status: **ACCEPTED / INFRASTRUCTURE BASELINE READY**

## Changes under validation

- `stack_stop.py` recognizes the registered RViz session after its wrapper has
  `exec`-transformed into `roslaunch`; PID/start-time/fingerprint and stack marker checks
  are unchanged.
- Per-UAV RViz remains optional and outside READY/control. Both LiDAR displays are
  available but disabled by default, and RViz frame rate is 10 Hz.
- No TF, mission, setpoint, PX4, MAVROS, Faster-LIO, or EGO algorithm changed.

## RViz orphan root cause and recovery

Old PGID `9329` contained the correctly owned RViz `roslaunch` session and its children.
The registered command fingerprint described `rviz_live.sh`, while the live leader had
become `roslaunch ... rflysim_rviz.launch` after `exec`. The role-specific identity
fragments did not include this legitimate transform, so stop refused to signal it.

A focused test first reproduced this rejection. After adding the RViz launch fragment,
standard stop terminated PGID 9329 and verified all related ports free. The same stop
path subsequently cleaned two additional dual-RViz stacks, including the accepted flight
run, with `owned_orphan=0` and `unknown_suspicious=0`.

## Startup acceptance

| Sample | Stack | Wall READY time | Result |
| --- | --- | ---: | --- |
| 1 | `stack-20260825T092856Z-fa676cc6` | 125.3 s | PASS |
| 2 | `stack-20260825T094439Z-19e19b97` | 123.2 s | PASS |
| 3 | `stack-20260825T100508Z-15c8beaa` | 123.4 s | PASS |

Mean 124.0 s, minimum 123.2 s, maximum 125.3 s. The two valid earlier samples were
198.6 s and 134.1 s (mean 166.4 s), so the observed mean reduction is 42.4 s (25.5%).
The 30 s PX4 boot wait and 10 s scene/load wait remain because neither has a reliable
instance-specific replacement signal; all later gates remain bounded and fail-closed.

## Flight regression

| Run | RViz | Stack / run | Result |
| --- | --- | --- | --- |
| 1 | OFF | `stack-20260825T101041Z-613b1f5c` / `stage7-20260825T101140Z-8668` | PASS |
| 2 | dual ON | `stack-20260825T101757Z-8f42967e` / `stage7-20260825T101855Z-20017` | PASS |

Both runs completed the existing 82 s staggered route. Each confirmed dual OFFBOARD,
arming, takeoff, navigation, landing, and disarm. Each reported collision count 0,
OFFBOARD-loss count 0, timeout count 0, and minimum inter-UAV distance 0.85 m.

The original no-lift symptom did not reproduce after lifecycle cleanup. One intermediate
heavy-RViz run took off (UAV1 0.812 m, UAV2 4.199 m) but EGO produced no second UAV1
trajectory while reporting that the drone/control points were in obstacles. At that time
the two RViz renderers consumed about 63% + 55% CPU. This was not a TF or arming failure.
With LiDAR disabled by default and rendering limited to 10 Hz, CPU fell to about 21% +
19%; RViz had no LiDAR subscription, and the complete route passed.

## Final clean-state proof

The final standard stop recorded the RViz role as `owned_but_exited` and reported:

```text
owned_and_alive=0
owned_orphan=0
unknown_suspicious=0
stale_pid_reuse=0
ports 11311/14600/14601/14610/14611 = free
roscore_alive=false
```

No `pkill`, `killall`, `taskkill`, direct PGID kill, or `wsl --shutdown` was used.
