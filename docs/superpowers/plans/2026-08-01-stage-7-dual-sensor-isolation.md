# Stage 7 Dual-Sensor Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two independently identified RflySim LiDAR/IMU chains, adapt their clouds to the faster_lio schema, and fail closed before planner startup or arming unless a current no-arm readiness report passes.

**Architecture:** Two project-owned sensor configurations bind distinct RflySim sensors to CopterSim 1 and 2. A bridge process per vehicle publishes identity plus raw input, a focused point-cloud adapter produces vehicle-namespaced FAST-LIO inputs, and a readiness checker validates identity, schema, freshness, isolation, and stationary stability. Existing Stage 7 launchers consume only those normalized topics and arm-capable execution requires the saved readiness report.

**Tech Stack:** Python 3, ROS1 Noetic (`rospy`, `sensor_msgs`, `nav_msgs`, `std_msgs`), RflySimSDK `VisionCaptureApi`, ROS launch XML, Bash/WSL, PowerShell validators, JSON.

## Global Constraints

- Work only inside `future_aircraft_sim`; do not modify `28com_sim`, RflySimSDK, CopterSim, PX4 Firmware, or upstream faster_lio/ego-swarm sources.
- UAV1 and UAV2 must have different CopterSim IDs, sensor SeqIDs, UDP ports, raw topics, and normalized topics.
- A malformed or shared sensor configuration must fail before FAST-LIO, ego-swarm, setpoint publication, mode changes, or arming calls.
- Acceptance validation must keep both vehicles `armed: false`; another flight requires separate explicit user authorization.
- WSL shell scripts must remain LF-only.
- Every production behavior change must first be exercised by a failing test.

## File Structure

- Create `config/rflysim_sensor_uav1.json`: RflySim LiDAR configuration bound to CopterSim 1, SeqID 0, UDP port 9999.
- Create `config/rflysim_sensor_uav2.json`: RflySim LiDAR configuration bound to CopterSim 2, SeqID 10, UDP port 10009.
- Modify `config/stage7_live_slam_ego_swarm.json`: replace shared inputs with explicit bridge identities, raw topics, normalized topics, scan layout, and readiness limits.
- Modify `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py`: validate bridge/config identity and publish a latched JSON identity topic.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py`: ROS-independent cloud schema validation and byte conversion.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py`: ROS wrapper around the pure cloud contract.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py`: dry-run/live readiness report generation and report validation.
- Modify `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch`: launch adapters and bind each FAST-LIO instance to its own normalized inputs.
- Modify `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`: install the new executable scripts.
- Modify `scripts/wsl/stage7_live_fastlio_dual.sh`: launch two bridges, reject shared configuration, run readiness prechecks, then launch FAST-LIO.
- Modify `scripts/wsl/stage7_live_ego_swarm_dual.sh`: require a valid current-run readiness report.
- Modify `scripts/wsl/stage7_live_slam_ego_swarm_flight.sh`: require the same report before any setpoint or arm-capable process starts.
- Modify `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py`: report isolated sensor layers and readiness state.
- Create `tests/stage7_dual_sensor_config_check.py`: offline bridge/config isolation checks.
- Create `tests/stage7_cloud_contract_check.py`: exact raw-schema conversion and rejection tests.
- Create `tests/stage7_sensor_readiness_check.py`: readiness and stale-report tests.
- Modify `scripts/validate_stage7.ps1`: run the new tests and freeze all fail-closed contracts.

---

### Task 1: Freeze Independent Bridge Configuration

**Files:**
- Create: `tests/stage7_dual_sensor_config_check.py`
- Create: `config/rflysim_sensor_uav1.json`
- Create: `config/rflysim_sensor_uav2.json`
- Modify: `config/stage7_live_slam_ego_swarm.json`

**Interfaces:**
- Consumes: RflySim `VisionSensors` JSON fields `SeqID`, `TypeID`, `TargetCopter`, `DataWidth`, `DataHeight`, `DataCheckFreq`, and `SendProtocol`.
- Produces: `fast_lio.bridges[]` entries with `uav_id`, `copter_id`, `config`, `sensor_seq_id`, `udp_port`, `raw_lidar_topic`, `raw_imu_topic`, `lidar_topic`, `imu_topic`, and `identity_topic`.

- [ ] **Step 1: Write the failing isolation test**

```python
def validate(stage7, sensor_configs):
    bridges = stage7["fast_lio"]["bridges"]
    assert len(bridges) == 2
    for field in ("copter_id", "sensor_seq_id", "udp_port", "raw_lidar_topic",
                  "raw_imu_topic", "lidar_topic", "imu_topic", "identity_topic"):
        assert len({bridge[field] for bridge in bridges}) == 2, field
    for bridge in bridges:
        sensor = sensor_configs[bridge["uav_id"]]["VisionSensors"][0]
        assert sensor["TargetCopter"] == bridge["copter_id"]
        assert sensor["SeqID"] == bridge["sensor_seq_id"]
        assert sensor["SendProtocol"][5] == bridge["udp_port"]
```

The script loads paths supplied by `--config`, `--uav1-sensor`, and
`--uav2-sensor`, calls `validate`, and exits nonzero on the current shared
configuration.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python tests/stage7_dual_sensor_config_check.py --config config/stage7_live_slam_ego_swarm.json --uav1-sensor config/rflysim_sensor_uav1.json --uav2-sensor config/rflysim_sensor_uav2.json
```

Expected: FAIL because the two sensor configs and `fast_lio.bridges` do not yet exist.

- [ ] **Step 3: Add the minimal isolated configurations**

Create one TypeID 23 sensor in each config. Use:

```json
{"uav1": {"SeqID": 0, "TargetCopter": 1, "SendProtocol": [1,127,0,0,1,9999,0,0]},
 "uav2": {"SeqID": 10, "TargetCopter": 2, "SendProtocol": [1,127,0,0,1,10009,0,0]}}
```

Both sensors use `DataWidth: 64`, `DataHeight: 272`, `DataCheckFreq: 10`,
`SensorPosXYZ: [0,0,-0.1]`, identity rotation, and a 0.1 second scan period.
Update Stage 7 config so UAV1 uses `/rflysim/sensor0/mid360_lidar` and
`/uav1/rflysim/imu_raw`, while UAV2 uses `/rflysim/sensor10/mid360_lidar` and
`/uav2/rflysim/imu_raw`; normalized outputs are `/uavN/rflysim/lidar` and
`/uavN/rflysim/imu`.

- [ ] **Step 4: Run the test and verify GREEN**

Run the command from Step 2.

Expected: PASS and print both distinct bridge identities.

- [ ] **Step 5: Commit**

```powershell
git add tests/stage7_dual_sensor_config_check.py config/rflysim_sensor_uav1.json config/rflysim_sensor_uav2.json config/stage7_live_slam_ego_swarm.json
git commit -m "fix: isolate stage7 sensor configuration"
```

### Task 2: Publish and Validate Bridge Identity

**Files:**
- Modify: `tests/stage7_sensor_bridge_import_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py`

**Interfaces:**
- Consumes: `validate_sensor_config(config_path: Path, copter_id: int, sensor_seq_id: int, udp_port: int) -> dict` arguments.
- Produces: `build_identity(args, sensor: dict, target_ip: str) -> dict` and a latched `std_msgs/String` message on `--identity-topic`.

- [ ] **Step 1: Add failing pure-function tests**

```python
sensor = module.validate_sensor_config(config_path, 2, 10, 10009)
identity = module.build_identity(args, sensor, "127.0.0.1")
assert identity["copter_id"] == 2
assert identity["sensor_seq_id"] == 10
assert identity["udp_port"] == 10009
assert identity["raw_lidar_topic"] == "/rflysim/sensor10/mid360_lidar"

with expect_failure("TargetCopter"):
    module.validate_sensor_config(config_path, 1, 10, 10009)
```

Keep the existing SDK-path/import checks.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python tests/stage7_sensor_bridge_import_check.py --module future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py --psp-path D:\PX4PSP --config config/rflysim_sensor_uav2.json
```

Expected: FAIL because `validate_sensor_config` and `build_identity` are absent.

- [ ] **Step 3: Implement validation and the latched identity publisher**

Add arguments `--sensor-seq-id`, `--udp-port`, `--raw-lidar-topic`,
`--raw-imu-topic`, and `--identity-topic`. Validate the JSON before importing
or requesting SDK sensors. After ROS initialization, publish sorted JSON once
with `rospy.Publisher(identity_topic, String, queue_size=1, latch=True)` and
keep the process alive. A mismatch raises `ValueError` and exits 1 before
`sendReqToUE4`.

- [ ] **Step 4: Run the focused and existing checks**

Run the command from Step 2 and:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_stage7.ps1
```

Expected: focused test PASS; Stage 7 may still fail only for files deliberately introduced by later tasks, not bridge identity behavior.

- [ ] **Step 5: Commit**

```powershell
git add tests/stage7_sensor_bridge_import_check.py future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py
git commit -m "fix: identify rflysim sensor bridge sources"
```

### Task 3: Convert RflySim Clouds to the FAST-LIO Contract

**Files:**
- Create: `tests/stage7_cloud_contract_check.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `convert_cloud(data: bytes, fields: list[dict], width: int, height: int, point_step: int, layout_width: int, layout_height: int, scan_period_sec: float) -> ConvertedCloud`.
- Produces: `ConvertedCloud(data: bytes, fields: tuple[FieldSpec, ...], point_step: int, accepted_points: int, time_span_sec: float)` with fields `x`, `y`, `z`, `intensity`, `t`, `reflectivity`, `ring`, `ambient`, and `range` matching `ouster_ros::Point` offsets and datatypes.

- [ ] **Step 1: Write failing byte-level conversion tests**

Build a 2-by-2 raw cloud with `struct.pack("<ffff", x, y, z, seg)` and assert:

```python
converted = module.convert_cloud(raw, RAW_FIELDS, 4, 1, 16, 2, 2, 0.1)
assert [f.name for f in converted.fields] == [
    "x", "y", "z", "intensity", "t", "reflectivity", "ring", "ambient", "range"
]
assert converted.accepted_points == 4
assert converted.time_span_sec == 0.1
assert read_t_values(converted) == sorted(read_t_values(converted))
assert read_ring_values(converted) == [0, 1, 0, 1]
```

Also assert rejection of NaN coordinates, incorrect `point_step`, mismatched
point count, missing `seg`, and non-positive scan period.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python tests/stage7_cloud_contract_check.py --module future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py
```

Expected: FAIL because the cloud contract module does not exist.

- [ ] **Step 3: Implement the pure converter**

Use `dataclasses`, `math.isfinite`, and `struct.Struct`. Publish the compact,
32-byte little-endian layout `x@0:f32`, `y@4:f32`, `z@8:f32`,
`intensity@12:f32`, `t@16:u32`, `reflectivity@20:u16`, `ring@22:u8`, one pad
byte, `ambient@24:u16`, two pad bytes, and `range@28:u32`. Compute:

```python
ring = point_index % layout_width
t_seconds = scan_period_sec * point_index / max(point_count - 1, 1)
range_mm = round(math.sqrt(x*x + y*y + z*z) * 1000.0)
intensity = max(0.0, float(seg))
reflectivity = min(65535, round(intensity))
ambient = 0
```

Encode `t` in nanoseconds as `uint32` because faster_lio divides Ouster `t` by
`1e6` to obtain milliseconds. Reject the entire scan on any malformed point;
do not silently filter it because filtering would change the configured scan
layout and timing.

- [ ] **Step 4: Implement the ROS wrapper**

The wrapper subscribes to `~input_topic`, publishes `sensor_msgs/PointCloud2`
to `~output_topic`, preserves the source header stamp, sets the configured
vehicle LiDAR frame, and publishes latched JSON diagnostics on
`~diagnostics_topic`. It imports conversion logic from
`rflysim_cloud_contract.py`; all ROS-only code remains outside the pure module.
Install both executable scripts in CMake.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
python tests/stage7_cloud_contract_check.py --module future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py
powershell -ExecutionPolicy Bypass -File scripts/validate_stage7.ps1
```

Expected: cloud tests PASS; Stage 7 has no cloud-schema contract failures.

- [ ] **Step 6: Commit**

```powershell
git add tests/stage7_cloud_contract_check.py future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt
git commit -m "feat: adapt rflysim clouds for faster-lio"
```

### Task 4: Add Fail-Closed Sensor Readiness Reports

**Files:**
- Create: `tests/stage7_sensor_readiness_check.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: Stage 7 config, bridge identity JSON, adapter diagnostic JSON, ROS publisher maps, timed LiDAR/IMU/odometry samples, MAVROS state, `run_id`, and `simulation_instance_id`.
- Produces: `validate_report(report: dict, expected_run_id: str, expected_instance_id: str, max_age_sec: float, now: float) -> list[str]` and a report with gates `identity`, `schema`, `freshness`, `isolation`, and `stationary_stability`.

- [ ] **Step 1: Write failing report validation tests**

```python
assert module.validate_report(valid_report, "run-1", "sim-1", 30.0, 110.0) == []
assert "shared raw_lidar_topic" in module.validate_report(shared_report, "run-1", "sim-1", 30.0, 110.0)
assert "stale report" in module.validate_report(valid_report, "run-1", "sim-1", 5.0, 110.0)
assert "simulation instance mismatch" in module.validate_report(valid_report, "run-1", "sim-2", 30.0, 110.0)
assert "vehicle already armed" in module.validate_report(armed_report, "run-1", "sim-1", 30.0, 110.0)
```

Also cover duplicate Copter IDs, SeqIDs, ports, identity topics, wrong
publishers, non-monotonic timestamps, and excessive stationary drift.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python tests/stage7_sensor_readiness_check.py --module future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py
```

Expected: FAIL because the readiness module does not exist.

- [ ] **Step 3: Implement pure report validation and dry-run output**

The report is `ready: true` only when all five named gates pass for both
vehicles and both MAVROS states show `armed: false`. Include `created_at`,
`run_id`, `simulation_instance_id`, bridge process start markers, observed
publishers, topic stamps, cloud time spans, and stationary deltas. Dry-run
creates a deterministic structural report but marks live evidence as
`not_executed`; it must never be accepted by `validate_report` for live use.

- [ ] **Step 4: Implement live sampling**

Use bounded `rospy.wait_for_message` calls and a continuous stability window
from config. Check finite position/orientation/velocity values, monotonic source
stamps, exact expected publishers from ROS master system state, and adapter
diagnostics with nonzero accepted scans. Any timeout writes a failure report and
returns nonzero.

- [ ] **Step 5: Extend the topic probe**

Replace the former shared-bridge exception with per-UAV identity, raw LiDAR,
raw IMU, normalized LiDAR, normalized IMU, adapter diagnostics, and readiness
report checks. Keep planner and arm layers false until readiness is accepted.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
python tests/stage7_sensor_readiness_check.py --module future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py
powershell -ExecutionPolicy Bypass -File scripts/validate_stage7.ps1
```

Expected: focused tests PASS; dry-run report is structurally valid but rejected as live authorization.

- [ ] **Step 7: Commit**

```powershell
git add tests/stage7_sensor_readiness_check.py future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt
git commit -m "feat: add stage7 sensor readiness gate"
```

### Task 5: Wire Dual Bridges, Adapters, and Arm Gates

**Files:**
- Modify: `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch`
- Modify: `scripts/wsl/stage7_live_fastlio_dual.sh`
- Modify: `scripts/wsl/stage7_live_ego_swarm_dual.sh`
- Modify: `scripts/wsl/stage7_live_slam_ego_swarm_flight.sh`
- Modify: `scripts/run_live_fastlio_dual.bat`
- Modify: `scripts/validate_stage7.ps1`

**Interfaces:**
- Consumes: isolated bridge config, normalized sensor topics, and `stage7_sensor_readiness.validate_report` output.
- Produces: a live FAST-LIO startup that can create a no-arm readiness report, plus planner/flight runners that require that exact report.

- [ ] **Step 1: Add failing launcher-contract assertions**

Extend `validate_stage7.ps1` to require:

```powershell
foreach ($topic in @('/uav1/rflysim/lidar','/uav1/rflysim/imu','/uav2/rflysim/lidar','/uav2/rflysim/imu')) {
    if ($fastLioLaunch -notmatch [regex]::Escape($topic)) { $contractErrors += "missing isolated FAST-LIO input: $topic" }
}
if ($fastLioRunner -notmatch '--copter-id 1' -or $fastLioRunner -notmatch '--copter-id 2') {
    $contractErrors += 'stage7 FAST-LIO runner must start two identified sensor bridges'
}
if ($flightRunner -notmatch 'stage7_sensor_readiness.py.+--validate') {
    $contractErrors += 'arm-capable runner must validate the current Stage 7 readiness report'
}
```

Require both new configs/tests/scripts in `$requiredPaths` and ban
`shared_rflysim_bridge` from Stage 7 runtime/config files.

- [ ] **Step 2: Run Stage 7 validation and verify RED**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_stage7.ps1
```

Expected: FAIL on isolated launch inputs, two bridge commands, and readiness enforcement.

- [ ] **Step 3: Wire the launch file**

Launch one `rflysim_pointcloud_adapter.py` per UAV with its own raw/output
topics, layout, scan period, frame, and diagnostics. Set FAST-LIO
`common/lid_topic` and `common/imu_topic` to normalized `/uavN/rflysim/...`
topics. Remove every shared sensor default.

- [ ] **Step 4: Wire the WSL runners**

The FAST-LIO runner starts both bridges with explicit config, Copter ID, SeqID,
port, identity topic, and ROS namespace; waits for both distinct identities and
raw topics; then launches adapters/FAST-LIO and runs no-arm readiness to a
run-scoped report. The ego-swarm and flight runners call readiness validation
with the current run and simulation instance before starting any planner,
setpoint bridge, mode request, or arm request.

- [ ] **Step 5: Verify dry-runs and all offline stages**

Run:

```powershell
cmd /c scripts\run_live_fastlio_dual.bat --dry-run
cmd /c scripts\run_live_ego_swarm_dual.bat --dry-run
cmd /c scripts\run_live_slam_ego_swarm_flight.bat --dry-run
powershell -ExecutionPolicy Bypass -File scripts/validate_stage0.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage1.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage2.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage2_1.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage3.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage4.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage5.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage5b.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage5c.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage5d.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage5e.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage6a.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage6b.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts/validate_stage7.ps1
```

Expected: all validators PASS; dry-runs mention two independent sensor sources and no arming side effects.

- [ ] **Step 6: Commit**

```powershell
git add future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch scripts/wsl/stage7_live_fastlio_dual.sh scripts/wsl/stage7_live_ego_swarm_dual.sh scripts/wsl/stage7_live_slam_ego_swarm_flight.sh scripts/run_live_fastlio_dual.bat scripts/validate_stage7.ps1
git commit -m "fix: gate stage7 on isolated localization"
```

### Task 6: Clean Restart and Live No-Arm Acceptance

**Files:**
- Runtime output: `logs/stage7_live/<run-id>/sensor_readiness.json`
- Runtime output: `logs/stage7_live/<run-id>/topic_probe.json`
- Runtime output: `logs/stage7_live/<run-id>/fastlio_dual.log`
- Modify only if a live defect is reproduced first by an offline failing test.

**Interfaces:**
- Consumes: completed offline implementation and user authorization to restart simulation.
- Produces: saved no-arm evidence for two independent, stationary localization chains.

- [ ] **Step 1: Verify exact cleanup targets**

List WSL distributions and Windows processes named `px4`, `CopterSim`,
`RflySim3D`, and `QGroundControl`. Confirm the targets belong to this simulation
before terminating them.

- [ ] **Step 2: Clean old runtime processes and restart base simulation**

Terminate the project WSL ROS environment and stale named simulator processes,
then run `scripts/start_two_uav.bat`. Do not start an arm-capable runner.

- [ ] **Step 3: Prove base state is safe**

Check `/uav1/mavros/state` and `/uav2/mavros/state` until both report
`connected: true`, `armed: false`, and `mode: MANUAL`. Abort on any armed state.

- [ ] **Step 4: Start isolated sensor/FAST-LIO readiness**

Run `scripts/run_live_fastlio_dual.bat`, capture both bridge identities and
publisher graphs, and wait for the complete stationary observation window.

- [ ] **Step 5: Validate saved evidence**

Run the readiness validator against the saved report and confirm:

```text
identity=pass schema=pass freshness=pass isolation=pass stationary_stability=pass
uav1.armed=false uav2.armed=false ready=true
```

Confirm the faster_lio log contains no missing point-field warnings and both
estimated positions remain within configured stationary limits.

- [ ] **Step 6: Re-run Stage 7 offline validation and inspect git state**

Run `scripts/validate_stage7.ps1`, `git diff --check`, and `git status --short`.
Logs remain untracked/ignored; source changes require tests and a separate
commit before acceptance.

- [ ] **Step 7: Commit any test-driven live correction**

If no correction was needed, do not create an empty commit. If a defect was
fixed through a new failing test, stage only those source/test files and commit:

```powershell
git commit -m "fix: harden stage7 live sensor readiness"
```

Do not arm either vehicle after acceptance.
