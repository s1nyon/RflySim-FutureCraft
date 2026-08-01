# Stage 2.1 28com Single-UAV Alignment Design

## Purpose

Make the Stage 2.1 live gate usable with the installed RflySim toolchain while retaining the project-facing `/uav1` MAVROS interface. This work establishes a safe single-UAV launch and read-only readiness proof; it does not arm, take off, or run a mission.

## Decision

Use the observed 28com single-UAV flow only as a lifecycle reference:

1. Start RflySim/CopterSim and PX4 SITL completely.
2. Start MAVROS as a persistent managed process after PX4 is ready.
3. Verify MAVROS from its actual state, odometry, and service advertisements.

Do not copy its network interface. The 28com reference is root `/mavros` with `udp://:20101@localhost:20100`. The project contract remains `/uav1`, but it must use a PX4-created dedicated MAVROS link rather than the Rfly SIL/CopterSim ports. The corresponding dual-UAV contract is `udp://:14601@127.0.0.1:14600` for `/uav1` and `udp://:14611@127.0.0.1:14610` for `/uav2`.

## Boundaries

The Stage 2.1 verifier may subscribe to `/uav1/mavros/state` and `/uav1/mavros/local_position/odom`, and wait for the set-mode and arming service advertisements. It must never invoke those services, publish setpoints, arm, or start a mission.

PX4 `out.log` is supporting evidence only. A missing `px4-mavlink` executable must not prevent ROS evidence collection. The report must label PX4 evidence as `fresh_snapshot`, `log_only`, or `unavailable`, instead of misrepresenting an existing log as fresh live output.

The project-owned launcher explicitly owns long-lived WSL processes. It must not use `nohup` in an immediately closing WSL shell, because those children are reaped. Do not alter or copy 28com sources, PX4 Firmware, RflySim3D, or CopterSim.

## Readiness and testing

`ready` requires the exact project contract, `state.connected: true`, a received concrete `nav_msgs/Odometry`, and service advertisement proof. Explicit ROS failures must be classified even with incomplete PX4 log evidence. Unit tests cover full/log-only/unavailable PX4 evidence and assert that odometry waits use `Odometry`, not Python `object`. Offline validation freezes ports, namespaces, no-flight rules, LF line endings, and launch dry-run output. A future live acceptance must show both connected state and odometry before Stage 5/6 work proceeds.
