# Infrastructure Baseline

Updated: 2026-08-25

## Project RViz

The project RViz is optional and remains outside READY, health, control, and stop semantics.
The protected live path still starts with RViz disabled.

From a healthy, owned stack with VcXsrv display `127.0.0.1:0.0` available,
pass the current lifecycle identity explicitly:

```bat
scripts\run_rflysim_rviz.bat uav1 --stack-id STACK_ID --manifest STACK_MANIFEST
scripts\run_rflysim_rviz.bat uav2 --stack-id STACK_ID --manifest STACK_MANIFEST
scripts\run_rflysim_rviz.bat dual --stack-id STACK_ID --manifest STACK_MANIFEST
```

`uav1` uses fixed frame `uav1_camera_init`; `uav2` uses
`uav2_camera_init`. `dual` starts two independent RViz processes. It does not add a
shared transform or establish `competition_world`.

Each view contains TF, Faster-LIO relayed odometry, a bounded local path, raw adapted
LiDAR in `uavX_lidar`, and visualization-only EGO trajectory/goal/PositionCommand
markers. The adapter relabels marker/command values into that UAV's verified local
frame without changing numeric values or stamps. It does not publish TF or control
topics and does not copy registered high-bandwidth point clouds. Ground-truth display
is not included because no reliable project GT topic/frame contract has been verified.

The two RViz processes and visualization adapters were observed live. Their nodes,
per-UAV path headers and manifest role `wsl:rviz_session` were verified with
`unknown_suspicious=0`; raw odometry remained approximately 9–12 Hz during the bounded
observation. Visual orientation and full RViz ON flight performance remain unaccepted.
The attempted flight reached dual OFFBOARD/armed state but produced no observed takeoff,
and standard stop left the registered RViz PGID alive. See
[`2026-08-25-rviz-live-flight-no-lift-and-stop-residual.md`](../incidents/2026-08-25-rviz-live-flight-no-lift-and-stop-residual.md).

## Startup progression

The startup path has these relevant waits:

| Wait | Current purpose | Current decision |
| --- | --- | --- |
| `STAGE2_BOOT_WAIT_SECONDS=30` | Preserve PX4/SITL boot before Stage 2 starts | **RETAINED**: a live attempt proved that a stale WSL socket can satisfy the existing socket predicate before the newly owned PX4 instance is ready |
| `PREDICTED_COURSE_SCENE_WAIT_SECONDS=10` | Additional delay before sending the dynamic course load | **RETAINED**: no independent UE scene-load acknowledgement exists |
| ROS master wait | `rostopic list` succeeds | Predicate-driven, bounded, fail-closed |
| PX4 instance wait | `/tmp/px4-sock-1` and `/tmp/px4-sock-2` exist as sockets | Predicate-driven, bounded, fail-closed |
| MAVROS wait | both `/uavX/mavros/state` report `connected: True` | Predicate-driven, bounded, fail-closed |
| health wait | run-scoped GUI/ROS/MAVROS/course status plus topology | Predicate-driven, bounded, fail-closed |
| sensor/Faster-LIO/EGO waits | real messages, publishers/subscribers and registered roles | Predicate-driven, bounded, fail-closed |

Two clean RViz-OFF pre-change startup samples completed before the crash (198.6 s and
134.1 s wall time). The required third sample blue-screened the Windows host and is not
a valid timing result. No after-timing claim is accepted.

## Active live blockers

Further live startup, RViz, and flight regression are **BLOCKED** by
[`2026-08-25-live-startup-bsod-0x1e.md`](../incidents/2026-08-25-live-startup-bsod-0x1e.md).
Offline validation does not close this blocker. Infrastructure baseline readiness must
remain unclaimed until dump analysis and the required fresh live ladder complete.

Additionally, stack `stack-20260825T081042Z-756ce781` ended with all core ports free and
`owned_and_alive=0`, but manifest `stop.clean=false` because RViz PGID `9329` remained as
an owned orphan. No fresh start is allowed from this state. The same run's flight evidence
confirmed dual OFFBOARD/arming but no physical takeoff; this is not a passed regression and
does not justify changing coordinate or mission mathematics.
