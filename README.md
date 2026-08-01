# future_aircraft_sim

`future_aircraft_sim` 是面向未来飞行器创新大赛仿真任务的仿真侧工作区。它保存 RflySim / PX4 SITL / MAVROS 的启动编排、阶段配置、离线验证脚本和任务契约；ROS 代码集中在 `future_aircraft_ws` 中开发。

AI 工作说明请见 [.agents/AGENT2READ.md](.agents/AGENT2READ.md)。

## 项目简介

本项目基于既有 `28com_uav` 实机工程演进，不复制原工程主体，而是在 ROS1 Noetic、PX4 SITL、MAVROS 与 RflySim 的基础上，逐步搭建双机协同导航、任务调度、日志评分和目标感知的仿真链路。

当前路线是“先建立可重复闭环，再替换核心能力”：先跑通单机、双机启动与 MAVROS namespace，再引入日志评分、行为树、ego-swarm adapter 和 target provider。后续迁移到真实 FS-310 硬件时，上层 ROS 话题和任务接口应尽量保持一致。

## 当前进度

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
- Stage 7：双机独立 RflySim sensor bridge、FAST-LIO/Ouster 点云适配、run-scoped no-arm readiness、ego-swarm wrapper 与 guarded live flight runner 的离线契约

Stage 2.1 是进入后续 live 阶段的强制单机回程链路门：先启动选定的单机仿真路径，运行 `scripts\run_stage2_1_mavlink_check.bat` 并检查 `logs/stage2_1_live/mavlink_link_report.json`；只有 `status` 为 `ready` 才能继续排查双机扩展，否则应修复报告所分类的边界。双机扩展通过后，才运行 Stage 6D no-arm smoke。

Stage 6D / 6E 提供了更直接的 live 入口。dry-run 验证不会启动 RflySim、PX4、MAVROS 或 GUI；真实运行时，6D 不会 arm，6E 会先执行双 MAVROS 连通性检查，只有检查通过且 `--allow-arm --simulation-only` 与配置门禁同时满足时，才调用仿真 MAVROS arming service。

Stage 7 是当前 live-first 路线：两个项目本地 sensor bridge 分别绑定 CopterSim 1/2、SeqID 0/10 和 UDP 9999/10009；点云 adapter 生成 faster_lio 所需的 32-byte Ouster schema，IMU 也隔离到 `/uav1`、`/uav2`。`run_live_fastlio_dual` 会先生成 `logs/stage7_live/<run-id>/sensor_readiness.json`，只有 identity、schema、freshness、isolation、stationary_stability 五个 no-arm gate 全部通过，ego-swarm 和 flight runner 才能继续。Stage 7 现在只有离线 contract 通过；不要把它记为 live 完成。

### 进度估算

当前项目总体进度约为 **78%**。该数字按完成真实双机任务闭环所需的关键路径估算，不是按 Stage 数量简单平均：

- 离线工程与接口契约约 **95%**：启动编排、namespace、双传感器隔离、点云 schema、run-scoped readiness、日志评分、mission executor 和 arm 安全门禁均已有确定性验证。
- 真实仿真闭环约 **65%**：双 MAVROS 已在 GUI 仿真中实测 `connected: true`；Stage 6D 使用 PX4 `ODOMETRY` 经 MAVROS extras 发布的 `/uav*/mavros/odometry/in`，其现场数据、OFFBOARD、仿真解锁、起飞、任务执行和降落仍需端到端确认。
- 核心能力替换约 **55%**：双机传感器适配与 FAST-LIO 输入契约已落地；ego-swarm 仍需 live 接入验证，视觉 provider 仍使用确定性仿真检测数据。

因此，当前状态可以概括为“离线任务框架基本完成，正在进入真实仿真联调”。下一次显著的进度提升应来自 live 定位、规划和飞控闭环，而不是继续增加视觉或行为树离线契约。

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

下一步是 **仅 no-arm** 的 Stage 7 live 验收：运行 `start_two_uav -> run_live_fastlio_dual`，确认 run-scoped `sensor_readiness.json` 的五个 gate 均为 `pass`、两机 `armed=false`。在这份现场证据通过前不要启动 ego-swarm 或 flight runner；后续仿真解锁飞行仍需要单独明确授权。

当前 Stage 7 路线：

1. `scripts\start_two_uav.bat` 启动双机 RflySim/PX4/MAVROS。
2. `scripts\run_live_fastlio_dual.bat` 启动独立双 bridge、adapter、FAST-LIO，并生成 `logs/stage7_live/<run-id>/sensor_readiness.json`；当前验收在此停止且保持两机未解锁。
3. `scripts\run_live_ego_swarm_dual.bat` 启动本项目 ego-swarm 双机 wrapper，替换 28comsim 的 ego-planner 流程，但不修改 `28com_sim`。
4. `scripts\run_stage7_topic_probe.bat` 生成分层只读诊断报告，确认 sensor bridge、FAST-LIO、MAVROS、ego-swarm 和 flight gate。
5. `scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only` 执行最小 live flight runner：两机进入 OFFBOARD、仿真解锁、起飞、短航段飞行并降落。

视觉识别、target provider 和行为树暂时不进入这条主线。
