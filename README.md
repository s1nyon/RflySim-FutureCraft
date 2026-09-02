# future_aircraft_sim

## Competition Goal

本项目面向未来飞行器创新大赛赛题 2.1「室内狭窄通道环境下多飞行器智能协同导航与作业挑战赛」。目标是让不少于两架自主飞行器在狭窄、带转弯并含静态/动态障碍的通道中完成起飞、定位避障、未知目标协同作业、穿越和 ArUco 平台精准降落。正式要求以[参赛指南](docs/reference/competition-guide-2026.pdf)为准，阶段路线与验收标准见[当前竞赛路线图](docs/current/competition-roadmap.md)。

## Current Capability

- PBL-1（`lidar_only` 双机 RflySim/PX4/MAVROS/Faster-LIO/EGO-Swarm/OFFBOARD 错时穿越基线）已通过 3 次 fresh-instance 完整 live 回归并冻结。
- Competition Course V2 地图基线 `MAP READY → FROZEN`（2026-09-01/09-02），
  两轮独立 fresh startup world-state retention PASS；正式 freeze/handoff 见
  [Simulation Freeze & C++ Handoff](docs/current/2026-09-02-simulation-baseline-freeze-handoff.md)。
- UAV1 Section A 完整飞行链 **3/3 independent fresh-instance PASS**（endpoint、
  collision 0、watchdog/geofence 0、UAV2 0 违规、AUTO.LAND/disarm 全确认）；
  Section A 入口 wall clearance ≈0.072–0.085m 低于 0.25m 稳定阈值，列为已知
  planner/corridor-entry performance limitation（非 infra blocker），
  证据见 [repeatability evidence](docs/evidence/2026-09-02-v2-section-a-repeatability-clearance-not-stable.md)。
- manifest 化 lifecycle 已通过 5 次 start/READY/stop closure 与 PBL-1 回归；启动、检查、停止和 fresh-instance 均 fail closed。
- 2026-08-11 仓库结构迁移后的 `dev` live 链已恢复：fresh-instance armed 验证
  （双机 OFFBOARD/arm/起飞/14 段导航/降落，`success=true` 41.5s）通过，
  证据见 `docs/evidence/2026-08-11-live-import-and-pwsh-compat-armed-verified.md`。
  已知待修缺陷：WSL 进程组 stop 在 `stack_stop.py` 中失效（stop 报 NOT clean，
  需显式 PID 补清），见 `docs/incidents/2026-08-11-wsl-pgid-stop-ineffective.md`。
- 当前开发阶段：**Phase 2.5 C++ Competition Mission Development（NEXT ACTIVE；
  现有 package 基础 PRESENT，广义 mission 架构尚未实现）**；仿真/infrastructure/map
  已冻结为稳定底座；PBL-1 是回归基线，不等于比赛完整能力。
- D435i RGB/Depth 接口已保留，但 `full` 多传感器模式的 live 飞行稳定性尚未闭环；默认飞行配置仍为 `lidar_only`。
- `future_aircraft_mission` 是**现有且计划继续使用**的 C++ competition mission
  package；现有 `EgoSetpointBridge` 为 PRESENT / KEEP 的 baseline 模块；更广义的
  mission 架构尚未实现，后续模块在该 package 内由用户增量设计。
  `multi_uav_mission` Python 与 lifecycle 是受保护基线。

## Repository Layout

| Path | Purpose |
| --- | --- |
| `future_aircraft_ws/src/future_aircraft_mission/` | 现有且继续使用的 C++ competition mission package（广义 mission 架构待增量实现） |
| `future_aircraft_ws/src/multi_uav_mission/` | 受保护的 live-validated Python/launch 基线 |
| `third_party/ego-planner-swarm/` | 固定 team-fork commit 的独立 Catkin overlay |
| `config/` | 环境模板、阶段契约、传感器与赛道定义 |
| `scripts/` | 入口、生命周期内部实现和诊断脚本；分类见[脚本索引](scripts/README.md) |
| `tests/` | 离线 contract 与 regression 检查 |
| `docs/` | 当前状态、架构、证据、事故、决策和参考资料；见[文档索引](docs/README.md) |
| `logs/`, `generated/` | 被忽略的运行态证据和确定性生成产物；路径属于受保护运行契约 |
| `.agents/`, `.vscode/` | Agent 入口规则与双 workspace 开发配置 |

## Quick Start

先做只读环境检查和 DryRun：

```powershell
.\sim.ps1 doctor
.\sim.ps1 start
.\sim.ps1 status
.\sim.ps1 stop
```

状态变更必须显式使用 `-Execute`。默认 `dev` 启动配置包含双传感器、Faster-LIO readiness 和 EGO-Swarm，并停在 mission execution、OFFBOARD 与 arming 之前。开发构建与验证：

```powershell
.\sim.ps1 build
.\sim.ps1 validate -Suite mission
.\sim.ps1 validate -Suite core
```

## Safety

- 所有 live lifecycle 操作必须使用 manifest 化入口；unknown/stale ownership、端口歧义或 stop-clean 失败时只报告并停止，不自动 force retry。
- 禁止恢复 `scripts/cleanup_sim_stack.ps1` 与 `scripts/restart_live_stack.ps1` 的旧逻辑；它们是恒失败的 hazard tombstone。
- 禁止名称扫杀、`wsl --shutdown`、自动硬重启循环和隐式 arming。
- 仿真飞行仅在当前实例 readiness PASS，并同时显式提供 `--simulation-only`、`--allow-arm` 且 policy 允许时执行。真机始终由人类 arm/授权 Offboard。
- 完整安全规则和 Red-Zone 见 [AGENTS.md](AGENTS.md)。

## Development Ownership

- 人类默认拥有 `future_aircraft_mission` 的比赛行为、任务策略和控制意图。
- Agent 默认维护仿真编排、地图、项目侧 adapter、诊断、维护脚本及其测试。
- ROS 接口、launch 组合、package manifest、lifecycle/launcher 和任何可能影响 PBL-1 的改动属于 change-gated shared boundary，修改前必须说明证据、影响、回滚与验证方案。
- `multi_uav_mission` Python 基线和 lifecycle 实现冻结，除非 fresh regression evidence 证明必须修改。

## Validation

文档与仓库结构改动运行：

```powershell
D:\PX4PSP\Python38\python.exe tests\script_inventory_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
```

当前核心离线门：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

离线 PASS 不代表 live PASS；未运行 fresh live 时必须明确写明 live parity 未验证。

## Documentation Index

- [文档总索引](docs/README.md)
- [当前竞赛路线图](docs/current/competition-roadmap.md)
- [PBL-1 live 回归证据](docs/evidence/2026-08-08-pbl1-fullstack-regression-closure.md)
- [Lifecycle 架构](docs/architecture/2026-08-08-live-stack-lifecycle-design.md)
- [Agent 当前入口](.agents/AGENT2READ.md)
- [RflySim 工具链边界](.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md)
