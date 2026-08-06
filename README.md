# future_aircraft_sim

面向未来飞行器创新大赛的双机协同仿真工程。项目以 RflySim、PX4 SITL 和 MAVROS 为底座，在 28com FS-310 无人机链路之上搭建定位、规划、感知与任务执行闭环，目标是把仿真验证过的链路平滑迁移回真实硬件。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 仿真 | RflySim3D + CopterSim，SLAMScene 基图 |
| 飞控 | PX4 SITL（iris 机架），MAVROS 双命名空间 |
| 定位 | Faster-LIO（Mid360 雷达 + IMU） |
| 规划 | EGO-Swarm（`external/ego-planner-swarm`） |
| 传感器 | Mid360、Intel RealSense D435i（RGB + 深度）、下视相机，与 28com UAV_demo 对齐 |
| 环境 | Python / ROS1 Noetic / WSL（RflySim-20.04）/ Windows 启动编排 |

## 当前状态

- Stage 7 最小双机闭环已通过现场验收（2026-08-01）：OFFBOARD、解锁、起飞、ego-swarm 短航段、降落、自动卸锁，报告 `ready=true`，最小机间距 0.85 m。
- 双机错时穿隧道全程成功：UAV1 领先、UAV2 落后，7 段全部到达，无碰撞、无急停。
- 机间防撞以感知为主：UAV1 被 UAV2 的 Mid360 grid_map 标记为障碍，UAV2 在 0.2 m 触发 `EMERGENCY_STOP`。两机 FAST-LIO 坐标系相互独立，ego-swarm 的轨迹广播不参与防撞决策。
- 仿真传感器载荷已补齐 D435i 并接入 EGO-Swarm 深度融合（离线验证通过，live 验证待下次仿真确认）。

待办：跨新实例的重复运行（3–5 次）、更长航段、目标感知与行为树任务集成、实机迁移。

## 目录结构

| 目录 | 内容 |
| --- | --- |
| `future_aircraft_ws/` | ROS1 工作区源码（多机任务包） |
| `scripts/` | Windows 启动/验证脚本、WSL 辅助脚本 |
| `config/` | 阶段配置、环境模板、赛道定义 |
| `external/` | 独立构建的算法仓库 |
| `tests/` | 离线契约与回归测试 |
| `docs/` | 阶段设计与问题记录 |
| `generated/` | 赛道生成产物（构建期生成） |
| `logs/` | 每次运行产生的日志与报告 |
| `.agents/` | 面向开发 agent 的操作手册 |

## 快速开始

### 双机赛道仿真

```bat
scripts\start_predicted_course_two_uav.bat
```

该入口依次完成赛道生成、平地地形部署、双机 PX4 SITL 启动与动态实体加载，不会请求 OFFBOARD 或解锁。

### Stage 7 live 顺序

```bat
scripts\run_live_fastlio_dual.bat
scripts\run_live_ego_swarm_dual.bat
scripts\run_stage7_topic_probe.bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

`run_live_fastlio_dual.bat` 生成 run-scoped 的 no-arm readiness 报告（`logs/stage7_live/<run-id>/sensor_readiness.json`），五项门禁全部通过后才允许后续规划器与飞行入口；`run_stage7_topic_probe.bat` 是只读诊断入口。仿真解锁必须显式使用 `--allow-arm --simulation-only`。

### 离线验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

## 运行约束

- 仿真解锁仅通过 `--allow-arm --simulation-only`；真实飞机保持人工解锁与手动 Offboard。
- 每次重启仿真视为新实例，readiness 报告携带 run-id 与 simulation-instance-id，跨实例一律拒绝。
- no-arm 门禁五项：identity、schema、freshness、isolation、stationary_stability。
- 双机联调前先通过 Stage 2.1 单机 MAVLink 回程检查（`scripts\run_stage2_1_mavlink_check.bat`）。
- MAVLink 端口约定：`16540/17540`、`16541/17541` 仅用于 CopterSim/PX4；MAVROS 使用专用链路 `/uav1: udp://:14601@127.0.0.1:14600`、`/uav2: udp://:14611@127.0.0.1:14610`。
- 动态实体赛道以 RflySim LiDAR 可见性与几何净空验收，不作为 CopterSim 地形。

## 赛道

`config/maps/predicted_narrow_course_v1.json` 是唯一赛道源：S 形通道中心线约 14.93 m、净宽 1.4–1.5 m、墙高 2.5 m，天花板与墙顶齐平，双降落平台中心间距 2.0 m，碰撞在加载时启用。基图为 SLAMScene。

## 文档与约定

- [.agents/AGENT2READ.md](.agents/AGENT2READ.md)：agent 执行规则与开发经验（传感器对齐、坐标系、ego-swarm 参数语义等）。
- [docs/d435i_sensor_parity_2026-08-07.md](docs/d435i_sensor_parity_2026-08-07.md)：与 28com UAV_demo 的传感器载荷对齐说明。
- [docs/](docs/)：阶段设计与问题记录。
- ROS 代码只放在 `future_aircraft_ws`，不修改 28com 原工程；多机命名空间固定为 `/uav1`、`/uav2`；任务、规划、感知通过固定接口解耦。
