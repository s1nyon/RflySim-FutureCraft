# future_aircraft_sim

`future_aircraft_sim` 是面向未来飞行器创新大赛仿真任务的仿真侧工作区。它保存 RflySim / PX4 SITL / MAVROS 的启动编排、阶段配置、离线验证脚本和任务契约；ROS 代码集中在 `future_aircraft_ws` 中开发。

AI 工作说明请见 [.agents/AGENT2READ.md](.agents/AGENT2READ.md)。

## 项目简介

本项目基于既有 `28com_uav` 实机工程演进，不复制原工程主体，而是在 ROS1 Noetic、PX4 SITL、MAVROS 与 RflySim 的基础上，逐步搭建双机协同导航、任务调度、日志评分和目标感知的仿真链路。

当前路线是“先建立可重复闭环，再替换核心能力”：先跑通单机、双机启动与 MAVROS namespace，再引入日志评分、行为树、ego-swarm adapter 和 target provider。后续迁移到真实 FS-310 硬件时，上层 ROS 话题和任务接口应尽量保持一致。

## 当前进度

> **Stage 8 live 状态（2026-08-02）：未通过。** 双机穿隧道 run `stage7-20260802T102552Z-8563` 虽通过 readiness 和 topic probe，但 UAV2 异常升高至约 11.257 m、切入 ALTCTL 并离开有效定位范围；随后执行器还记录 UAV1 `planner_commands=0`、导航超时。两机最终均已解除解锁。本次问题、已修正的 watchdog 前置竞态和下次排查顺序见 [docs/stage8_tunnel_live_issue_2026-08-02.md](docs/stage8_tunnel_live_issue_2026-08-02.md)。不得将当前状态描述为双机已完成穿隧道和降落。

> **2026-08-07 调试主线更新（未提交工作树）。** 已按 28com UAV_demo 架构对齐并落地离线代码：
> - 主 odom 输入切换为 `/uavX/mavros/local_position/odom`（watchdog、executor 航迹验证与 preflight 等待），`/odometry/in` 仅作交叉校验；
> - 新增 Gate B 检查 `odom_tf_contract_check.py`（MAVROS odom 插件四组 TF lookup + mavros 日志 `ODOM: Ex` 扫描）；
> - `mission_executor` 失败路径落盘 partial events/trace/score；run 产物新增 `provenance.json` 并被 flight report 引用；
> - watchdog 输出结构化决策 JSONL（含 reason）；topic probe 改为真实 goal 订阅者计数与 pos_cmd 消息流检查；
> - FAST-LIO 静态 TF 加 respawn，ego-swarm launch 移除全局 `world/map/base_link/camera_link` 帧污染；
> - stage8 动态 LiDAR 探针按 SLAMScene 参数化（墙世界 NED → LiDAR 系 ROI）。

2026-08-01 的完整双机 live flight run `stage7-20260801T101757Z-2497` 已通过：两机完成 OFFBOARD、仿真解锁、1 m 起飞、ego-swarm 短航段、AUTO.LAND 与最终 disarm。报告为 `ready=true`，碰撞、OFFBOARD 丢失和超时均为 0，最小机间距 0.85 m，总时长 23.5 s。对应修复提交为 `ce7e0a7`。

已经完成的离线阶段：

- Stage 0：工作区与启动脚本骨架
- Stage 1：单机 MAVROS 启动链路
- Stage 2：双机 namespace 启动链路
- Stage 4：ego-swarm 离线适配契约
- Stage 5A - 5E：行为树、live boundary、mission executor、MAVROS smoke checker 与仿真 arm 门禁
- Stage 6A：理想目标 provider
- Stage 6B：仿真视觉 provider
- Stage 6C：live dual-MAVROS smoke runbook
- Stage 6D / 6E：no-arm live smoke runner 与 simulation-arm live runner
- Stage 7：双机独立 RflySim sensor bridge、FAST-LIO/Ouster 点云适配、run-scoped no-arm readiness、ego-swarm wrapper，以及已通过现场验收的 guarded 双机飞行闭环
- Stage 8：参数化预测赛道，包括双机起飞区、约 14.93 m 的 S 形狭窄通道、双降落平台、RflySim 动态实体、ROS 参考点云和 CopterSim 平地校准产物

Stage 2.1 是进入后续 live 阶段的强制单机回程链路门：先启动选定的单机仿真路径，运行 `scripts\run_stage2_1_mavlink_check.bat` 并检查 `logs/stage2_1_live/mavlink_link_report.json`；只有 `status` 为 `ready` 才能继续排查双机扩展，否则应修复报告所分类的边界。双机扩展通过后，才运行 Stage 6D no-arm smoke。

Stage 6D / 6E 提供了更直接的 live 入口。dry-run 验证不会启动 RflySim、PX4、MAVROS 或 GUI；真实运行时，6D 不会 arm，6E 会先执行双 MAVROS 连通性检查，只有检查通过且 `--allow-arm --simulation-only` 与配置门禁同时满足时，才调用仿真 MAVROS arming service。

Stage 7 是当前 live-first 路线：两个项目本地 sensor bridge 分别绑定 CopterSim 1/2、SeqID 0/10 和 UDP 9999/10009；点云 adapter 生成 faster_lio 所需的 32-byte Ouster schema，IMU 也隔离到 `/uav1`、`/uav2`。`run_live_fastlio_dual` 会先生成 `logs/stage7_live/<run-id>/sensor_readiness.json`，只有 identity、schema、freshness、isolation、stationary_stability 五个 no-arm gate 全部通过，ego-swarm 和 flight runner 才能继续。2026-08-01 的 run `stage7-20260801T082349Z-6875` 完成了双 FAST-LIO 静止 no-arm live 验收：五个 gate 全部 `pass`、两机 `armed=false`、`ready=true`。这是定位层的历史基线；后续完整飞行验收使用了新的 run 和仿真实例。

后续 no-arm run `stage7-20260801T090244Z-5522`（实例 `px4-2c74476509ac6faa`）再次通过五项 gate 且两机未解锁。首次 ego-swarm 启动暴露的 ROS overlay 顺序缺陷已由 `9ad9b4c` 修复，只读 topic probe 与 ego runner 的 readiness 窗口也由 `46178c0` 统一为 120 秒。最终 flight run `stage7-20260801T101757Z-2497`（实例 `px4-bb8094a4352d452e`）完成双机 OFFBOARD、解锁、1 m 起飞、短航段、降落和自动卸载；报告为 `ready=true`，碰撞、OFFBOARD 丢失和超时均为 0，最小机间距 `0.85 m`，用时 `23.5 s`。这证明 Stage 7 最小定位—规划—控制闭环可用，但还不等于长航程、复杂障碍或完整竞赛任务已经完成。

### 进度估算

当前项目总体进度约为 **88%**。该数字按完成真实双机任务闭环所需的关键路径估算，不是按 Stage 数量简单平均：

- 离线工程与接口契约约 **97%**：启动编排、namespace、双传感器隔离、点云 schema、run-scoped readiness、日志评分、mission executor、故障降落和仿真 arm 门禁均有确定性验证。
- 真实仿真闭环约 **90%**：双 MAVROS、双 FAST-LIO、双 ego-swarm、OFFBOARD、解锁、起飞、短航段和降落已完成一次无碰撞端到端验收；尚缺跨新实例的连续重复运行、较长航线和更复杂障碍环境验证。
- 核心能力替换约 **70%**：定位、规划与飞控最小闭环已接入项目；视觉 provider 仍使用确定性仿真检测数据，目标任务和行为树尚未重新接回这条稳定 live 主线，实机迁移也尚未验证。

因此，当前状态可以概括为“Stage 7 最小双机 live 闭环完成，项目进入重复性、航线覆盖和完整任务集成阶段”。下一次显著的进度提升应来自多次连续稳定运行与更有代表性的路线，而不是继续堆叠离线契约。

## 目录说明

- `config/`：阶段配置、环境模板、确定性输入数据
- `scripts/`：Windows 启动脚本、验证脚本、WSL 辅助脚本
- `future_aircraft_ws/`：ROS1 工作区源码
- `tests/fixtures/`：离线验证的固定输出
- `docs/superpowers/`：设计说明、计划与阶段文档
- `.agents/`：给 agent 看的执行说明和工作约束
- `logs/`：每次运行生成的日志与评分结果

## 常用命令

离线验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6b.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

双机仿真启动：

```bat
scripts\start_two_uav.bat
```

No-arm live smoke：

```bat
scripts\run_live_no_arm_smoke.bat
```

仿真 arm live runner：

```bat
scripts\run_live_sim_arm.bat
```

Stage 7 live-first runners：

```bat
scripts\run_live_fastlio_dual.bat
scripts\run_live_ego_swarm_dual.bat
scripts\run_stage7_topic_probe.bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

## Stage 8 预测狭窄通道地图

第一版赛道使用 `VisionRingBlank` 作为 UE/CopterSim 平地基础地图，并通过 Python 动态加载课程自有实体。唯一场景源是 `config/maps/predicted_narrow_course_v1.json`。其主要尺寸为：通道中心线约 14.927433 m、净宽 1.4–1.5 m、两个 0.9 m 转弯、2.5 m 墙高、双降落平台中心间距 2.0 m。

离线生成和检查：

```bat
scripts\validate_stage8.ps1
scripts\generate_predicted_narrow_course.bat
scripts\start_predicted_course_two_uav.bat --dry-run
```

启动带地图的双机 GUI 仿真：

```bat
scripts\start_predicted_course_two_uav.bat
```

该入口生成地图产物，由双机启动脚本选择 `VisionRingBlank` 基础地图，再以默认的“仅加载物体”模式添加动态墙体和平台；加载阶段不会重复切换 UE 关卡，也不会请求 OFFBOARD 或解锁。每次实际启动后，仍应先执行 `scripts\run_live_fastlio_dual.bat` 和 `scripts\run_stage7_topic_probe.bat` 完成 no-arm 传感器/定位检查；任何仿真飞行仍需另行显式使用 simulation-only arm 门禁。

`narrow_course_ue_loader.py --change-map` 仅供传感器启动前的独立调试。不要在 FAST-LIO 或其他 RflySim 视觉传感器运行时使用该参数：`RflyChangeMapbyName` 会重建 UE 关卡并中断现有激光雷达捕获状态。

动态墙体不是 CopterSim 高度地形。地图验收以 RflySim LiDAR 可见性和项目几何净空评估为准，不能把 CopterSim 地形高度查询当作墙体碰撞证明。生成的 `VisionRingBlank.png/.txt` 位于 `generated/predicted_narrow_course_v1/`，不会自动覆盖安装目录。

## Live 联调顺序

推荐顺序：

1. 启动 `scripts\start_two_uav.bat`，拉起双机仿真、PX4 SITL、WSL 与双 MAVROS。
2. 执行 `scripts\run_live_no_arm_smoke.bat`，生成 live plan，运行 ROS smoke check，并确认 mission executor 中 arming 被阻断。
3. 若 no-arm smoke 通过，执行 `scripts\run_live_sim_arm.bat`；该入口会再次执行 MAVROS smoke check，通过后才进入仿真 arm 路径。

Stage 7 live-first 顺序：

1. `scripts\start_two_uav.bat`
2. `scripts\run_live_fastlio_dual.bat`
3. `scripts\run_live_ego_swarm_dual.bat`
4. `scripts\run_stage7_topic_probe.bat`
5. `scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`

`run_live_fastlio_dual` 会启动两个项目本地 sensor bridge，分别使用 `config/rflysim_sensor_uav1.json` 和 `config/rflysim_sensor_uav2.json`，再启动点云 adapter、IMU relay 与双机 FAST-LIO。它只采集 no-arm readiness，不启动 planner、不发布 setpoint、不请求模式或解锁。`run_live_ego_swarm_dual` 只 source 已构建的 `external/ego-planner-swarm`，且必须先验证同一 run/仿真实例的 readiness 报告。

`run_stage7_topic_probe` 是只读诊断入口，不发布 setpoint、不发送 planner goal、不调用 arming。它加载 `logs/stage7_live/current_run.env`，拒绝 stale、跨 run 或跨仿真实例的 readiness 报告，再把状态分成 `sensor_bridge`、`fast_lio`、`mavros`、`ego_swarm`、`flight_gate` 五层。

Stage 7 flight runner 复用当前 sensor readiness 的 `run_id` 和 `simulation_instance_id`；在启动 setpoint bridge、请求 OFFBOARD 或 arming 前再次 fail-closed 校验报告。失败时 `flight_report.json` 的 `ready` 为 `false`，`phase` 和 `executor.exit_code` 标出失败阶段。两机 planner goal 始终分别发布到 `/uav1/planning/goal` 与 `/uav2/planning/goal`。

Rfly SIL 的 `16540/17540` 与 `16541/17541` 仅供 CopterSim/PX4 使用，不能复用为 MAVROS FCU URL。启动器会在 PX4 上额外创建专用 MAVLink 链路：`/uav1` 使用 `udp://:14601@127.0.0.1:14600`，`/uav2` 使用 `udp://:14611@127.0.0.1:14610`。这避免了 CopterSim 与 MAVROS 争用 Rfly SIL 端口；链路请求 `LOCAL_POSITION_NED` 供 local pose/velocity，并请求 `ODOMETRY` 供 Stage 6D 的 `/uav*/mavros/odometry/in`。

## 开发约定

- ROS 逻辑只在 `future_aircraft_ws` 中开发。
- 不复制 `28com_uav` 原工程主体。
- 多机控制默认使用 `/uav1`、`/uav2` 命名空间。
- 任务、规划、感知之间通过固定接口解耦，避免把实现细节写进行为树。
- 仿真阶段可以自动解锁，但真实飞机默认只走人工 arm 和手动切 Offboard。
- 每次阶段推进都要同步更新文档和验证入口。

## 下一步

下一步是把已通过的 Stage 7 最小闭环变成可重复的工程基线：在每个新仿真实例中生成新的 run-id 与 `simulation_instance_id`，先完成 no-arm readiness，再按相同入口执行飞行。优先连续完成 3–5 次无碰撞、无 OFFBOARD 丢失、无超时运行；随后扩大航段与墙面净空、整理 run-scoped 飞行产物，最后把目标感知和行为树任务接回 live 主线。仿真 arm 仍必须显式使用 `--allow-arm --simulation-only`；实机继续保持人工解锁。

当前 Stage 7 路线：

1. `scripts\start_two_uav.bat` 启动双机 RflySim/PX4/MAVROS；每次重启都视为新仿真实例。
2. `scripts\run_live_fastlio_dual.bat` 启动独立双 bridge、adapter、FAST-LIO，并生成 `logs/stage7_live/<run-id>/sensor_readiness.json`；2026-08-01 的 no-arm live 验收已在此通过并保持两机未解锁。
3. `scripts\run_live_ego_swarm_dual.bat` 启动本项目 ego-swarm 双机 wrapper，替换 28comsim 的 ego-planner 流程，但不修改 `28com_sim`。
4. `scripts\run_stage7_topic_probe.bat` 生成分层只读诊断报告，确认 sensor bridge、FAST-LIO、MAVROS、ego-swarm 和 flight gate。
5. `scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only` 执行已验收的最小 live flight runner：两机进入 OFFBOARD、仿真解锁、起飞、短航段飞行并降落；新实例不得复用旧 readiness 报告。

视觉识别、target provider 和行为树暂时不进入这条主线。
