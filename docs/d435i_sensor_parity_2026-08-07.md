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

待下次仿真启动后完成（live）：

1. no-arm 实跑 `scripts\run_stage7_topic_probe.bat`，确认 transport probe
   （唯一 publisher、约 30 Hz、mono16/640x480、时间戳单调、非全零）真实通过；
2. 检查深度图像与 SLAMScene 赛道墙体/天花板的几何距离一致性（transport probe
   无法覆盖，需 live 可视化或点云比对）；
3. 确认 ego-swarm 日志中深度融合实际触发（`has_first_depth_`/`flag_use_depth_fusion`），并在窄隧道中对比开/关深度滤波的占用图与轨迹；
4. 复测感知防撞（UAV2 急停）在深度融合开启后仍正常。

