# Stage 4 Ego-Swarm Minimal Integration Design

## Scope

Stage 4 introduces the official `ego-planner-swarm` source and a local adapter contract without changing the upstream project. The first deliverable is an offline-verifiable integration layer: repository metadata, adapter configuration, launch command generation, and validation scripts.

## Approach

Recommended approach: keep upstream `ego-planner-swarm` under `external/ego-planner-swarm`, and keep all project-specific behavior inside `future_aircraft_ws/src/multi_uav_mission`. This protects the official source from local task logic and lets future updates be handled as an explicit external dependency refresh.

Alternatives considered:

- Vendor ego-swarm directly into `future_aircraft_ws/src`: simpler for `catkin_make`, but mixes external and local ownership.
- Add only documentation now: low risk, but does not establish a testable adapter contract.
- Build the full planner immediately: valuable later, but too dependent on ROS/PCL/Eigen/WSL state for the first Stage 4 checkpoint.

## Interfaces

The adapter reads `config/stage4_ego_swarm.json` and produces per-UAV launch commands for:

- namespace: `/uav1`, `/uav2`
- odometry input: `/uavX/mavros/local_position/odom`
- goal input: `/uavX/planner/goal`
- trajectory output: `/uavX/planner/trajectory`
- frame: `map`

The adapter CLI is `future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py`.

## Error Handling

The adapter fails clearly when the config file is missing, malformed, or missing required UAV fields. The Stage 4 validation script must not require a live ROS master, MAVROS, PX4, or RflySim.

## Testing

Stage 4 validation runs offline:

- Verify the official repository exists, or record the expected clone command when network access is not available.
- Verify adapter config fields for both UAVs.
- Run adapter CLI against the fixture config and compare generated command data to `tests/fixtures/stage4/expected_ego_swarm_commands.json`.
- Re-run Stage 0-3 validation to prevent regressions.

## Live Gate

The live ROS gate remains separate: after ROS dependencies are available in WSL, compile and run the official ego-swarm demo, then replace generated command placeholders with known-good launch files and package names.
