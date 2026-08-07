# Future Aircraft Sim Agent Handbook

This file is the machine-oriented operating guide for the repository. Any agent working in this workspace should read the files under `.agents/` before making changes, with this document as the primary source of execution rules and current project state. When a task touches the simulation toolchain, also follow [RFLYSIM_TOOLCHAIN_REFERENCE.md](RFLYSIM_TOOLCHAIN_REFERENCE.md) before diagnosing or changing code.

## Repository Purpose

`future_aircraft_sim` is the simulation-side workspace for a multi-UAV indoor navigation and task-execution challenge. The project reuses the existing `28com_uav` ROS1/PX4/MAVROS stack, then layers a simulation-focused mission workflow on top of it.

## Working Rules

- Do not copy or rewrite the original `28com_uav` project into this repository.
- Keep ROS development inside `future_aircraft_ws`.
- Keep Windows launch orchestration, environment setup, and run wrappers in `scripts/`, `config/`, and related support files.
- Preserve the `/uav1` and `/uav2` namespace contract.
- The watchdog, executor navigation verification, and preflight topic wait use
  `/uavX/mavros/local_position/odom` (PX4-fused, 28com-parity) as the primary
  odometry source. `/uavX/mavros/odometry/in` is only a cross-check; FAST-LIO raw
  odometry stays under `/uavX/slam/odometry_raw`.
- The MAVROS odometry plugin TF contract is a hard pre-arm gate
  (`odom_tf_contract_check.py`): it mirrors the four static lookups MAVROS
  1.20.1 performs per UAV and scans mavros logs for `ODOM: Ex`.
- Keep Stage 5 `mission_events.jsonl` compatibility intact.
- Simulation arming is acceptable in this project when `--simulation-only`, `--allow-arm`, and `simulation_arm_policy.allow_arm=true` all agree.
- Never assume real-hardware arming is allowed; real aircraft must remain manual-arm by default.
- If a UAV's reported xyz position is wildly unreasonable (non-finite, or beyond
  the course geofence by more than `Geofence.unreasonable_margin_m`), the
  geofence watchdog returns `no_autoland` / `unreasonable_position` and never
  requests AUTO.LAND. The correct response is to fix the code and restart the
  simulation; do not rely on a garbage-state auto-return.
- If a task changes an interface, update both this file and the root `README.md`.

## Environment Map

Confirmed local locations under `D:\PX4PSP`:

- `D:\PX4PSP\RflySimAPIs` - RflySim APIs and example material
- `D:\PX4PSP\RflySim3D` - RflySim3D launcher and assets
- `D:\PX4PSP\CopterSim` - CopterSim runtime
- `D:\PX4PSP\Firmware` - PX4 firmware tree used by the simulation stack
- `D:\PX4PSP\Python38\python.exe` - local Python runtime used by validation and helper scripts
- `D:\PX4PSP\WinWSL` - Windows-side WSL helper assets
- `D:\PX4PSP\VcXsrv` - X server bundle used by the WSL launch flow

WSL-side conventions used by the scripts:

- `RFLYSIM_WSL_DISTRO=RflySim-20.04`
- `PSP_PATH_LINUX=/mnt/d/PX4PSP`
- `REF_28COM_UAV_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav`
- `FUTURE_AIRCRAFT_SIM_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim`
- ROS1 Noetic is sourced from `/opt/ros/noetic/setup.bash` inside that distro

## Current State

Latest Stage 8 live evidence, 2026-08-02:

- The tunnel-flight run `stage7-20260802T102552Z-8563` did **not** pass. Sensor readiness and the layered topic probe passed, but UAV2 was observed armed in `ALTCTL` at approximately 11.257 m and left the effective localization area. The executor later failed UAV1 navigation with `planner_commands=0` and `last_distance=2.596m`.
- Both simulated vehicles were confirmed disarmed at the end. Do not report tunnel traversal or landing success from this run.
- Two preceding watchdog defects were reproduced and corrected in the working tree: duplicate ROS node names and an immediate non-OFFBOARD decision during the post-arm state-message race. These corrections pass the focused geofence check and offline Stage 8 validation, but they do not resolve the altitude/planner failure.
- Read [docs/stage8_tunnel_live_issue_2026-08-02.md](../docs/stage8_tunnel_live_issue_2026-08-02.md) before the next live attempt. Capture actual planner z, MAVROS raw setpoint z/frame/type mask, odometry frame direction, PX4 mode-loss reason, and watchdog decisions before changing the route or relaxing safety bounds.

2026-08-07 interface updates (merged into `main` and pushed to
`origin/main` on 2026-08-07; all development now happens on `main`):

- **ego-swarm inter-UAV coordination caveat**: the swarm trajectory broadcast
  (`/broadcast_bspline`, `/drone_*_planning/swarm_trajs`) assumes all UAVs share
  one coordinate frame and start times within 0.25 s. This project runs each UAV
  on its own FAST-LIO frame (origin at its takeoff pose), so the received swarm
  trajectories are NOT valid in the local frame and are often discarded by the
  time-sync check. Do not rely on `swarm_clearance` for collision avoidance.
  Inter-UAV collision avoidance must come from perception: each UAV's mid360
  cloud feeds its grid map, and the planner's collision check triggers replan or
  emergency stop. Verify with `check_swarm_obstacle.py` before trusting it.

- `mission_executor.py` now writes partial `mission_events.jsonl`,
  `executor_trace.json`, and `score_summary.json` on every failure path
  (`mission_failed` event plus completed-action trace), instead of only on success.
- `stage7_run_artifacts.py` emits `provenance.json` (git_commit, base_map,
  course_name, course_spec_sha256, simulation_instance_id, ros_master_uri);
  `stage7_flight_report.py` embeds it under `report.provenance`.
- `course_geofence_watchdog.py` writes structured JSONL decisions
  (`--output`, every state change) with an explicit `reason`
  (`outside_x|outside_y|outside_z|mode_loss|stale_odom|max_speed|
  unreasonable_position|disarmed|ok`; `unreasonable_position` yields decision
  `no_autoland` instead of `land`);
  `watchdog_decision_with_reason` is the canonical decision API.
- `stage7_topic_probe.py` replaced the fake-positive goal check with a real
  subscriber-count check and added planner-command message-flow measurement.
- New `odom_tf_contract_check.py` (Gate B) verifies the namespaced TF frames and
  the exact MAVROS odom-plugin lookups, and scans mavros logs for `ODOM: Ex`.
- `rflysim_fastlio_dual.launch` static TF publishers now use `respawn="true"`;
  `rflysim_ego_swarm_single.launch` no longer publishes global
  `world/map/base_link/camera_link` static frames that polluted the TF tree.
- `stage8_dynamic_lidar_probe.py` is SLAMScene-aware: capture takes sensor
  pose/yaw and wall world-NED coordinates and projects the wall into the LiDAR
  frame for ROI counting.
- `stage7_topic_probe.py` now carries the D435i transport contract in its
  `sensor_bridge` layer: `topic_publisher_count` (exactly one publisher on
  `/uav*/rflysim/sensor*/img_depth`) and `depth_image_flow` (hard checks for
  `mono16`, 640x480, 20-45 Hz receive rate, monotonic header stamps, and at
  least one non-all-zero frame; report includes zero_ratio and depth
  min/max). `validate_config()` now requires the vision fields
  (`raw_rgb_topic`, `raw_bottom_topic`, `raw_depth_topic`, `depth_topic`,
  `sensor_rgb_topic`, `sensor_bottom_topic`, `sensor_depth_topic`,
  `planner_depth_topic`, `mavros_setpoint_topic`). This covers the transport
  half of the D435i pending live items; wall-geometry consistency is still a
  live-only check.
- New read-only `stage8_control_chain_recorder.py`: subscribes to
  `/uav*/planning/pos_cmd`, `/uav*/mavros/setpoint_raw/local`,
  `/uav*/slam/odometry_raw`, `/uav*/mavros/odometry/out`,
  `/uav*/mavros/odometry/in`, `/uav*/mavros/local_position/odom`, and
  `/uav*/mavros/state`; writes run-scoped
  `$STAGE7_RUN_DIR/stage8_control_chain.jsonl` plus
  `stage8_control_chain_summary.json`. Every event carries
  `receive_wall_time`, `receive_monotonic`, and `header.stamp`; setpoint z is
  only counted as commanded when `IGNORE_PZ` is unset. It never publishes,
  never calls services, and never arms; watchdog and flight-event recording
  stay with their existing implementations. Launch with
  `scripts\run_stage8_control_chain_recorder.bat`.
- Flight artifacts are now run-scoped:
  `stage7_live_slam_ego_swarm_flight.sh` writes plan, smoke report, flight
  report, mission events, executor trace, score summary, executor/runner
  logs, and watchdog/keepalive outputs under `$STAGE7_RUN_DIR`;
  `run_stage7_topic_probe.bat` writes
  `$STAGE7_RUN_DIR/topic_probe_report.json`. Only the run metadata
  `logs/stage7_live/current_run.env` stays flat, so historical evidence can
  never be confused with the current instance.
- `run_stage8_control_chain_recorder.bat` must source the 28com_uav workspace
  for `quadrotor_msgs` (added 2026-08-07; validate_stage8.ps1 enforces it).
  The recorder's default geofence z is `[-0.5, 2.0]`, matching the course
  watchdog, so idle ground samples at z~-0.1 are not flagged as outside.
- Live flight 2026-08-07 (instance `px4-c50420f823fe4489`) reached OFFBOARD
  + arming on both UAVs but aborted at takeoff: the geofence watchdog fired
  `land/stale_odom` on a single 0.52 s odometry gap (> 0.5 s threshold) right
  when the takeoff setpoint was published, so altitude never left the ground.
  The flight runner's watchdog now uses `--max-odom-age-s 2`;
  validate_stage7.ps1 enforces it. A 2 s odom loss is still an immediate land.
- **D435i sensor parity (commit `39742ab`)**: both UAV sensor configs now carry
  Mid360 + D435i RGB/depth + down camera, matching the real FS-310/28comsim
  payload. `rflysim_fastlio_dual.launch` relays `/rflysim/sensor*` camera
  topics into `/uav*/rflysim/sensor*`; `rflysim_ego_swarm_dual.launch` feeds
  the real `img_depth` topic into `grid_map/depth`. Read
  [docs/d435i_sensor_parity_2026-08-07.md](../docs/d435i_sensor_parity_2026-08-07.md).

Latest live evidence, 2026-08-01 (post-Stage-7 baseline):

- Full dual-UAV flight run `stage7-20260801T101757Z-2497` passed (both UAVs
  armed in OFFBOARD, takeoff to 1 m, short ego-swarm segment, landing, disarm;
  min separation 0.85 m).
- Staggered tunnel traversal succeeded end-to-end: UAV1 led, UAV2 lagged, all
  seven course segments reached, no collision and no emergency stop.
- Perception-based collision avoidance verified live: UAV1 was marked as an
  obstacle in UAV2's grid_map and UAV2 executed `EMERGENCY_STOP` at 0.2 m.
  Swarm-trajectory coordination is NOT reliable across the two independent
  FAST-LIO frames and must not be treated as the collision guarantee.

Latest D435i work, 2026-08-07 (offline only, live validation pending):

- `config/rflysim_sensor_uav{1,2}.json` now define per UAV: Mid360 (TypeID 23),
  D435i RGB (TypeID 1 @[0.1,0.04,0]), down camera (TypeID 1 @[0,0,0.1],
  pitch -90), D435i depth (TypeID 2 @[0.1,0.04,0], 0.3-12 m).
- Sensor contract test, bridge import test, and readiness test all pass
  offline. Launch XML parses. The D435i transport probe (unique publisher,
  ~30 Hz, mono16/640x480, monotonic stamps, non-zero frames) is now part of
  `stage7_topic_probe.py` and passes offline. Live no-arm verification of the
  depth topics, depth wall-geometry consistency, and of ego-swarm depth fusion
  still has to be run on the next simulation restart.
- First live probe run (instance `px4-a289b8bc70d45c16`, run
  `stage7-20260807T063728Z-2686`): readiness five gates passed and the depth
  transport checks (unique publisher, mono16, 640x480, non-zero) passed, but
  the relayed depth topics measured only ~1.8/2.2 Hz instead of the configured
  30 Hz, so `depth_image_flow` failed its rate gate. Raw-vs-relay rate
  comparison and wall-geometry consistency are still open live items.

Validated offline stages:

- Stage 0: workspace and launch scaffold
- Stage 1: single-UAV launch chain
- Stage 2: dual-UAV namespace launch chain
- Stage 4: ego-swarm offline adapter contract
- Stage 5A to Stage 5E: behavior tree, live boundary, executor, smoke checks, and simulation-arm executor
- Stage 6A: ideal target provider bridge
- Stage 6B: simulation-vision target provider bridge
- Stage 6C: live dual-MAVROS smoke runbook
- Stage 6D / 6E: no-arm live smoke runner and simulation-arm live runner
- Stage 7: offline dual-sensor isolation, RflySim-to-Ouster cloud adaptation, run-scoped no-arm readiness, ego-swarm, and guarded simulation-arm flight runner contracts
- Stage 8: project-local predicted narrow-course specification, deterministic Python artifacts, safe RflySim dynamic-object loading, ROS reference cloud, and course-specific dual-UAV launch contracts

Current limits:

- Stage 2.1 is a hard gate before Stage 6D/6E: run `scripts\run_stage2_1_mavlink_check.bat` after the selected single-UAV simulation path is started, inspect `logs/stage2_1_live/mavlink_link_report.json`, and proceed only when `status` is `ready`. The legacy Rfly SIL-port report `px4_to_mavros_return_path_blocked` was resolved for the dual path by creating dedicated MAVROS links; it does not mean Stage 6D or Stage 6E has passed.
- Offline validation passes for the staged contracts. Live GUI validation has confirmed dual PX4, dual MAVROS and `state.connected: true`; the Stage 6D odometry input is `/uav*/mavros/odometry/in`, sourced from PX4 MAVLink `ODOMETRY` through MAVROS extras, and still requires fresh end-to-end confirmation.
- Stage 6D dry-run validates the no-arm live runner contract without launching anything.
- Stage 6E dry-run validates the simulation-arm runner contract; real execution first runs dual-MAVROS smoke checks, then may call `/uav1/mavros/cmd/arming` and `/uav2/mavros/cmd/arming` in simulation only when the checks and all arm gates pass.
- Stage 7 dry-run/offline validation covers two identified sensor bridges, exact Ouster point fields/timing, normalized per-UAV LiDAR/IMU, run-scoped readiness validation, dual FAST-LIO, dual ego-swarm, and the guarded flight runner. Live sensor/FAST-LIO readiness and the minimum dual ego-swarm flight loop are proven by the 2026-08-01 runs below. The remaining gap is repeatability, longer/obstacle-rich routes, and full mission integration—not first-flight feasibility.
- `run_live_fastlio_dual.bat` is now the no-arm acceptance entrypoint. It writes `logs/stage7_live/<run-id>/sensor_readiness.json` and `logs/stage7_live/current_run.env`; later planner/flight runners reject missing, stale, cross-run, cross-instance, shared-source, unstable, or armed evidence.
- Vision integration is still staged through deterministic providers rather than real detector inference.
- New live-first direction: the Stage 7 FAST-LIO/faster_lio, project-local ego-swarm, and minimal simulation-arm takeoff/flight/landing loop is proven. Prioritize 3–5 fresh-instance repeat runs, longer collision-free routes, and run-scoped artifact cleanup before reconnecting vision, target detection, and behavior-tree mission logic.

## Live Debug Notes, 2026-07-29

The live toolchain investigation reached Stage 2 and was intentionally stopped before completing Stage 6D/6E live validation. Do not report live validation as complete until a fresh run captures Stage 6D no-arm smoke output and, if requested, Stage 6E simulation-arm output.

Confirmed fixes and operating notes from the live debugging session:

- Windows `cmd` launchers must not use nested quoting like `cmd /k "call ""..."""`; that pattern produced Chinese Windows errors equivalent to "The filename, directory name, or volume label syntax is incorrect" and "The command syntax is incorrect." Use `cmd /k call "..."` for generated `.bat` wrappers.
- `scripts/start_two_uav.bat` should start `start_vcxsrv.bat` before launching RflySim/PX4/MAVROS. VcXsrv is part of the RflySim/WSL GUI path.
- Avoid `timeout /t` inside these noninteractive orchestration windows. Use PowerShell `Start-Sleep` for boot waits.
- WSL shell scripts under `scripts/wsl/*.sh` must stay LF-only. `.gitattributes` enforces this with `scripts/wsl/*.sh text eol=lf`.
- The generated two-UAV SITL wrapper must call WSL as `wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "..."` and must preserve the generated `%VehicleNum%`, `%START_INDEX%`, and `%PX4SitlFrame%` variables.
- `scripts/wsl/stage2_two_mavros.sh` must keep the WSL session alive after starting `roscore` and the two MAVROS launches. Without the final `wait`, `roscore` can start successfully and then shut down when the WSL launch session exits.
- After the keepalive fix, a live process check showed `roscore`, `rosmaster`, two `roslaunch mavros px4.launch` processes, and two `mavros_node` processes running in WSL. This is evidence for Stage 2 process residency only, not a full mission smoke pass.
- `Firmware/Tools/sitl_multiple_run_rfly.sh` reserves `16540/17540` and `16541/17541` for the Rfly SIL/CopterSim link. `scripts/wsl/stage2_two_mavros.sh` must create dedicated PX4 MAVLink links before starting MAVROS: `/uav1` uses `udp://:14601@127.0.0.1:14600`, `/uav2` uses `udp://:14611@127.0.0.1:14610`. Reusing the Rfly SIL ports makes MAVROS stay `connected: False`.

Latest live evidence, 2026-07-30:

- `scripts\start_two_uav.bat` successfully started RflySim3D, two CopterSim processes, two PX4 instances, roscore and two MAVROS nodes.
- After the dedicated-link change, `/uav1/mavros/state` and `/uav2/mavros/state` both reported `connected: True`, `armed: False`, `mode: MANUAL` and `system_status: 3`.
- The previous Stage 6D no-arm smoke was blocked by missing `/uav1/mavros/local_position/odom` and `/uav2/mavros/local_position/odom`. That MAVROS topic requires `LOCAL_POSITION_NED_COV`, which this PX4 build cannot stream. Stage 6D now waits for `/uav1/mavros/odometry/in` and `/uav2/mavros/odometry/in`, the MAVROS outputs of PX4 `ODOMETRY`; `odometry/out` is the reverse input to PX4. Do not treat connection success as a completed mission smoke until a fresh no-arm report passes.

Latest Stage 7 live evidence, 2026-08-01:

- Full dual-UAV flight run `stage7-20260801T101757Z-2497`, simulation instance `px4-bb8094a4352d452e`, completed successfully after `ce7e0a7` shortened the wall-adjacent navigation segment and made reached-goal verification independent of a future planner command. Both UAVs armed in OFFBOARD, took off to 1 m, completed the short ego-swarm segment, landed, and disarmed. `flight_report.json` recorded `ready: true`, `collision_count: 0`, `offboard_loss_count: 0`, `timeout_count: 0`, minimum separation `0.85 m`, and duration `23.5 s`.

- Run `stage7-20260801T082349Z-6875`, simulation instance `px4-ac4e722ff724856a`, saved `logs/stage7_live/stage7-20260801T082349Z-6875/sensor_readiness.json`.
- `identity`, `schema`, `freshness`, `isolation`, and `stationary_stability` all passed; both MAVROS states remained `armed: false`, `mode: MANUAL`, and the report returned `ready: true`.
- Each adapter accepted 17,408 points with the exact 32-byte Ouster field layout. Two independent `run_mapping_online` processes remained active and the FAST-LIO log had no missing-field, fatal, process-died, or segmentation errors.
- Live corrections are committed as `e169acc` (ROS initialization, bounded startup and lifecycle cleanup) and `7c9e363` (namespaced IMU source remaps). No planner goal, setpoint, OFFBOARD, ego-swarm, or arming command was sent.
- A later no-arm run `stage7-20260801T090244Z-5522`, simulation instance `px4-2c74476509ac6faa`, again passed identity, schema, freshness, isolation, and stationary stability with both vehicles disarmed. The first ego-swarm launch then failed before `roslaunch` because sourcing the standalone ego workspace hid the project ROS overlay; `9ad9b4c` restores the project overlay with `--extend`, and `46178c0` aligns the read-only topic probe with the ego runner's 120-second readiness window. The successful `stage7-20260801T101757Z-2497` flight supersedes the earlier “requires fresh live run” status.

## Recommended Next Step

Stage 7's minimum dual-UAV live loop is accepted. Continue from this baseline in the following order:

1. Repeat the complete run 3–5 times on fresh simulation instances and record clean-run rate, duration, minimum separation, collisions, OFFBOARD losses, and timeouts.
2. Increase route length and wall clearance incrementally, retaining a failed offline regression before each defect fix.
3. Move flight artifacts fully under their run directory so historical evidence cannot be confused with the current instance. (completed 2026-08-07)
4. Reconnect target perception and behavior-tree mission logic only after the live loop is repeatable.

Every simulator restart requires a new run id and simulation instance id. Historical readiness reports remain evidence only and must never authorize a later flight. Simulation flight still requires the explicit `--allow-arm --simulation-only` gates; real aircraft remain manual-arm.

Current Stage 7 entrypoints:

1. `scripts\start_two_uav.bat`
2. `scripts\run_live_fastlio_dual.bat`
3. `scripts\run_live_ego_swarm_dual.bat`
4. `scripts\run_stage7_topic_probe.bat`
5. `scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`

Stage 7 intentionally uses `/uav*/mavros/odometry/out` for FAST-LIO external odometry into MAVROS. Stage 6D still observes `/uav*/mavros/odometry/in` from PX4/MAVROS feedback. Keep those directions distinct.
The raw Stage 7 sources are `/rflysim/sensor0/mid360_lidar` plus `/uav1/rflysim/imu_raw`, and `/rflysim/sensor10/mid360_lidar` plus `/uav2/rflysim/imu_raw`. FAST-LIO consumes only normalized `/uav1/rflysim/{lidar,imu}` and `/uav2/rflysim/{lidar,imu}`.
`scripts\run_stage7_topic_probe.bat` is read-only and writes `logs/stage7_live/topic_probe_report.json` with `sensor_bridge`, `fast_lio`, `mavros`, `ego_swarm`, and `flight_gate` readiness layers. Run it before the Stage 7 simulation-arm flight runner and use it as the first failure triage artifact.

The Stage 7 planner, topic probe, and flight runner reuse the current readiness `run_id` and `simulation_instance_id`. The flight runner validates that evidence before creating setpoint bridges or requesting OFFBOARD/arming and writes `logs/stage7_live/flight_report.json` on executor success and failure. Keep planner goals isolated on `/uav1/planning/goal` and `/uav2/planning/goal`.

This route intentionally skips object detection, target provider, and behavior-tree mission logic.

Offline validation baseline:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

## Stage 8 Predicted Narrow Course

`config/maps/predicted_narrow_course_v1.json` is the only authoritative course geometry. `scripts\generate_predicted_narrow_course.bat` creates the preview, reference points, validation report, and flat `VisionRingBlank` terrain pair under ignored `generated/` output. `scripts\start_predicted_course_two_uav.bat --dry-run` is the side-effect-free launch contract; without `--dry-run` it starts the existing two-UAV chain on `VisionRingBlank` and loads course-owned dynamic IDs `12000..12999`.

The course launcher does not request OFFBOARD or arm. A live map check must proceed through `scripts\run_live_fastlio_dual.bat` and `scripts\run_stage7_topic_probe.bat` before any separately authorized simulation-only flight. Dynamic walls are not CopterSim terrain: accept them through RflySim LiDAR visibility and geometric-clearance evidence, not through terrain-height queries. Never deploy generated terrain files over `CopterSim\external\map` without an explicit user request and an exact-target backup/check.

## Developer Lessons (2026-08-07)

High-value findings from recent development. Read these before touching sensor
config, ego-swarm wiring, odometry, or the live run flow.

### Sensor stack: 28comsim parity and the "no D435i" question

- RflySim `VisionCaptureApi.jsonLoad` has its own format contract that plain
  `json.loads` cannot catch: 16-entry `otherParams` requires `EularOrQuat`
  plus 4-entry `SensorAngQuat` (28com's RGB uses this new-protocol shape),
  while 8-entry `otherParams` must NOT set `EularOrQuat`. A live sensor-bridge
  run rejected the D435i RGB/depth with `Json data format is wrong!` and
  loaded only lidar + down camera until both configs were fixed.
  `stage7_dual_sensor_config_check.py::validate_sdk_loadable` now enforces it.
- The real FS-310/28comsim `UAV_demo` carries D435i (RGB + depth), a down-facing
  monocular camera, and Mid360/IMU. Its simulation `Config.json` only has
  mid360 + front RGB + down RGB: **there is no TypeID 2 depth in 28com's
  simulation**. The FS-J310 launch's `depth_topic=/rflysim/sensor1` is dead in
  simulation (the real topic is `/rflysim/sensor1/img_rgb`), so 28com's
  simulation also runs EGO-Planner cloud-only. Our previous no-depth setup was
  therefore 28com-sim parity, not a defect.
- EGO-Planner's grid map builds from `grid_map/cloud` (required) and uses
  `grid_map/depth` only as an optional enhancement (projection/filter). A LiDAR
  cloud is enough to plan. What depth/RGB actually unlock are `drone_detect`
  (other-UAV detection from depth) and `object_det` (YOLO on RGB). Neither is
  currently used; inter-UAV avoidance must come from perception
  (mid360 -> grid_map obstacle marking + `EMERGENCY_STOP`), which is verified.
- RflySim `VisionCaptureApi` publishes absolute topics per `SeqID` and
  `TypeID`: TypeID 1 -> `/rflysim/sensor{seq}/img_rgb`, TypeID 2 ->
  `/rflysim/sensor{seq}/img_depth` (mono16, millimeters), TypeID 23 ->
  `/rflysim/sensor{seq}/mid360_lidar`. Because topics are absolute, per-UAV
  namespacing requires explicit `topic_tools` relays (already added in
  `rflysim_fastlio_dual.launch`).
- TypeID 2 depth over `SendProtocol=1` (UDP jpeg) is a standard, officially
  documented combination and works from WSL/Linux; shared memory (protocol 0)
  is Windows-local only.
- This repo's sensor config JSONs must be comment-free plain JSON because
  `rflysim_sensor_bridge.py` validates them with `json.loads`. 28com's
  commented `Config.json` files only parse because `VisionCaptureApi` is
  lenient.

### ego-planner-swarm parameter semantics (this fork)

- In `external/ego-planner-swarm`, `grid_map/pose_type` is
  `POSE_STAMPED = 1`, `ODOMETRY = 2` (verify against `grid_map.h`; other EGO
  forks may differ). Our launch uses `pose_type=2`, so the depth image is
  synchronized with `grid_map/odom` via `depthOdomCallback` and
  `grid_map/pose` is never subscribed. **No separate camera-pose topic is
  needed.**
- `md_.cam2body_` is a fixed rotation with no translation: depth projection
  assumes the camera is at the body origin. The D435i's 0.1/0.04 m mounting
  offset is ignored by EGO, which is acceptable inside the 0.25 m inflation.

### Odometry and coordinate frames

- The two UAVs run independent FAST-LIO frames (origins differ by the takeoff
  offset, about 1.4 m). ego-swarm's swarm trajectory cost directly subtracts
  trajectories, so cross-frame swarm coordination is invalid; the broadcast is
  also gated by a 0.25 s start-time window, non-periodic publishing, and no
  broadcast while in `WAIT_TARGET`. Fix path: unify frames first at the odom
  layer (add takeoff offsets in `odom_frame_relay.py`), then optionally patch
  `ego-planner-swarm` source (periodic broadcast, wider time window, stale
  trajectory broadcast) and rebuild.
- `/mavros/odometry/in` reporting z≈+1 (ENU side) is normal and is NOT evidence
  of a coordinate-chain error. The real pre-arm gate is the MAVROS odometry
  plugin's hardcoded `odom_ned`/`base_link_frd` TF lookups and PX4 EKF
  external-vision fusion flags.
- FAST-LIO `extrinsic_T=[0,0,0.1]` is the calibrated value matching the lidar
  mount at `[0,0,-0.1]` (FRD). Do not "fix" it again.

### Live flow and housekeeping

- Simulation arm only with `--allow-arm --simulation-only`; real aircraft stay
  manual-arm. Every simulator restart is a new `simulation_instance_id`;
  readiness reports from other runs/instances are always rejected.
- Stage 7 live order is fixed:
  `start_two_uav.bat` -> `run_live_fastlio_dual.bat` ->
  `run_live_ego_swarm_dual.bat` -> `run_stage7_topic_probe.bat` ->
  `run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`.
- `run_live_fastlio_dual.bat` now also relays RGB/depth/down-camera topics into
  `/uav*/rflysim/sensor*`; use those names in probes and planner wiring.
- GitHub push to `s1nyon/RflySim-FutureCraft` failed with `Connection was
  reset` until git was pointed at the local Clash proxy. Fix (already applied,
  global): `git config --global http.proxy http://127.0.0.1:7890` and the same
  for `https.proxy`. Clash for Windows runs on 127.0.0.1:7890 and WinINET is
  already set to it, but git had no proxy and was trying the blocked
  `github.com` IP directly. If the GCM "Unable to persist credentials with the
  'wincredman' credential store" warning appears, it is cosmetic; the push
  still succeeds.

### Pending live validation (next simulation restart)

1. No-arm: run `scripts\run_stage7_topic_probe.bat`; the new
   `depth_publisher_count` and `depth_flow` checks must pass for
   `/uav1/rflysim/sensor3/img_depth` and `/uav2/rflysim/sensor13/img_depth`
   (transport half; note the first live probe measured ~2 Hz, below the
   20-45 Hz gate — compare raw vs relayed rate before accepting).
   Confirm depth values match the course walls/ceiling geometry (live-only;
   the transport probe cannot prove it).
2. ego-swarm log shows depth fusion actually triggering
   (`depthOdomCallback` / `flag_use_depth_fusion`).
3. Compare occupancy/trajectory in the narrow tunnel with depth fusion on vs
   off; re-verify perception emergency stop still works with fusion enabled.

## File Map

- `config/` - stage contracts, environment templates, and deterministic fixtures.
- `scripts/` - Windows launchers, validation entry points, and WSL helpers.
- `future_aircraft_ws/` - ROS1 workspace sources for mission logic and adapters.
- `tests/fixtures/` - frozen outputs for offline regression checks.
- `docs/superpowers/` - design notes and implementation plans.
- `.agents/` - machine-oriented instructions and repository operating notes.
- `README.md` - human-facing repository overview.

## Sandbox Note

If the Windows sandbox runner is blocked, non-destructive PowerShell commands may be run directly for read-only inspection, offline validation, and local dry-run checks. Simulation live runners can be launched when the user has explicitly accepted simulation arming risk. Anything that can delete, overwrite broadly, change git history, install or download dependencies, or arm real hardware still requires explicit confirmation.
