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

Stage 2.1 是进入后续 live 阶段的强制单机回程链路门：先启动选定的单机仿真路径，运行 `scripts\run_stage2_1_mavlink_check.bat` 并检查 `logs/stage2_1_live/mavlink_link_report.json`；只有 `status` 为 `ready` 才能继续排查双机扩展，否则应修复报告所分类的边界。双机扩展通过后，才运行 Stage 6D no-arm smoke。

Stage 6D / 6E 提供了更直接的 live 入口。dry-run 验证不会启动 RflySim、PX4、MAVROS 或 GUI；真实运行时，6D 不会 arm，6E 会先执行双 MAVROS 连通性检查，只有检查通过且 `--allow-arm --simulation-only` 与配置门禁同时满足时，才调用仿真 MAVROS arming service。

### 进度估算

当前项目总体进度约为 **75%**。该数字按完成真实双机任务闭环所需的关键路径估算，不是按 Stage 数量简单平均：

- 离线工程与接口契约约 **90%**：启动编排、namespace、日志评分、行为树、mission executor、arm 安全门禁和 target provider 均已有确定性验证。
- 真实仿真闭环约 **60%**：live runner 和 smoke runbook 已就绪，但双 MAVROS、OFFBOARD、仿真解锁、起飞、任务执行和降落仍需端到端实跑确认。
- 核心能力替换约 **45%**：ego-swarm 目前完成 adapter 契约，官方 planner 尚未克隆、编译和 live 接入；视觉 provider 仍使用确定性仿真检测数据，没有接入真实相机 topic 和检测模型。

因此，当前状态可以概括为“离线任务框架基本完成，正在进入真实仿真联调”。下一次显著的进度提升应来自 Stage 6D/6E live 路径成功运行，而不是继续增加离线契约。

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

## Live 联调顺序

推荐顺序：

1. 启动 `scripts\start_two_uav.bat`，拉起双机仿真、PX4 SITL、WSL 与双 MAVROS。
2. 执行 `scripts\run_live_no_arm_smoke.bat`，生成 live plan，运行 ROS smoke check，并确认 mission executor 中 arming 被阻断。
3. 若 no-arm smoke 通过，执行 `scripts\run_live_sim_arm.bat`；该入口会再次执行 MAVROS smoke check，通过后才进入仿真 arm 路径。

当前 PX4 SITL wrapper 的 Rfly MAVLink 端口为 `/uav1` 的 `udp://:16540@127.0.0.1:17540` 与 `/uav2` 的 `udp://:16541@127.0.0.1:17541`；MAVROS 端口不匹配时 `/mavros/state` 会保持 `connected: False`，并且不会发布 local odom。

## 开发约定

- ROS 逻辑只在 `future_aircraft_ws` 中开发。
- 不复制 `28com_uav` 原工程主体。
- 多机控制默认使用 `/uav1`、`/uav2` 命名空间。
- 任务、规划、感知之间通过固定接口解耦，避免把实现细节写进行为树。
- 仿真阶段可以自动解锁，但真实飞机默认只走人工 arm 和手动切 Offboard。
- 每次阶段推进都要同步更新文档和验证入口。

## 下一步

下一步是真正执行 live dual-MAVROS smoke。先启动双机仿真链路，然后运行 no-arm smoke；若结果稳定，再运行 simulation-arm runner，并根据 `logs/stage6e_live/mission_events.jsonl` 和 `score_summary.json` 判断后续修正点。
