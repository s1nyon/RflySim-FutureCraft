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

Stage 6D / 6E 提供了更直接的 live 入口。dry-run 验证不会启动 RflySim、PX4、MAVROS 或 GUI；真实运行时，6D 不会 arm，6E 会在 `--allow-arm --simulation-only` 和配置门禁同时满足后调用仿真 MAVROS arming service。

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
3. 若 no-arm smoke 通过，执行 `scripts\run_live_sim_arm.bat`，进入仿真 arm 路径。

## 开发约定

- ROS 逻辑只在 `future_aircraft_ws` 中开发。
- 不复制 `28com_uav` 原工程主体。
- 多机控制默认使用 `/uav1`、`/uav2` 命名空间。
- 任务、规划、感知之间通过固定接口解耦，避免把实现细节写进行为树。
- 仿真阶段可以自动解锁，但真实飞机默认只走人工 arm 和手动切 Offboard。
- 每次阶段推进都要同步更新文档和验证入口。

## 下一步

下一步是真正执行 live dual-MAVROS smoke。先启动双机仿真链路，然后运行 no-arm smoke；若结果稳定，再运行 simulation-arm runner，并根据 `logs/stage6e_live/mission_events.jsonl` 和 `score_summary.json` 判断后续修正点。
