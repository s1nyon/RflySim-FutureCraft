# Stage 5E Simulation ARM Executor Design

## Scope

Stage 5E allows the Stage 5C mission executor to call MAVROS arming services in simulation. This accelerates the project toward a real dual-UAV closed loop while preserving a clear boundary between simulation and future real-aircraft use.

Validation remains offline. It verifies the arming policy and event surface, but it does not start RflySim, ROS, PX4, MAVROS, or GUI programs.

## Architecture

Extend the existing Stage 5C executor instead of adding a second runner:

```text
config/stage5_live_mission.json
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
scripts/validate_stage5e.ps1
tests/fixtures/stage5e/
```

`stage5_live_mission.json` gains a `simulation_arm_policy` object. `mission_executor.py` gains `--live-config` and `--simulation-only` flags. Arming is allowed only when all three conditions are true:

- CLI includes `--allow-arm`
- CLI includes `--simulation-only`
- live config contains `simulation_arm_policy.allow_arm: true`

When arming is allowed, the executor records simulation authorization events and proceeds with the backend arming action. When arming is blocked, the executor records the existing blocked event and does not call the backend service.

## Interfaces

CLI:

```text
mission_executor.py --plan live_mission_plan.json --live-config config/stage5_live_mission.json --backend dry-run --allow-arm --simulation-only --events mission_events.jsonl --trace executor_trace.json --score score_summary.json
mission_executor.py --plan live_mission_plan.json --live-config config/stage5_live_mission.json --backend ros --allow-arm --simulation-only --events mission_events.jsonl --trace executor_trace.json --score score_summary.json
```

Required config:

```json
{
  "simulation_arm_policy": {
    "allow_arm": true,
    "mode": "simulation_only",
    "operator_ack": "simulation_stage5e"
  }
}
```

Required arming events for each UAV:

- `arming_requested`
- `arming_allowed_by_simulation_gate`
- `arming_service_called`

Required takeoff event for each UAV:

- `takeoff_setpoint_published`

## Safety Boundary

Stage 5E does not remove the arming gate. It makes simulation arming explicit and auditable. A command that passes `--allow-arm` without `--simulation-only` must still block arming.

The ROS backend may call `/uavX/mavros/cmd/arming` only after the simulation gate passes.

## Testing

`scripts/validate_stage5e.ps1` runs offline. It generates a Stage 5B plan, runs `mission_executor.py` in dry-run mode with `--allow-arm --simulation-only --live-config config/stage5_live_mission.json`, compares events, trace, and score outputs to fixtures, then re-runs Stage 5D validation.

The validator must confirm the allowed arming event surface without starting live simulation.

## Live Gate

After Stage 5D ROS smoke passes against a running Stage 2 dual-MAVROS stack, Stage 5E can be run live with `--backend ros --allow-arm --simulation-only`. That run is expected to call OFFBOARD and arming services in the simulator.
