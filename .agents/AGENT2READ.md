# Future Aircraft Sim — Agent Entry Guide

## Current Truth

- Lifecycle 是 **FROZEN / CLOSED**：5 次 fresh start→READY→stop-clean closure 与 3 次 PBL-1 full regression 已通过。
- 2026-08-11 仓库结构迁移后，`dev` live 链的 armed 验证已恢复并通过
  （fresh-instance：双机 OFFBOARD/arm/起飞/14 段导航/降落，`success=true` 41.5s，
  证据 `../docs/evidence/2026-08-11-live-import-and-pwsh-compat-armed-verified.md`）。
  两项兼容修复（adapter 模块解析、PS5.1/PS7 schema-v2 整数判定）已随修复提交验证。
- 2026-08-20 的 8/20 参数/飞行计划改动已做 **4/4 fresh-instance full arm flight
  PASS**（每次 clean stop → fresh start → readiness → EGO → arm flight 背靠背，
  50.5s/次，无 collision/offboard-loss/timeout），证据
  `../docs/evidence/2026-08-20-current-params-4x-fresh-arm-verified.md`。当天早期
  19:45/21:07 的失败仍按旧栈/未背靠背/odom 抖动处理，不凭单次失败升级为当前 blocker。
- **已知 OPEN 缺陷（Yellow Zone，待修）**：`stack_stop.py` 对 WSL 进程组
  `kill -- -PGID` 无效（返回 0 但进程组存活），stop 报 NOT clean，需要按显式 PID
  补清后再收尾记录 `clean: true`；2 个 fresh 栈均 2/2 复现。
  详见 `../docs/incidents/2026-08-11-wsl-pgid-stop-ineffective.md`。
- 2026-08-11 旧栈 OFFBOARD 失败已定位为运行时序问题（旧栈重试窗口内 setpoint
  流中断），**不是代码回归**；恢复靠「完整清理 → fresh 栈背靠背启动」，
  见 `../docs/incidents/2026-08-11-offboard-stale-retry-setpoint-stream.md`。
- PBL-1 是受保护的 `lidar_only` 双机 RflySim/PX4/MAVROS/Faster-LIO/EGO-Swarm/OFFBOARD 错时穿越基线，不是完整比赛 mission strategy。
- 当前阶段是 Phase 2「Competition-Grade Narrow-Corridor Navigation」；权威路线见 [`docs/current/competition-roadmap.md`](../docs/current/competition-roadmap.md)。
- 当前无 P0/P1 blocker。下一缺口是按比赛几何/障碍验收导航，以及真实视觉目标感知。
- D435i `full` 模式仍需 live 飞行闭环；默认 `lidar_only`。Depth transport、目标测距和 Depth→EGO 是三个独立验收层。
- `planner_commands=0` 的 PositionCommand md5、executor subscriber churn 与 lifecycle 强杀事故均已解决；只有 fresh evidence 再现时才重新作为 blocker，历史见 [`docs/incidents/`](../docs/incidents/)。

## Five-Minute Entry Check

开始编辑前回答：

1. 任务属于 simulator、sensor、localization、MAVROS/PX4、planner、mission、vision、tooling 还是 docs？
2. 是否可能影响 PBL-1、lifecycle 或 arming/stop 安全？
3. 最近可信 evidence 是哪个 run/instance；问题是 current regression 还是旧 incident？
4. 人类/Agent/shared ownership 边界是什么？
5. 能区分首要假设的最小实验和对应验证阶梯是什么？

先读 `AGENTS.md`；涉及 RflySim/PX4/MAVROS/WSL 再读 `RFLYSIM_TOOLCHAIN_REFERENCE.md`。检查工作区现有修改，不覆盖用户或其他 Agent 工作。

## Architecture

```text
RflySim3D + CopterSim + PX4 SITL
→ /uav1, /uav2 MAVROS dedicated links
→ per-UAV Mid360/IMU sensor isolation
→ independent Faster-LIO local frames
→ EGO-Swarm local planning
→ setpoint bridge / PX4 OFFBOARD
→ dual-UAV mission execution
→ optional vision / task logic
```

- ROS1 Noetic 运行于 `RflySim-20.04` WSL。
- MAVROS 专用链路：UAV1 `udp://:14601@127.0.0.1:14600`，UAV2 `udp://:14611@127.0.0.1:14610`；不得复用 CopterSim/PX4 的 `16540/17540`、`16541/17541`。
- 两机 FAST-LIO 原点独立；不得把 swarm trajectory broadcast 当作可靠机间防撞。当前机间安全依赖本机 Mid360→grid map→replan/`EMERGENCY_STOP`。
- 主赛道源是 `config/maps/predicted_narrow_course_v1.json`。不安装 UE Editor，不覆盖外部 CopterSim/RflySim 资产。
- ROS overlay 顺序是 ROS Noetic→`third_party/ego-planner-swarm/devel`→`future_aircraft_ws`。

## Ownership

- 人类默认拥有 `future_aircraft_ws/src/future_aircraft_mission/` 中的比赛行为、任务策略和控制意图。
- Agent 默认维护仿真编排、地图、项目侧 adapter、诊断、维护脚本、文档及其测试。
- ROS 接口、launch 组合、package manifest 和任何影响 PBL-1 的文件是 change-gated shared boundary；修改前向用户说明 evidence、影响、风险、rollback 和 validation。
- `multi_uav_mission` Python/launch 基线与 `scripts/lifecycle/` 冻结；lifecycle/launcher 代码修改属于 Yellow Zone。
- `third_party/ego-planner-swarm`、Faster-LIO/PX4 核心、共享坐标系和 watchdog/geofence 大改也是 Yellow Zone。
- 原 `28com_sim`/`28com_uav` 和已安装工具链只作参考，不作为项目 workaround 修改。

## Protected Baseline

PBL-1 必须保持：双机 identity/isolation、Faster-LIO 稳定、MAVROS connection、odom freshness、OFFBOARD/arming/takeoff、EGO planning、setpoint bridge、错时全路线、watchdog/geofence 语义和感知式防撞。

任何增量按以下顺序升级，不跳级：

```text
L0 lidar_only PBL-1
→ L1 + RGB
→ L2 + Depth transport（不依赖 planner）
→ L3 validated Depth→EGO fusion
```

已验证约定包括 `FAST-LIO extrinsic_T=[0,0,0.1]`、主飞行位置 `/uavX/mavros/local_position/odom`、raw localization `/uavX/slam/odometry_raw`。不要凭 ENU/NED 直觉改变符号或混淆 MAVROS odometry in/out。

## Task Routing

- 启动、端口、WSL、MAVROS：先读 `.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md`，再看 lifecycle manifest/health 与 Stage 2/2.1 evidence。
- 无法起飞：sim/PX4/MAVROS→readiness 五门→local odom freshness→watchdog→OFFBOARD→arm→setpoint→PX4 response。
- 能起飞不导航：mission goal→EGO acceptance→odom/cloud→`/planning/pos_cmd`→setpoint bridge→MAVROS setpoint→PX4。
- 传感器回归：`lidar_only`→+RGB→+down camera→+Depth transport→Depth fusion，找到最小失败增量。
- 控制链异常：使用只读 `run_stage8_control_chain_recorder.bat`；不靠增大 timeout 或关闭 watchdog 隐藏根因。
- 历史症状只从 [`docs/incidents/`](../docs/incidents/) 复用诊断方法；当前路线与 active engineering state 只从 [`docs/current/`](../docs/current/) 读取。

## Testing Ladder

```text
T0 focused static/offline contract
→ T1 relevant repository / Stage validators
→ T2 live no-arm identity/isolation/odom/TF/input
→ T3 single UAV
→ T4 dual takeoff/hover
→ T5 short navigation
→ T6 full PBL route
→ T7 fresh-instance repeatability
```

纯文档不机械运行 live。可能影响 PBL-1 时至少覆盖 Stage 7/8 离线门并按风险升级 live。一次成功可继续开发；稳定 baseline 至少 3 次 fresh-instance。离线 PASS 不能表述为 live PASS。

## Live Entry Commands

```powershell
.\sim.ps1 doctor
.\sim.ps1 start                     # DryRun
.\sim.ps1 start -Execute            # 状态变更，遵守 AGENTS Red-Zone
.\sim.ps1 status                    # 只读
.\sim.ps1 stop                      # DryRun
.\sim.ps1 stop -Execute             # 真实进程停止需用户明确授权
```

Live flight chain：

```bat
scripts\run_live_fastlio_dual.bat
scripts\run_live_ego_swarm_dual.bat
scripts\run_stage7_topic_probe.bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

只有当前 run readiness 的 identity、schema、freshness、isolation、stationary_stability 全 PASS，且 policy `allow_arm=true` 时才允许仿真 arm。真机始终人工 arm/Offboard。所有 stop/fresh-instance 必须基于 manifest 的 PID+start-time+command fingerprint ownership；unknown/stale/端口冲突 fail closed。禁止恢复 hazard tombstone、名称扫杀、`wsl --shutdown`、自动 force retry 或隐式 arming。

## Truth Priority

冲突时按以下顺序：fresh live evidence→当前 run-scoped artifacts→用户明确的最新状态→当前代码/launch/config 行为→当前离线测试→Current Truth 文档→incident/旧计划/旧日志→推测。

一次进程启动不证明 mission 成功，一份旧 readiness 不授权新 instance。Fresh evidence 改变状态后，同步更新根 README、本节和 `docs/current/`，不要让历史事故留在 Current Truth。

## Handoff Format

- **Changed**：文件与行为边界。
- **Evidence**：观察、责任层和为何不是旧 incident。
- **Validation**：命令、exit code、offline/live 层级和 artifacts。
- **Remaining Risk**：尚未证明的 live parity、环境或边界。
- **Next Recommended Step**：下一最小动作。

允许本地 commit；未经用户许可不得 push。提交前检查 diff、受保护路径、secret/generated logs 与 WSL shell LF。
