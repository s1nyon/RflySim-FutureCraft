# Dual-UAV TF / Frame Contract (Task 1A Audit Draft)

Audit date: 2026-08-24

Scope: source-level/static audit plus previously accepted run-scoped evidence; no new live stack was started.

Live parity: **NOT RE-VALIDATED IN THIS AUDIT**. `sim.ps1 status` reported no active stack, so the dynamic TF tree is **PENDING LIVE CONFIRMATION**.

## Evidence notation

- **[SOURCE-VERIFIED]**: directly established by current launch, adapter, dependency, or plugin source.
- **[ACCEPTED-LIVE]**: established by an already accepted run-scoped artifact; not fresh evidence from this audit.
- **[INFERRED]**: follows from multiple verified facts but was not observed directly on a running ROS graph.
- **[UNKNOWN]**: requires live or other direct evidence.

## A. Current Verified Contract

### A.1 Contract boundary

The current system has three distinct coordinate concepts. They must not be collapsed without an alignment measurement:

1. `uav1_camera_init` and `uav2_camera_init` are independent Faster-LIO localization origins.
2. MAVROS/PX4 navigation uses per-UAV `uavX_map`, `uavX_odom`, `uavX_*_ned`, and `uavX_base_link_frd` compatibility/convention frames, plus a separately produced PX4 local-position feedback message.
3. A competition/global frame does not currently exist as a measured shared physical frame.

There is no verified transform between the two Faster-LIO origins. The zero aliases `uavX_map -> uavX_odom -> uavX_camera_init` are per-UAV compatibility edges, not evidence of a shared origin between UAVs.

### A.2 Per-UAV frame roles

| Role | UAV1 | UAV2 | Current meaning | Evidence |
| --- | --- | --- | --- | --- |
| Faster-LIO localization/world | `uav1_camera_init` | `uav2_camera_init` | Independent local SLAM origin; dynamic TF parent | [SOURCE-VERIFIED] |
| Faster-LIO IMU/body | `uav1_body` | `uav2_body` | Body pose estimated by Faster-LIO; dynamic TF child | [SOURCE-VERIFIED] |
| MAVROS ROS body | `uav1_base_link` | `uav2_base_link` | FLU compatibility body, zero-aliased from Faster-LIO body | [SOURCE-VERIFIED] |
| LiDAR message frame | `uav1_lidar` | `uav2_lidar` | Adapter-assigned label for unchanged raw XYZ | [SOURCE-VERIFIED] |
| MAVROS map | `uav1_map` | `uav2_map` | Per-UAV ROS ENU map label used by MAVROS odometry plugin | [SOURCE-VERIFIED] |
| MAVROS odom | `uav1_odom` | `uav2_odom` | Per-UAV ROS ENU odom label, zero-aliased to local SLAM origin | [SOURCE-VERIFIED] |
| MAVROS parent NED | `uav1_odom_ned`, `uav1_map_ned` | `uav2_odom_ned`, `uav2_map_ned` | Convention-conversion targets used by MAVROS odometry | [SOURCE-VERIFIED] |
| MAVROS body FRD | `uav1_base_link_frd` | `uav2_base_link_frd` | Convention-conversion target used by MAVROS odometry | [SOURCE-VERIFIED] |

### A.3 Sensor and Faster-LIO contract

The active configuration loads the external Faster-LIO `mid360.yaml`, then overrides `mapping/extrinsic_T` to `[0, 0, 0.1]`. Effective values for both UAVs are:

| Parameter | Effective value |
| --- | --- |
| `common/lid_topic` | `/uav1/rflysim/lidar` or `/uav2/rflysim/lidar` |
| `common/imu_topic` | `/uav1/rflysim/imu` or `/uav2/rflysim/imu` |
| `mapping/extrinsic_T` | `[0, 0, 0.1]` |
| `mapping/extrinsic_R` | identity 3x3 |
| `mapping/extrinsic_est_en` | `false` |
| `publish/path_publish_en` | `false` |
| `publish/scan_publish_en` | `true` |
| `publish/scan_bodyframe_pub_en` | `true` |

Faster-LIO loads this translation into `offset_T_L_I` and applies `R_L_I * p_lidar + T_L_I` internally before producing IMU/body and world points. Therefore the verified LiDAR-to-IMU/body extrinsic is stored in Faster-LIO, not in the ROS TF edge. The current zero `uavX_base_link -> uavX_lidar` publisher is a compatibility alias. Faster-LIO does not consume that TF, so the current pipeline does not double-apply the 0.1 m translation.

The RflySim SDK publishes raw TypeID 23 cloud XYZ without a ROS-coordinate transform. With no `tf_cfg.yaml` loaded, it assigns the literal header `map` only as a visualization default. Existing accepted bridge logs confirm that the default branch was used. The project point-cloud adapter:

- preserves every accepted `x`, `y`, and `z` value;
- changes the byte layout from RflySim `x/y/z/seg` to the Ouster-compatible field layout;
- synthesizes scan-relative `t`, ring, intensity, and related fields;
- preserves the input header timestamp;
- replaces only the header frame string with `uavX_lidar`;
- performs no rotation or translation.

Thus `map -> uavX_lidar` at this boundary is a frame relabel, not a coordinate transform. The pipeline treats the numeric XYZ as LiDAR-local, and accepted flight behavior is consistent with that contract; a direct geometric frame observation is **UNKNOWN — requires live evidence**.

The SDK IMU message uses the generic header `imu`, simulation-aligned `imuStmp`, and explicit component mappings: acceleration `(-x,+y,-z)` and angular rate `(+x,-y,-z)`. `topic_tools/relay` preserves the message unchanged. The exact named physical convention behind the generic `imu` string is **UNKNOWN — requires live evidence/documented SDK convention**; Faster-LIO consumes the values as its IMU/body measurement.

Faster-LIO output behavior is source-verified:

| Output | Mathematical coordinates | Literal header | Timestamp |
| --- | --- | --- | --- |
| `/uavX/slam/odometry_raw` | Pose of IMU/body in that UAV's Faster-LIO local origin | `camera_init`; child `body` | Faster-LIO `lidar_end_time_` |
| `/uavX/slam/cloud_registered` | Points transformed into that UAV's Faster-LIO local origin | `camera_init` | `lidar_end_time_` |
| `/uavX/slam/cloud_registered_body` | Undistorted points transformed from LiDAR into Faster-LIO IMU/body with internal extrinsic | `body` | `lidar_end_time_` |
| `/uavX/slam/path` | Poses in that UAV's Faster-LIO local origin | `camera_init` | `Path.header.stamp` is initialized once with `ros::Time::now()`; each pose stamp uses `lidar_end_time_`; currently not published because `path_publish_en=false` |
| TF | Same pose as odometry | `uavX_camera_init -> uavX_body` | Odometry/`lidar_end_time_` stamp |

ROS namespaces do not modify string-valued message frame IDs. Consequently the raw odometry and registered-cloud headers remain generic even though their topics are UAV-specific. Only Faster-LIO's dynamic TF parent and child are parameterized per UAV.

### A.4 Odometry relay contract

For each UAV:

```text
/uavX/slam/odometry_raw
        -> odom_frame_relay
        -> /uavX/mavros/odometry/out
```

`odom_frame_relay.py` deep-copies the message and changes only:

- `header.frame_id`: `camera_init` -> `uavX_camera_init`
- `child_frame_id`: `body` -> `uavX_body`

Pose, twist, covariance, and timestamp are unchanged. This is **frame relabel / message adaptation, not a mathematical coordinate transform**.

### A.5 MAVROS topic direction and frame contract

The installed MAVROS version is 1.20.1. Its odometry plugin publishes private topic `in` and subscribes to private topic `out`; the names are relative to MAVROS/FCU, not an instruction to infer direction from English alone.

| Topic | ROS role | Data direction | Current message frames | Mathematical action |
| --- | --- | --- | --- | --- |
| `/uavX/mavros/odometry/out` | MAVROS subscriber; also tapped by EGO | ROS/Faster-LIO -> MAVROS -> FCU | `uavX_camera_init`, child `uavX_body` | The message itself is not transformed by the relay. MAVROS then looks up `uavX_odom_ned <- uavX_camera_init` and `uavX_base_link_frd <- uavX_body`, rotates pose/twist/covariance, and sends MAVLink `ODOMETRY` as `LOCAL_FRD`/`BODY_FRD`, estimator `VISION`. |
| `/uavX/mavros/odometry/in` | MAVROS publisher | FCU MAVLink `ODOMETRY` -> ROS | `uavX_map`, child `uavX_base_link` | MAVROS converts FCU NED/FRD data through `uavX_map_ned -> uavX_map` and `uavX_base_link_frd -> uavX_base_link`. Availability/data rate depend on FCU `ODOMETRY` output. |
| `/uavX/mavros/local_position/odom` | MAVROS local-position publisher | FCU `LOCAL_POSITION_NED(_COV)` -> ROS | source-configured generic `map`, child `base_link` | MAVROS converts PX4 local NED position/velocity to ROS ENU and expresses twist in the body frame. This is PX4/EKF local-navigation feedback, not the relayed Faster-LIO message. |

`rflysim_mavros_px4.launch` overrides only odometry-plugin `map_id_des`, `odom_parent_id_des`, and `odom_child_id_des`. It does not override local-position `frame_id` or `tf/child_frame_id`. Installed `px4_config.yaml` sets those to `map` and `base_link`, with `local_position/tf/send=false`. Those expected message headers are source-verified; a live `rostopic echo` is **PENDING LIVE CONFIRMATION**.

### A.6 EGO-Swarm contract

For UAV1 (`drone_id=0`) and UAV2 (`drone_id=1`):

- `~odom_world` and `~grid_map/odom` both resolve to `/uavX/mavros/odometry/out`.
- `~grid_map/cloud` resolves to `/uavX/slam/cloud_registered`.
- planner command output resolves to `/uavX/planning/pos_cmd`.
- both planners publish/subscribe the global topic `/broadcast_bspline`; its presence does not prove reliable inter-UAV collision avoidance or a shared localization origin.

EGO's odometry callbacks copy numeric pose/twist fields without inspecting `header.frame_id`. Its cloud callback converts and uses XYZ without TF lookup or header inspection. `grid_map/frame_id=world` is applied to published occupancy clouds, while `traj_server` hardcodes `PositionCommand.header.frame_id="world"`. Therefore current `world` is an internal label applied to each planner's own per-UAV Faster-LIO numeric space. It is not a transformed, measured, shared world.

The odometry and `cloud_registered` inputs are mathematically consistent per UAV because both are generated from the same Faster-LIO state/local origin and the relay does not alter odometry numbers. Their message headers are not contract-consistent (`uavX_camera_init` versus generic `camera_init`), and EGO succeeds only because it ignores those headers.

The old generic static publishers `world -> map` and `base_link -> camera_link` were removed in commit `163fcd9`. The current single-UAV launch explicitly documents their omission. Including that launch twice therefore does **not** currently duplicate those generic TF edges. Generic frame-label reuse still exists in messages and EGO outputs:

| Generic string | Current use | Current TF publisher? | Collision assessment |
| --- | --- | --- | --- |
| `world` | Both EGO grid-map outputs and both `PositionCommand` headers | No | Semantic collision/ambiguity: two independent local numeric spaces share one label |
| `map` | RflySim raw sensor default header; both MAVROS local-position odometry headers | No (`uavX_map` is used in TF) | Semantic collision/ambiguity; no current duplicate TF edge |
| `base_link` | Both MAVROS local-position odometry child strings | No (`uavX_base_link` is used in TF) | Semantic collision/ambiguity; `tf/send=false` prevents duplicate local-position TF publication |
| `camera_link` | No current active project launch use | No | No current collision; historical static edge removed |
| `camera_init`, `body` | Hardcoded Faster-LIO raw message headers | No generic TF; dynamic TF uses `uavX_*` | Message/TF naming inconsistency |
| `imu` | Both SDK IMU message headers | No | Semantic collision/ambiguity |

### A.7 Data / Frame Matrix

Rows marked accepted-live use the latest trusted run artifacts only for publisher isolation/timestamps; no header was freshly echoed in this audit.

| Data | Topic | Publisher | `header.frame_id` | `child_frame_id` | Actual coordinate semantics | Consumer |
| --- | --- | --- | --- | --- | --- | --- |
| UAV1 LiDAR raw | `/rflysim/sensor0/mid360_lidar` | `/uav1/rflysim_sensor_bridge` [ACCEPTED-LIVE] | `map` [SOURCE + accepted log branch] | n/a | XYZ passed through from TypeID 23; SDK says `map` is a visualization default, not a conversion. Intended LiDAR-local; direct geometric confirmation UNKNOWN | UAV1 point-cloud adapter |
| UAV1 LiDAR adapted | `/uav1/rflysim/lidar` | `/uav1/rflysim_pointcloud_adapter` [ACCEPTED-LIVE] | `uav1_lidar` | n/a | Same XYZ as raw; layout changed, no rotation/translation; source stamp preserved | UAV1 Faster-LIO |
| UAV1 IMU raw | `/uav1/rflysim/imu_raw` | `/uav1/rflysim_sensor_bridge` [ACCEPTED-LIVE] | `imu` | n/a | SDK sign-mapped IMU values; exact named convention UNKNOWN | `/uav1/rflysim_imu_relay` |
| UAV1 IMU | `/uav1/rflysim/imu` | `/uav1/rflysim_imu_relay` [ACCEPTED-LIVE] | `imu` (unchanged) | n/a | Identical relayed IMU message and simulation-aligned stamp | UAV1 Faster-LIO |
| UAV1 Faster-LIO raw odom | `/uav1/slam/odometry_raw` | `/uav1/slam/laserMapping` | `camera_init` | `body` | UAV1 body pose/twist in UAV1 local SLAM origin; `lidar_end_time_` | odom relay |
| UAV1 registered cloud | `/uav1/slam/cloud_registered` | `/uav1/slam/laserMapping` | `camera_init` | n/a | XYZ transformed into UAV1 local SLAM origin; `lidar_end_time_` | UAV1 EGO grid map |
| UAV1 registered body cloud | `/uav1/slam/cloud_registered_body` | `/uav1/slam/laserMapping` | `body` | n/a | XYZ in Faster-LIO IMU/body after internal LiDAR extrinsic; `lidar_end_time_` | No active project planner consumer found |
| UAV1 MAVROS odometry out | `/uav1/mavros/odometry/out` | `/uav1/slam/odom_frame_relay` | `uav1_camera_init` | `uav1_body` | Same numeric pose/twist/covariance/stamp as raw odom; labels only changed | MAVROS odometry plugin and UAV1 EGO |
| UAV1 MAVROS local-position odom | `/uav1/mavros/local_position/odom` | `/uav1/mavros` local-position plugin | `map` [SOURCE; live pending] | `base_link` [SOURCE; live pending] | PX4/EKF local navigation converted NED -> ENU; FCU-synchronized stamp | mission executor/watchdog/recorders |
| UAV1 MAVROS odometry in | `/uav1/mavros/odometry/in` | `/uav1/mavros` odometry plugin | `uav1_map` | `uav1_base_link` | FCU MAVLink ODOMETRY converted NED/FRD -> configured ROS frames | diagnostics/legacy mission config; actual live production UNKNOWN |
| UAV1 EGO odom input | `/uav1/mavros/odometry/out` | odom relay | `uav1_camera_init` | `uav1_body` | UAV1 local SLAM numeric space; EGO ignores frame strings | `/uav1/planner/rflysim_ego_swarm_node` |
| UAV1 EGO cloud input | `/uav1/slam/cloud_registered` | UAV1 Faster-LIO | `camera_init` | n/a | Same UAV1 local SLAM numeric space; EGO ignores frame string | `/uav1/planner/rflysim_ego_swarm_node` |
| UAV1 EGO position command | `/uav1/planning/pos_cmd` | `/uav1/planner/rflysim_traj_server` | `world` | n/a | UAV1 local SLAM/planner numeric space, not shared world; stamp=`ros::Time::now()` | project setpoint bridge -> MAVROS raw local setpoint |
| UAV2 LiDAR raw | `/rflysim/sensor10/mid360_lidar` | `/uav2/rflysim_sensor_bridge` [ACCEPTED-LIVE] | `map` [SOURCE + accepted log branch] | n/a | XYZ passed through from TypeID 23; SDK says `map` is a visualization default, not a conversion. Intended LiDAR-local; direct geometric confirmation UNKNOWN | UAV2 point-cloud adapter |
| UAV2 LiDAR adapted | `/uav2/rflysim/lidar` | `/uav2/rflysim_pointcloud_adapter` [ACCEPTED-LIVE] | `uav2_lidar` | n/a | Same XYZ as raw; layout changed, no rotation/translation; source stamp preserved | UAV2 Faster-LIO |
| UAV2 IMU raw | `/uav2/rflysim/imu_raw` | `/uav2/rflysim_sensor_bridge` [ACCEPTED-LIVE] | `imu` | n/a | SDK sign-mapped IMU values; exact named convention UNKNOWN | `/uav2/rflysim_imu_relay` |
| UAV2 IMU | `/uav2/rflysim/imu` | `/uav2/rflysim_imu_relay` [ACCEPTED-LIVE] | `imu` (unchanged) | n/a | Identical relayed IMU message and simulation-aligned stamp | UAV2 Faster-LIO |
| UAV2 Faster-LIO raw odom | `/uav2/slam/odometry_raw` | `/uav2/slam/laserMapping` | `camera_init` | `body` | UAV2 body pose/twist in UAV2 local SLAM origin; `lidar_end_time_` | odom relay |
| UAV2 registered cloud | `/uav2/slam/cloud_registered` | `/uav2/slam/laserMapping` | `camera_init` | n/a | XYZ transformed into UAV2 local SLAM origin; `lidar_end_time_` | UAV2 EGO grid map |
| UAV2 registered body cloud | `/uav2/slam/cloud_registered_body` | `/uav2/slam/laserMapping` | `body` | n/a | XYZ in Faster-LIO IMU/body after internal LiDAR extrinsic; `lidar_end_time_` | No active project planner consumer found |
| UAV2 MAVROS odometry out | `/uav2/mavros/odometry/out` | `/uav2/slam/odom_frame_relay` | `uav2_camera_init` | `uav2_body` | Same numeric pose/twist/covariance/stamp as raw odom; labels only changed | MAVROS odometry plugin and UAV2 EGO |
| UAV2 MAVROS local-position odom | `/uav2/mavros/local_position/odom` | `/uav2/mavros` local-position plugin | `map` [SOURCE; live pending] | `base_link` [SOURCE; live pending] | PX4/EKF local navigation converted NED -> ENU; FCU-synchronized stamp | mission executor/watchdog/recorders |
| UAV2 MAVROS odometry in | `/uav2/mavros/odometry/in` | `/uav2/mavros` odometry plugin | `uav2_map` | `uav2_base_link` | FCU MAVLink ODOMETRY converted NED/FRD -> configured ROS frames | diagnostics/legacy mission config; actual live production UNKNOWN |
| UAV2 EGO odom input | `/uav2/mavros/odometry/out` | odom relay | `uav2_camera_init` | `uav2_body` | UAV2 local SLAM numeric space; EGO ignores frame strings | `/uav2/planner/rflysim_ego_swarm_node` |
| UAV2 EGO cloud input | `/uav2/slam/cloud_registered` | UAV2 Faster-LIO | `camera_init` | n/a | Same UAV2 local SLAM numeric space; EGO ignores frame string | `/uav2/planner/rflysim_ego_swarm_node` |
| UAV2 EGO position command | `/uav2/planning/pos_cmd` | `/uav2/planner/rflysim_traj_server` | `world` | n/a | UAV2 local SLAM/planner numeric space, not shared world; stamp=`ros::Time::now()` | project setpoint bridge -> MAVROS raw local setpoint |

### A.8 Project static TF inventory

The final CLI argument is a period in milliseconds, not Hz. ROS 1 `tf/static_transform_publisher` periodically republishes these edges on `/tf`; these are not latched `/tf_static` broadcasters.

| Publisher | Parent | Child | Translation m | Rotation CLI (`yaw,pitch,roll`) | Period / nominal rate | UAV | Class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/uav1/slam/laser_base_link` | `uav1_base_link` | `uav1_lidar` | `0,0,0` | `0,0,0` | 100 ms / 10 Hz | 1 | D/E: compatibility alias; not physical extrinsic |
| `/uav1/slam/base_link_body` | `uav1_body` | `uav1_base_link` | `0,0,0` | `0,0,0` | 100 ms / 10 Hz | 1 | D: Faster-LIO body -> MAVROS FLU alias |
| `/uav1/slam/slam_mavros` | `uav1_odom` | `uav1_camera_init` | `0,0,0` | `0,0,0` | 100 ms / 10 Hz | 1 | C: per-UAV localization-origin alias |
| `/uav1/slam/odom_map` | `uav1_map` | `uav1_odom` | `0,0,0` | `0,0,0` | 1000 ms / 1 Hz | 1 | C/D: MAVROS map/odom compatibility alias |
| `/uav1/slam/odom_ned` | `uav1_odom` | `uav1_odom_ned` | `0,0,0` | `pi/2,0,pi` | 1000 ms / 1 Hz | 1 | B: ENU/FLU convention -> NED/FRD parent orientation |
| `/uav1/slam/map_ned` | `uav1_map` | `uav1_map_ned` | `0,0,0` | `pi/2,0,pi` | 1000 ms / 1 Hz | 1 | B: ENU map -> NED map orientation |
| `/uav1/slam/base_link_frd` | `uav1_base_link` | `uav1_base_link_frd` | `0,0,0` | `0,0,pi` | 100 ms / 10 Hz | 1 | B: FLU -> FRD body orientation |
| `/uav2/slam/laser_base_link` | `uav2_base_link` | `uav2_lidar` | `0,0,0` | `0,0,0` | 100 ms / 10 Hz | 2 | D/E: compatibility alias; not physical extrinsic |
| `/uav2/slam/base_link_body` | `uav2_body` | `uav2_base_link` | `0,0,0` | `0,0,0` | 100 ms / 10 Hz | 2 | D: Faster-LIO body -> MAVROS FLU alias |
| `/uav2/slam/slam_mavros` | `uav2_odom` | `uav2_camera_init` | `0,0,0` | `0,0,0` | 100 ms / 10 Hz | 2 | C: per-UAV localization-origin alias |
| `/uav2/slam/odom_map` | `uav2_map` | `uav2_odom` | `0,0,0` | `0,0,0` | 1000 ms / 1 Hz | 2 | C/D: MAVROS map/odom compatibility alias |
| `/uav2/slam/odom_ned` | `uav2_odom` | `uav2_odom_ned` | `0,0,0` | `pi/2,0,pi` | 1000 ms / 1 Hz | 2 | B: ENU/FLU convention -> NED/FRD parent orientation |
| `/uav2/slam/map_ned` | `uav2_map` | `uav2_map_ned` | `0,0,0` | `pi/2,0,pi` | 1000 ms / 1 Hz | 2 | B: ENU map -> NED map orientation |
| `/uav2/slam/base_link_frd` | `uav2_base_link` | `uav2_base_link_frd` | `0,0,0` | `0,0,pi` | 100 ms / 10 Hz | 2 | B: FLU -> FRD body orientation |

There is no class-A physical sensor extrinsic in the current project TF inventory. The physical LiDAR-to-IMU/body offset is represented inside Faster-LIO. There is also no current project-side generic `world -> map` or `base_link -> camera_link` static publisher.

### A.9 Current source-provable TF trees

Every edge below is **[SOURCE-VERIFIED]**. The dynamic edge is configured in Faster-LIO source/launch. None was freshly observed in this audit, so runtime multiple-parent, duplicate-publisher, timestamp, and cross-UAV checks remain **PENDING LIVE CONFIRMATION**.

```text
UAV1
uav1_map
|--[zero static]--> uav1_odom
|  |--[zero static]--> uav1_camera_init
|  |  `--[dynamic Faster-LIO pose]--> uav1_body
|  |     `--[zero static]--> uav1_base_link
|  |        |--[zero compatibility alias]--> uav1_lidar
|  |        `--[FLU/FRD static rotation]--> uav1_base_link_frd
|  `--[ENU/NED static rotation]--> uav1_odom_ned
`--[ENU/NED static rotation]--> uav1_map_ned
```

```text
UAV2
uav2_map
|--[zero static]--> uav2_odom
|  |--[zero static]--> uav2_camera_init
|  |  `--[dynamic Faster-LIO pose]--> uav2_body
|  |     `--[zero static]--> uav2_base_link
|  |        |--[zero compatibility alias]--> uav2_lidar
|  |        `--[FLU/FRD static rotation]--> uav2_base_link_frd
|  `--[ENU/NED static rotation]--> uav2_odom_ned
`--[ENU/NED static rotation]--> uav2_map_ned
```

```text
Shared/generic TF
world       (no current project TF edge)
map         (no current project TF edge)
base_link   (no current project TF edge)
camera_link (no current project TF edge)

uav1_* and uav2_* trees have no source-level cross-edge.
There is no source-level transform between uav1_camera_init and uav2_camera_init.
```

### A.10 Findings

#### Confirmed correct for the protected baseline

- Sensor topics, adapter topics, Faster-LIO instances, planner inputs, and MAVROS endpoints are isolated by UAV.
- Faster-LIO dynamic TF strings are parameterized as `uavX_camera_init -> uavX_body`.
- Registered cloud and relayed odometry numbers use the same per-UAV Faster-LIO local coordinates.
- MAVROS has the per-UAV NED/FRD TF paths its odometry plugin requests.
- The 0.1 m LiDAR-to-IMU/body translation is applied internally once by Faster-LIO.
- Old duplicated generic EGO static transforms are absent from the current launch.

#### Suspicious but not proven wrong

- Zero `uavX_base_link -> uavX_lidar` looks physical by name but is only an alias; a general TF consumer would not recover the Faster-LIO internal 0.1 m extrinsic.
- Both planners label independent local spaces as `world`.
- MAVROS local-position feedback for both UAVs uses generic `map`/`base_link` message strings.
- The SDK IMU uses generic `imu`, and its exact named physical axis convention is not documented in this project.

#### Confirmed inconsistencies

- Faster-LIO hardcodes generic `camera_init`/`body` in odometry and cloud/path messages while publishing UAV-specific dynamic TF names.
- The odometry relay corrects only odometry strings. `cloud_registered` remains `camera_init`, even though EGO odometry is labeled `uavX_camera_init`.
- EGO uses the two inputs as if co-framed because it ignores both headers; numerical consistency exists, but the ROS message-level frame contract is inconsistent.
- RflySim's raw cloud header `map` is explicitly a visualization default and no coordinate transform is performed before the adapter relabels it `uavX_lidar`.

#### Unknown / needs live evidence

- Fresh `view_frames`, `tf_monitor`, and `tf_echo` results, including multiple parents, duplicate runtime broadcasters, or cross-UAV contamination.
- Live message headers for MAVROS local-position odometry and FCU odometry input.
- Whether `/uavX/mavros/odometry/in` currently receives FCU `ODOMETRY` at a useful rate.
- Direct geometric confirmation that raw TypeID 23 XYZ is LiDAR-local under the currently installed simulator/SDK build.
- Exact physical naming of the SDK's sign-mapped IMU axes.
- Cross-topic timestamp skew during a current run; accepted artifacts prove monotonic/current samples but are not fresh TF evidence.

### A.11 Answers to the required questions

1. UAV1 Faster-LIO's true local/world frame is the numeric local origin named by its configured TF parent `uav1_camera_init`; raw output headers still say `camera_init`.
2. UAV2 Faster-LIO's true local/world frame is the independent numeric local origin named by its configured TF parent `uav2_camera_init`; raw output headers still say `camera_init`.
3. No. There is no measured transform or source-level edge proving the two origins share one physical origin.
4. `/uavX/slam/odometry_raw` literally carries `header.frame_id=camera_init` and `child_frame_id=body`; its numbers belong to UAV X's own Faster-LIO local/body frames.
5. `/uavX/mavros/odometry/out` carries `uavX_camera_init`, child `uavX_body`. The relay does not transform the data. MAVROS performs the actual convention rotations only when converting it to MAVLink for PX4.
6. `/uavX/mavros/local_position/odom` is PX4 local-navigation feedback converted by MAVROS from NED to ENU, with source-configured generic `map`/`base_link`. It is not the relayed Faster-LIO message and its origin belongs to the PX4/EKF local navigation state.
7. `/uavX/slam/cloud_registered` XYZ is in UAV X's Faster-LIO local origin, while its literal header is generic `camera_init`.
8. `/uavX/slam/cloud_registered_body` XYZ is in Faster-LIO's IMU/body after internal LiDAR extrinsic application, while its literal header is generic `body`.
9. Yes numerically, per UAV: both come from the same Faster-LIO state/local origin. No at strict message-contract level: their frame strings differ and EGO performs no TF validation/conversion.
10. Current launch does not publish the historical `world -> map` or `base_link -> camera_link` static transforms, so it does not currently duplicate those TF edges. It still reuses `world` for both independent EGO outputs and reuses generic `map`/`base_link` in both MAVROS local-position messages, creating semantic frame-label collisions.
11. Yes. `body -> base_link`, `odom -> camera_init`, `map -> odom`, and zero `base_link -> lidar` are aliases/compatibility edges; the NED/FRD edges are convention rotations. The zero LiDAR edge is not the physical 0.1 m sensor extrinsic.
12. The current protected baseline needs an explicit per-UAV frame contract, not an invented unified global TF. A unified competition frame is only justified after a real alignment source exists.

### A.12 Live verification tooling

`frame_contract_probe.py` is a bounded, read-only ROS diagnostic for the next live-verification task. Run `rosrun multi_uav_mission frame_contract_probe.py --duration 8` only after a clean owned stack is READY; it writes ignored Markdown and JSON reports under `logs/frame_contract_probe/<UTC timestamp>/`, covering audited topic headers/stamps and graph endpoints, TF lookups and direct broadcasters, generic message-label reuse, cross-UAV edges, and timestamp statistics. It does not publish, set parameters, modify TF, or act as a lifecycle health gate.

## B. Proposed Target Contract

Everything in this section is **PROPOSED**, not current behavior.

### B.1 Preserve per-UAV localization truth

- Keep `uav1_camera_init` and `uav2_camera_init` as independent localization frames until an alignment transform is measured or otherwise derived.
- Make every localization-derived odometry, registered cloud, occupancy output, and planner command identify its corresponding per-UAV localization frame.
- Do not use ROS namespace as a substitute for an explicit frame string.
- Do not add a zero transform between the two localization origins.

### B.2 Make aliases explicit

- Document `uavX_odom -> uavX_camera_init` and `uavX_map -> uavX_odom` as per-UAV numeric-origin aliases required by current MAVROS integration.
- Treat `uavX_base_link -> uavX_lidar` as compatibility-only until the physical TF direction/value is independently derived and validated.
- Keep the validated Faster-LIO `extrinsic_T=[0,0,0.1]` unchanged unless a dedicated regression proves a replacement.

### B.3 Remove message-level generic ambiguity in a later change-gated task

A future minimal runtime patch may parameterize/relabel:

- Faster-LIO registered cloud headers to `uavX_camera_init`;
- MAVROS local-position message frames to `uavX_map`/`uavX_base_link`;
- EGO occupancy and position-command labels to the per-UAV localization frame.

Such a patch must not change numeric coordinates and must pass Stage 7/8 plus the live no-arm and flight regression ladder because launch/adapters are change-gated and the baseline is protected.

### B.4 Competition/global frame

```text
competition_world: RESERVED / FUTURE
```

It must remain absent until one of these supplies a defensible transform for each UAV:

- RflySim ground truth aligned to the course;
- OpenVINS or another global/local alignment;
- multi-UAV localization alignment;
- known and verified spawn transforms.

The future relationship should be expressed as measured transforms such as `competition_world -> uavX_camera_init`; the exact direction, ownership, and update policy are not selected in this audit.

### B.5 Task 1B implementation status

| Priority | Candidate | Files/area | Risk and required validation |
| --- | --- | --- | --- |
| P0 | **IMPLEMENTED OFFLINE / LIVE PENDING:** the read-only, run-scoped frame probe records publishers/subscribers, bounded header/stamp statistics, TF parent ownership, duplicate edges, and cross-UAV edges | New project diagnostic + focused offline test; no launch wiring | Offline validation is complete. Runtime claims remain pending one manually invoked capture on an already healthy no-arm stack. |
| P1 | Correct message labels without changing numbers: per-UAV registered-cloud label, MAVROS local-position frame params, and per-UAV EGO output/command label | Project adapter/launch; possibly a narrowly reviewed upstream EGO parameterization | Medium/high protected-baseline risk. Require design review, focused tests, Stage 7/8, no-arm header/TF capture, single-UAV, dual-UAV, short navigation, full route, repeated fresh instances. |
| P2 | Resolve the zero LiDAR TF alias and introduce `competition_world` only after deriving physical/global transforms | Frame adapter/launch and an alignment provider; do not patch Faster-LIO extrinsic casually | High coordinate/regression risk. Require independent transform math, double-application tests, ground-truth comparison, and the full PBL-1 ladder. |
