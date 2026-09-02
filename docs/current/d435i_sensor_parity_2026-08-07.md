# D435i 传感器对齐 28comsim UAV_demo（2026-08-07）

## 结论先行

28comsim `UAV_demo` 的 FS-310 无人机**确实搭载 Intel RealSense D435i**（RGB + 深度），此外还有下视单目相机和 Mid360 雷达/IMU。本项目此前两架无人机的仿真载荷只有 Mid360，**缺少 D435i**；EGO-Swarm 之所以能运行，是因为 EGO 的地图主要靠激光点云（`/cloud_registered`）构建，深度相机只是可选的辅助输入，并非运行前提。本次已按 28comsim 的方式补齐传感器载荷并把深度接入规划器。

## 严格比对

### 飞机模型

| 项 | 28comsim UAV_demo | future_aircraft_sim |
| --- | --- | --- |
| 机型 | FS-310（`CLASS_3D_ID=310`） | 同一 FS-310（SITL 入口复用 `28com_SITL/UAVSITL.bat`） |
| PX4 机架 | `PX4SitlFrame=iris` | 相同（同一 SITL 脚本） |
| 仿真模式 | `SimMode=2`（PX4_SITL_RFLY），`UDPSIMMODE=Mavlink_Vision` | 相同 |

两工程的飞机模型本来就是同一套，因此差异全部集中在传感器载荷。

### 传感器载荷

| 传感器 | 28com 真机（`start.sh`） | 28com 仿真（`Config.json`） | 本项目（本次修改前） | 本项目（本次修改后） |
| --- | --- | --- | --- | --- |
| Mid360 雷达 + IMU | 是（livox 驱动 → Faster-LIO） | 是（SeqID 0，`[0,0,-0.1]`，端口 9999） | 是（UAV1 SeqID 0/9999，UAV2 SeqID 10/10009） | 保持不变 |
| D435i RGB | 是（`/camera/color/image_raw` → object_det） | 是（SeqID 1，`[0.1,0.04,0]`，端口 9998） | **无** | 已加（UAV1 SeqID 1/9998，UAV2 SeqID 11/10008） |
| D435i 深度 | 是（→ ego-planner 深度滤波） | **无 TypeID 2**（launch 的 `depth_topic=/rflysim/sensor1` 在仿真中实际无消息） | **无** | 已加（UAV1 SeqID 3/9996，UAV2 SeqID 13/10006，`[0.1,0.04,0]`，`otherParams=[0.3,12,0.001]`） |
| 下视单目 | 是（usb_cam → ArUco/二维码） | 是（SeqID 2，`[0,0,0.1]` 俯仰 -90°，端口 9997） | **无** | 已加（UAV1 SeqID 2/9997，UAV2 SeqID 12/10007） |

注：28com 仿真 `Config.json` 中前向相机是 TypeID 1（RGB），并没有 TypeID 2 深度传感器；其 `FS-J310_ego-planner.launch` 中 `depth_topic=/rflysim/sensor1` 在仿真里实际订阅不到有效深度（真实 topic 是 `/rflysim/sensor1/img_rgb`）。也就是说 **28com 的仿真同样只靠点云跑 EGO**，本项目之前的行为与 28com 仿真一致；真正的深度链路只在 28com 真机（realsense2_camera）上存在。本次修改把这条链路也补进了仿真。

## 没有 D435i 时 EGO-Swarm 怎么跑的

EGO-Planner 的 grid_map 有两个独立输入：

1. `grid_map/cloud`：外部点云（本项目是 FAST-LIO 输出的 `/uavX/slam/cloud_registered`），用于构建占用图——这是主输入，**不依赖深度相机**。
2. `grid_map/depth` + `grid_map/odom`：深度图投影/滤波，用于补充点云稀疏区域与清理射线空间——可选。

本项目之前的 launch 把 `use_depth_filter` 设为 true，但 `depth_topic` 指向不存在的 `/uav1/rflysim/sensor1`，因此深度回调从未触发，规划完全由点云驱动。这与 28com 仿真实际一致，不属于“没传感器硬跑”。真正受影响的是依赖深度图像的功能：

- ego-swarm 的 `planner/drone_detect`（用深度图检测其他无人机并修正相对位姿）——本项目未启用，改用 mid360 点云感知（grid_map 标记对方 + `EMERGENCY_STOP`）兜底；
- 目标检测（object_det/YOLO，用 D435i RGB）——本项目当前任务不需要。

## 本次修改

- `config/rflysim_sensor_uav1.json` / `config/rflysim_sensor_uav2.json`：加入 D435i RGB、D435i 深度、下视相机，与 28com 仿真载荷一致（额外补上 28com 仿真缺失的 TypeID 2 深度）。
- `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch`：新增 RGB/深度/下视话题 relay，把 `/rflysim/sensor*` 的绝对话题转发到 `/uav*/rflysim/sensor*`。
- `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch`：`depth_topic` 指向真实深度话题 `/uav*/rflysim/sensor*/img_depth`；`pose_type=2`（ODOMETRY 模式）保持不变，深度图像直接与 `grid_map/odom` 同步，无需额外 camera pose 发布。
- `tests/stage7_dual_sensor_config_check.py`：契约检查改为多传感器校验（mid360 + D435i RGB/深度 + 下视），并新增缺失深度、深度安装位错误等回归用例。
- `config/stage7_live_slam_ego_swarm.json`：补充每机 `raw_rgb_topic` / `raw_depth_topic` / `raw_bottom_topic` / `depth_topic` / `planner_depth_topic` 字段。

## 验证状态与待办

已完成（离线）：

- 两个传感器配置 JSON 与 stage7 配置 JSON 可被 `json.loads` 解析；
- `stage7_dual_sensor_config_check.py`、`stage7_sensor_bridge_import_check.py`、`stage7_sensor_readiness_check.py` 全部通过。

### 2026-08-07 追加：D435i transport probe 已实现（离线）

- `stage7_topic_probe.py` 的 `sensor_bridge` 层新增两项深度检查：
  - `topic_publisher_count`：`/uav1/rflysim/sensor3/img_depth`、
    `/uav2/rflysim/sensor13/img_depth` 必须恰好 1 个 publisher（topic_tools relay）；
  - `depth_image_flow`：订阅 `sensor_msgs/Image`，硬检查
    `encoding=mono16`、`640x480`、接收帧率 20–45 Hz、header 时间戳单调、
    至少一帧非全零；报告同时给出 `count / receive_rate_hz /
    header_rate_hz / stamp_monotonic / encoding / width / height /
    zero_ratio / min / max`。
- `validate_config()` 现在强制校验 bridge 侧
  `raw_rgb_topic/raw_bottom_topic/raw_depth_topic/depth_topic` 与 UAV 侧
  `sensor_rgb_topic/sensor_bottom_topic/sensor_depth_topic/
  planner_depth_topic/mavros_setpoint_topic`。
- 新增断言已并入 `tests/stage7_probe_flow_check.py`，`scripts\validate_stage7.ps1`
  离线验证通过。

注意：深度“非全零”只证明传输链路活着，**不证明深度值与 SLAMScene
赛道墙体/天花板几何一致**。几何一致性仍属 live 待办，本次提交不得被描述为
“D435i live 验证通过”。

### 2026-08-07 追加：SDK jsonLoad 格式修正（live 发现）

首次 live 启动时 `run_live_fastlio_dual.bat` 的 bridge 日志出现两次
`Json data format is wrong!`，SDK 只加载了 2 个传感器（lidar + 下视），
RGB 与深度没有生效。根因是 RflySim `VisionCaptureApi.jsonLoad` 的格式契约：

- `otherParams` 为 16 维时必须带 `EularOrQuat` 与 4 维 `SensorAngQuat`
  （28com 的 RGB 即此新协议格式）；
- 8 维 `otherParams` 不能带 `EularOrQuat`（否则会被当作新协议继续校验并失败）。

本项目 UAV1/UAV2 的 D435i RGB（SeqID 1/11）与深度（SeqID 3/13）此前只写了
16 维 `otherParams`、漏了 `EularOrQuat`/`SensorAngQuat`，离线 `json.loads`
不会发现，只有 SDK 实际解析才会暴露。已按 28com 格式补齐两个配置文件；
`tests/stage7_dual_sensor_config_check.py` 新增 `validate_sdk_loadable`
契约，16 维 otherParams 缺键会被回归测试拒绝。

### 2026-08-07 追加：live transport 实测（深度帧率不达标）

新仿真实例 `px4-a289b8bc70d45c16`（run
`stage7-20260807T063728Z-2686`）上 readiness 五项门禁全部通过
（双机 17408 点/帧，`armed=false`），ego-swarm/FAST-LIO 正常；
`stage7_topic_probe.py` 首次真实执行 D435i 深度检查，结果：

- `/uav1/rflysim/sensor3/img_depth` 与 `/uav2/rflysim/sensor13/img_depth`
  publisher 唯一（relay 各 1 个）、encoding=mono16、640x480、至少一帧非全零
  ——transport 检查基本通过；
- 但帧率实测约 **1.8 / 2.2 Hz**（relayed 话题），远低于配置的 30 Hz，
  `depth_image_flow` 的 20–45 Hz 硬检查失败；
- 尚未区分：原始话题 `/rflysim/sensor3/img_depth` 与 relay 话题的帧率差、
  是否渲染负载（双机 4 传感器 640x480@30Hz + lidar）或 RflySim 深度输出
  本身限制导致。

结论：深度传输链路已真实打通（有数据、格式正确），但 30 Hz 帧率契约未达成，
不能宣称 D435i live 验证通过；下次 live 先对比 raw/relay 帧率再定验收标准。
另外本次 probe 首跑还暴露两个流程问题（非代码问题）：ego-swarm 中途掉线导致
planner 层失败；readiness 超过 120 秒过期导致 flight_gate 拒绝。

### 2026-08-07 追加：live 链路改为 lidar_only（飞行稳定性修复）

复测飞行时双机均能 OFFBOARD + arming，但起飞窗内 odom 出现秒级断流
（第一次 0.52 s、第二次 2.04 s），watchdog 失联保护把起飞打断，高度始终
贴地。对照昨天成功 run（bridge 只加载 1 个传感器）与今天的 4 传感器载荷，
根因是 D435i RGB+深度同时灌入 UE4 渲染后机器负载过高，传感器/odom 流
间歇停摆。修复：

- `rflysim_sensor_bridge.py` 新增 `--sensor-mode {lidar_only,full}`，
  默认 `lidar_only`：只把匹配 `--sensor-seq-id` 的传感器交给 SDK，UE4 只
  流 lidar，恢复稳定 10 Hz；`full` 模式加载全部传感器（配置契约不变，
  供后续视觉任务使用）。identity 携带 `sensor_mode`。
- `stage7_live_fastlio_dual.sh` 显式传 `--sensor-mode lidar_only`；
  `stage7_topic_probe.py` 在 lidar_only 模式下把深度检查标记为
  `skipped_lidar_only`（不阻塞链路），full 模式下仍硬检查。
- 深度 30 Hz / 几何一致性 live 验证移至 `full` 模式待办。

### 2026-08-07 最终结论：D435i live 集成暂缓

原计划是把 D435i（RGB + 深度）加入仿真链路，但今天的 live 复测证明：在
当前机器上 4 传感器载荷（双机 2×RGB + 2×深度 + 2×lidar + 2×IMU）会导致
UE4 渲染过载、传感器/odom 流间歇停摆，起飞窗内出现 0.52–2.04 s 断流并被
watchdog 误判失联打断起飞；深度帧率也只有约 2–3 Hz（远低于 30 Hz）。因此：

- **live 飞行链默认 `lidar_only`**（只加载 Mid360），配置契约与 D435i
  文件保留，`--sensor-mode full` 显式加载全部传感器（供后续视觉任务）；
- 切换后双机起飞已恢复（takeoff 确认通过）；
- 导航阶段 `planner_commands=0` 已被单独取证定位（与 D435i 无关）：
  `stage7_live_slam_ego_swarm_flight.sh` 未 source ego-planner-swarm devel，
  28com_uav devel 与 EGO 发布端的 `quadrotor_msgs/PositionCommand` md5 不一致
  （`44d620d9…` vs `4712f060…`），ROS 丢弃连接导致 bridge/executor 收不到
  pos_cmd。修复：flight runner 与 stage8 recorder 在 28com_uav 之后、project
  overlay 之前 source `$EGO_SWARM_WSL_DIR/devel/setup.bash`（2026-08-07 晚间
  曾短暂 revert 后按用户决定重新落地；已 live 验证：run
  `stage7-20260807T124153Z-22785` 中 UAV1 导航 `planner_commands=190/383/116`、
  ego 日志无 md5 drop。同一 run 出现一次 `local_position/odom` 瞬态断流导致
  任务中止，属独立待取证问题）；
- D435i 深度 30 Hz、几何一致性等 live 验证全部延后到 `full` 模式，
  不阻塞主飞行链。

待下次仿真启动后完成（live）：

0. 先复测主飞行链：fresh instance → readiness → ego-swarm → 双机短导航，
   确认 `/uav*/planning/pos_cmd` 无 md5 drop、executor 收到 planner commands
   （验证 `planner_commands=0` 修复）；
1. no-arm 实跑 `scripts\run_stage7_topic_probe.bat`，确认 transport probe
   （唯一 publisher、约 30 Hz、mono16/640x480、时间戳单调、非全零）真实通过；
2. 检查深度图像与 SLAMScene 赛道墙体/天花板的几何距离一致性（transport probe
   无法覆盖，需 live 可视化或点云比对）；
3. 确认 ego-swarm 日志中深度融合实际触发（`has_first_depth_`/`flag_use_depth_fusion`），并在窄隧道中对比开/关深度滤波的占用图与轨迹；
4. 复测感知防撞（UAV2 急停）在深度融合开启后仍正常。

