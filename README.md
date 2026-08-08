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
- 仿真传感器载荷已补齐 D435i 并接入 EGO-Swarm 深度融合（离线验证通过，live 验证待下次仿真确认）。深度链路 transport 契约（唯一 publisher、约 30 Hz、mono16/640x480、时间戳单调、非全零）已纳入 `run_stage7_topic_probe.bat` 的 `sensor_bridge` 层；与赛道墙体/天花板几何一致性仍需 live 确认。
- 2026-08-07 live 复测：传感器 bridge 默认改为 `lidar_only`（只加载 Mid360），双机 OFFBOARD/arming/**起飞高度确认已通过**。导航阶段 `planner_commands=0` 已根因定位为 `quadrotor_msgs/PositionCommand` md5 不一致（EGO 发布端 `4712f060…` vs 28com_uav devel `44d620d9…`），修复为 flight runner / stage8 recorder 在 28com_uav 之后、project overlay 之前 source ego-planner-swarm devel；**该修复已 live 验证**（run `stage7-20260807T124153Z-22785`：UAV1 导航 `planner_commands=190/383/116`，ego 日志无 md5 drop）。
- 2026-08-08 executor subscriber 修复：`mission_executor.py` 导航验证改为持久 `rospy.Subscriber` + 内存缓存（`TopicCache`），不再循环 `wait_for_message()`；新增离线回归测试并纳入 `validate_stage7.ps1`；cold-start readiness 新增 odom relay 初始化等待（`STAGE7_ODOM_INIT_TIMEOUT_SEC`），与消息超时分离。离线 Stage 6C/6D/7/8 验证通过；**live 完整双机错时穿隧道已通过**（3 次 fresh-instance 干净成功：`stage7-20260807T133813Z-2617`、`T134731Z-2508`、`T141751Z-3219`，各 14 段导航确认、41.5 s、零失败），另 1 次实例因 EGO 侧 UAV2 pos_cmd 偶发未发布失败（非 executor 回归）。D435i 多传感器载荷会拖垮 UE4 渲染导致 odom 断流，live 集成暂缓（`--sensor-mode full` 保留给后续视觉任务）。
- 2026-08-08 P0 Safe Live Stack Lifecycle：live 仿真启动/停止/fresh-instance 改为 manifest 化安全流程（`stack_id` + 进程指纹 ownership、只读 inspect、graceful stop、健康门 fail-closed），`scripts/cleanup_sim_stack.ps1` / `restart_live_stack.ps1` 已封禁为 fail-fast hazard stub。设计见 `docs/2026-08-08-live-stack-lifecycle-design.md`，离线验证 `scripts/validate_lifecycle.ps1` 全部通过；**live 验证待用户批准后执行**（首次用户在场监督，随后 3→5 次 fresh-instance）。
- 2026-08-08 P0.1 Safety Hardening：ownership 改为**创建时登记**（`stack_register.py`，删除名称/regex 扫描认领）、WSL 按独立 PGID 停止、`clean` 来自 stop 最终验证、健康状态按独立文件原子写、FAST-LIO/EGO/mission/recorder 创建时登记到同一 stack；离线回归全 PASS，**live 仍未执行**。
- 2026-08-08 P0.2 spawn_attested ownership：daemonized PX4 SITL 经 `RFLY_STACK_ID` 环境标记继承 + `/proc` 结构证据获得第二种合法 ownership（`wsl:px4_uav1/uav2`）；stop 前重新验证 marker，PGID 含未登记成员时禁止 group kill；live 上 marker 继承与登记已验证，健康门 5/5 READY。
- 地图：SLAMScene + 动态砖块方案已 live 验证可用；**不安装 UE Editor**，静态 UE 地图方案搁置（见 `docs/decisions/2026-08-07-no-ue-editor.md`）。

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
- 位置数据离谱（xyz 远超地图或非有限值）时不自动返航/降落：watchdog 判定为 `unreasonable_position` 并跳过 AUTO.LAND，应修好代码后重启仿真，不得依赖返航兜底。
- 传感器 bridge 默认 `lidar_only`（只加载 Mid360，保持 10 Hz 稳定）；D435i RGB/深度需显式 `--sensor-mode full` 才加载（视觉任务用），避免多传感器渲染拖垮飞行链路。
- 双机联调前先通过 Stage 2.1 单机 MAVLink 回程检查（`scripts\run_stage2_1_mavlink_check.bat`）。
- MAVLink 端口约定：`16540/17540`、`16541/17541` 仅用于 CopterSim/PX4；MAVROS 使用专用链路 `/uav1: udp://:14601@127.0.0.1:14600`、`/uav2: udp://:14611@127.0.0.1:14610`。
- 动态实体赛道以 RflySim LiDAR 可见性与几何净空验收，不作为 CopterSim 地形。
- Stage 8 控制链取证使用只读记录器 `scripts\run_stage8_control_chain_recorder.bat`（只订阅不发布，不 arm），输出
  `$STAGE7_RUN_DIR/stage8_control_chain.jsonl` 与 `stage8_control_chain_summary.json`，用于定位 planner/setpoint/FAST-LIO/MAVROS/PX4 各层 z 异常。
- Stage 7/8 实时产物按 run 隔离：flight_report.json、mission_events.jsonl、executor_trace.json、score_summary.json、runner/executor/watchdog/keepalive 日志及 topic probe 报告都写入 `$STAGE7_RUN_DIR`；run 元数据 `current_run.env` 仍固定在 `logs/stage7_live/`。

## 赛道

`config/maps/predicted_narrow_course_v1.json` 是唯一赛道源：S 形通道中心线约 14.93 m、净宽 1.4–1.5 m、墙高 2.5 m，天花板与墙顶齐平，双降落平台中心间距 2.0 m，碰撞在加载时启用。基图为 SLAMScene。

## 文档与约定

- [.agents/AGENT2READ.md](.agents/AGENT2READ.md)：agent 执行规则与开发经验（传感器对齐、坐标系、ego-swarm 参数语义等）。
- [docs/d435i_sensor_parity_2026-08-07.md](docs/d435i_sensor_parity_2026-08-07.md)：与 28com UAV_demo 的传感器载荷对齐说明。
- [docs/](docs/)：阶段设计与问题记录。
- ROS 代码只放在 `future_aircraft_ws`，不修改 28com 原工程；多机命名空间固定为 `/uav1`、`/uav2`；任务、规划、感知通过固定接口解耦。
