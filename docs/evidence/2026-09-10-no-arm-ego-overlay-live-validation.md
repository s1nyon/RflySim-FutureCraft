# 2026-09-10 NO-ARM EGO Overlay Live Validation

## Result

**PASS.** A fresh protected simulation instance demonstrated the complete
no-arm chain:

```text
/uav1/mavros/odometry/out
  -> /uav1/planner/rflysim_ego_swarm_node
  -> /uav1/planner/rflysim_traj_server
  -> /uav1/planning/pos_cmd
```

No C++ mission process was launched or modified. No arming, OFFBOARD request,
takeoff, or MAVROS setpoint publication was performed.

## Runtime Identity

- Branch: `feature/cpp-competition-mission`
- Lifecycle implementation commits: `21bac2c`, `78d7f16`
- Final fresh stack: `stack-20260910T041329Z-aba6cc07`
- Simulation instance: `px4-95c5b5184fb3eaa4`
- Start command: `sim.ps1 start -Execute`
- Start result: exit 0 after GUI/ROSCORE/both MAVROS/course and dual-UAV
  topology gates reported READY
- Post-start inspect: `fail_closed=false`, `owned_and_alive=20`,
  `stale_pid_reuse=0`, `owned_orphan=0`, `unknown_suspicious=0`, unknown ports 0

## Overlay Proof

The diagnostic shell sourced exactly:

```bash
source /opt/ros/noetic/setup.bash
source third_party/ego-planner-swarm/devel/setup.bash
source future_aircraft_ws/devel/setup.bash
```

`rospack find ego_planner` returned:

```text
/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/third_party/ego-planner-swarm/src/planner/plan_manage
```

It did not resolve to `/root/catkin_ws`. The stale project devel underlay that
initially reintroduced `/root/catkin_ws` was regenerated through the repository
workspace build helper before live testing. `quadrotor_msgs/PositionCommand`
resolved with the repository overlay and the C++ package compiled successfully;
the C++ mission itself was not changed.

## ROS Graph Evidence

`rosnode info /uav1/planner/rflysim_ego_swarm_node` reported the actual
subscription:

```text
/uav1/mavros/odometry/out [nav_msgs/Odometry]
```

`rostopic info /uav1/mavros/odometry/out` reported:

- publisher: `/uav1/slam/odom_frame_relay`
- subscribers: `/uav1/mavros`, `/uav1/planner/waypoint_generator`, and
  `/uav1/planner/rflysim_ego_swarm_node`
- measured odometry rate in the first confirming run: approximately 10.07 Hz

Neither `/odom_world` nor `/grid_map/odom` existed in the runtime topic list.
Thus no publisher-less legacy odometry subscription remained active.

## Planner Stimulus and PositionCommand

A single bounded `geometry_msgs/PoseStamped` goal was published to
`/uav1/planning/goal` with frame `map` and position `(1, 0, 1)`. It was used only
to trigger EGO; there was no consumer from `pos_cmd` into PX4 control in this
no-arm run.

Observed output:

- topic: `/uav1/planning/pos_cmd`
- type: `quadrotor_msgs/PositionCommand`
- publisher: `/uav1/planner/rflysim_traj_server`
- final fresh-run frequency window: 98.577–101.584 Hz
- sample: `trajectory_id=2`, `trajectory_flag=1`, frame `world`, position near
  `(1.0031, -0.000006, 1.0043)`

MAVROS state immediately before and after the goal was identical:

```text
connected: True
armed: False
guided: False
mode: MANUAL
```

## Lifecycle Defect and Why Earlier Live Runs Worked

The confirmed defect was limited to recovery from a cross-run numeric identity
collision. An unfinished 2026-09-09 manifest recorded UAV2 sensor bridge
PID/PGID 737. On 2026-09-10, a foreign VS Code shell reused both numbers but had
a different start time and command line. Old inspect ordering treated any
member of PGID 737 as an owned orphan before considering the mismatched leader
identity. Normal earlier live runs did not encounter that rare stale-manifest +
reused-leader-PID/PGID condition, so their successful EGO and flight evidence is
not contradicted.

The fix gives a present leader identity precedence over group membership across
inspect, stop, and stale retirement. A narrow compatibility rule preserves
frozen WSL launchers that legitimately `exec` in place: same PID, start time
within five seconds, and a role-specific argv fragment are all required.

Regression tests prove:

- a foreign reused leader is stale, never orphan-owned;
- stop DryRun plans no signal for it and Execute leaves it intact;
- token-bound stale retirement sends no process signal;
- genuine leader-absent orphan behavior remains supported;
- legitimate FAST-LIO/sensor/MAVROS/EGO exec transformations remain owned.

The stale manifest retirement reported `planned_process_signals: []` and
`signal_sent=false`; PID 737 retained the same VS Code shell start time and argv
after retirement and clean stop.

## Validation and Safe Closure

- `scripts/validate_lifecycle.ps1`: PASS
- `scripts/validate_stage7.ps1`: PASS
- `scripts/validate_stage8.ps1`: PASS
- Final stack stop DryRun: `clean=true`, `refused=0`
- Final stack stop Execute: `clean=true`, final verification problems 0
- No broad process kill, `wsl --shutdown`, fresh-instance loop, or manual
  scheduled-task retry/mutation was used; only the standard clean-stop cleanup
  for its own registered launcher ran

## Decision

The requested no-arm PositionCommand evidence is **PASS**. A later simulation
flight may be proposed because the no-arm gate is now satisfied, but this run
did not arm and does not itself constitute a flight test.

## Addendum: Lifecycle Code-Review Blocker (same day, offline)

Review of the lifecycle commits found that the WSL exec-session exception in
`scripts/lifecycle/stack_inspect.py` was too wide: each role matched a single
generic argv fragment (`mavros`, `px4-mavlink`, `--copter-id N`,
`tail -f /dev/null`) and the same matcher is reused by the stop path. A foreign
process reusing a recorded PID/PGID inside the five second window could
therefore have been treated as owned and received PID/PGID signals.

Hardening implemented and offline validated in this pass:

- every role now requires an AND-combination of argv fragments
  (MAVROS = launch file + `uav_namespace`; px4-mavlink = `--instance`;
  sensor bridge = script name + `--copter-id`; launcher sessions = script name
  + `scripts/wsl/`; roslaunch roles = `roslaunch` + the specific launch file);
- the exception now requires `ownership.granted == at_creation`
  (spawn-attested entries keep their own marker/identity path);
- the SITL wrapper session, whose last `bash -lic` command is exec'd in place so
  its live argv is only `tail -f /dev/null`, additionally requires the
  launcher-inherited `RFLY_STACK_ID` marker (`live_stack_wsl_ops.sh marker`),
  fail-closed when the marker cannot be verified;
- counterexample tests cover UAV1/UAV2 role swap, foreign same-window commands,
  swapped instances, a spawn-attested entry with a perfect argv, and
  marker-denied / marker-absent behaviour on inspect, stop and retirement.

Host measurements behind the new rules (throwaway probe processes, killed by
explicit PID; no project process was started):

- `bash -lic '<...>; <cmd>'` execs the final command in place, so the recorded
  PID/PGID survives with only the keepalive argv (`tail -f /dev/null`);
- the exported `RFLY_STACK_ID` survives that exec, `/proc/<pid>/environ` is
  readable, and the marker helper returns 0 for the matching id and 1 for a
  wrong id.

Offline gates after the change: `scripts\validate_lifecycle.ps1` PASS,
`scripts\validate_stage7.ps1` PASS, `scripts\validate_stage8.ps1` PASS.

Two limits remain explicit:

1. The hardened matcher has **not** been exercised against a running stack. The
   next authorized no-arm live run must show every registered role still
   classifying as `owned_and_alive`, and any fail-closed role must be
   investigated before this patch is described as live-validated.
2. The raw diagnostics of the run above were observed interactively but not
   saved into `logs/live_stack/stack-20260910T041329Z-aba6cc07/`. Independent
   audit of the overlay/graph/frequency claims requires one more authorized
   no-arm live run with its outputs written under the new stack id.
