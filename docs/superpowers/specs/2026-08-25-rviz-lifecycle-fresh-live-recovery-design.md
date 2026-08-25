# RViz Lifecycle and Fresh Live Recovery Design

## Goal

Restore a truthful dual-UAV RViz session that participates in the existing
manifest lifecycle, then use one clean live-stack restart to determine whether
the observed no-lift flight failure belongs to the stale runtime instance rather
than to the protected mission or frame mathematics.

## Evidence and diagnosis

The unmanaged RViz launcher created a WSL `roslaunch` process and visualization
adapter children without registering the launcher PID/PGID at creation. Stack
inspection therefore reported them as `unknown_suspicious` and correctly blocked
simulation arming. Closing the two GUI windows did not stop the adapter children.

The subsequent diagnostic flight established a separate fact: both UAVs entered
`OFFBOARD`, both reported `armed=true`, and both MAVROS raw-local setpoint streams
ran at approximately 20 Hz. UAV1 nevertheless remained near `z=-0.106 m` and the
takeoff-altitude check timed out. The geofence watchdog reported no violation.
This evidence does not justify changing the mission route, setpoint coordinates,
z sign, MAVROS frame behavior, PX4, or CopterSim. The current long-lived live
instance must be replaced before attributing the no-lift symptom to code.

## Design

The Windows RViz entry point continues to accept `uav1`, `uav2`, or `dual`, but a
live invocation must also identify the active `stack_id` and manifest. It converts
the manifest to a WSL path and invokes a small project-owned WSL wrapper. The
wrapper sources the established ROS overlays, verifies X11 and manifest inputs,
registers its own PID/PGID as `wsl:rviz_session` before `exec roslaunch`, and does
not publish TF or control messages. Direct children of the registered roslaunch
remain attributable under the frozen inspector rules.

ROS setup files are sourced before enabling Bash nounset mode because the Noetic
setup chain legitimately reads variables that may initially be unset. No lifecycle
ownership, inspector, manifest schema, launch order, TF, flight route, or control
algorithm is changed.

## Recovery and validation flow

1. Run focused RViz contract, adapter, Bash syntax, lifecycle, Stage 7, and Stage 8
   offline checks.
2. Commit the RViz lifecycle fix on the current infrastructure branch.
3. Use the standard manifest stop for the current stack and verify clean ownership,
   no unknown processes, and required ports released. No name sweep is permitted.
4. Start one fresh stack through `sim.ps1 start -Execute` and wait for READY.
5. Launch dual RViz with the new stack ID and manifest; require four expected ROS
   nodes, `wsl:rviz_session` in the manifest, and `unknown_suspicious=0`.
6. Collect fresh no-arm sensor readiness for the new simulation instance.
7. Run the existing simulation-only tunnel mission without route or parameter
   changes while observing MAVROS setpoint targets, mode, arming, altitude, and
   final landing/disarm evidence.

If the fresh instance flies, the previous no-lift behavior is classified as stale
runtime state and no flight code is changed. If it repeats with valid target data,
the run fails closed and the next investigation moves to the PX4-to-CopterSim
actuator boundary; no coordinate or mission patch is guessed in this iteration.

## Rollback and safety

The RViz change is isolated to its launcher, WSL wrapper, and focused contract
test and can be reverted as one commit. RViz remains optional and off by default.
All arming still requires fresh readiness, `--allow-arm`, `--simulation-only`, an
allowing simulation policy, and matching run/instance identity. Failure cleanup
uses only the standard manifest lifecycle.
