# Infrastructure Baseline

Updated: 2026-09-01

Competition Course V2 reached its independent no-arm map baseline on 2026-09-01.
That acceptance did not modify or reopen lifecycle, RViz, PX4/MAVROS ownership,
or the protected `predicted_narrow_course` default. See
[`competition-map-v2.md`](competition-map-v2.md).

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

Raw LiDAR remains available but is disabled by default, and each RViz render loop is
limited to 10 Hz. Enable a single LiDAR display manually when it is needed. The first
dual-window configuration rendered both point clouds continuously and consumed about
63% + 55% WSL CPU; the bounded configuration used about 21% + 19% during flight and
did not subscribe RViz to either `/uavX/rflysim/lidar` topic.

Dual RViz is **LIVE-VERIFIED**. Both processes and adapters remained online throughout
the accepted 82 s route. Path headers were `uav1_camera_init` and `uav2_camera_init`;
the run completed with zero collision, OFFBOARD-loss, and timeout events. Standard
stop then terminated the registered `wsl:rviz_session` and finished with zero owned
orphan, unknown, stale, or occupied-port findings. See
[`2026-08-25-infrastructure-recovery-closure.md`](../evidence/2026-08-25-infrastructure-recovery-closure.md).

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

Two valid pre-change samples were 198.6 s and 134.1 s (mean 166.4 s); the third attempted
sample ended in a host crash and is excluded. Three accepted RViz-OFF startup samples
after the launcher/readiness changes were 125.3 s, 123.2 s, and 123.4 s (mean 124.0 s):
42.4 s / 25.5% lower than the two-sample before mean. Stable fail-closed behavior takes
priority over this timing comparison; the retained waits below were not shortened.

## Acceptance

The infrastructure baseline is **READY** at the current branch tip:

- Phase 1 TF/frame contract remains CLOSED; no shared competition frame was introduced.
- startup is 3/3 fresh READY with RViz OFF;
- full existing-route flight is 2/2 fresh PASS (one RViz OFF, one dual RViz ON);
- every accepted stop ended with no owned orphan, unknown process, stale PID, or occupied
  ROS/PX4/MAVROS port;
- the earlier no-lift symptom was not reproduced after clean lifecycle recovery. A later
  heavy-RViz attempt did take off but failed planning under excessive visualization load;
  the default RViz load was reduced and the same RViz-ON route then passed.

The old failures remain historical evidence in
[`2026-08-25-rviz-live-flight-no-lift-and-stop-residual.md`](../incidents/2026-08-25-rviz-live-flight-no-lift-and-stop-residual.md)
and [`2026-08-25-live-startup-bsod-0x1e.md`](../incidents/2026-08-25-live-startup-bsod-0x1e.md),
not current blockers.
