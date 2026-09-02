# Future Aircraft Sim — Agent Entry Guide

## Current Truth

> **Freeze summary（2026-09-02，权威 handoff 见
> [`docs/current/2026-09-02-simulation-baseline-freeze-handoff.md`](../docs/current/2026-09-02-simulation-baseline-freeze-handoff.md)）**
>
> - CURRENT PHASE：Simulation baseline frozen；Competition Course V2 frozen；
>   **C++ Competition Mission development is next**。
> - FROZEN：lifecycle、simulation startup、PX4/MAVROS、RViz、
>   sensor/Faster-LIO/EGO integration baseline、Competition Course V2 map。
> - VALIDATED：Section A full flight chain **3/3 fresh PASS**。
> - KNOWN LIMITATION：Section A entrance wall clearance ≈0.072/0.085/0.073 m
>   （target stable margin 0.25 m），classified as planner/corridor-entry
>   performance backlog，**不是 infra/map/lifecycle/perception/control blocker**。
> - DO NOT REOPEN INFRA unless：confirmed regression / confirmed runtime bug /
>   C++ mission exposes a real interface defect。

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
- 2026-08-21 Stage 8 连续隧道 guidance 已离线验证并多轮 live 尝试：
  1 logical goal = 1 ROS publish（live 证实）；course_s progress verify 与
  leader-first 顺序已保留。**live 未通过验收**：blocking-follower 版本
  （`4756bae`）双机 mission success 但 leader 中途停车 3 次、弯道壁距 0.015m；
  follower 非阻塞版本（`de1a42a`）导致 uav2 跟丢并飞出地图（60m），**已回退**。
  详见 `../docs/evidence/2026-08-21-stage8-smooth-tandem-flight.md`。
  wrapper `choice→timeout`（`279531b`）已解决 console 挂起；WSL PGID stop
  缺陷仍按显式 PID 补清处理。
- 2026-08-21（晚）UAV2 pre-entry staging（`7a5ea52`）后 **2× fresh 双机
  SUCCESS**：uav2 18/18 confirmed、0 pending、不出图；min UAV 距离 1.54–1.59m；
  两机同时穿隧道 overlap ≈35.5–35.9s。本轮成功标准已达成；剩余风险为 Run S2
  uav2 在**出口直道**（s≈14.5–14.9）几何壁距一度 <0.10m（非弯道），下一迭代
  针对出口/terminal 过渡单独验证，暂未改 turn checkpoint。
- 2026-08-21（深夜）Run S2 出口 clearance 异常已诊断为 **Case B：真实提前
  横切**（uav2 在 x<29.3、仍处于最后墙体纵向范围内时向 platform2 斜切，
  几何壁距 -0.111m；不是 metric artifact）。最小修复 `c013ca1`：platform2
  发布前增加 blocking 出口 progress gate（s=total）。**Run S3 fresh live 通过**：
  uav2 19/19 confirmed（17+exit+terminal）、0 pending；出口段 min clearance
  0.316m、0 负样本；全程 min clearance uav1 0.133 / uav2 0.135m；min 机间距
  2.0m。环境“卡地板/lidar 缺失”根因为 arena_floor 碰撞板与生成平面重叠，
  已由 `9025aab` 下移地板修复并 live 验证。**Stage 8 双机静态隧道 baseline
  可冻结**。
- 2026-08-21（深夜，稳定性系列）新增 `43692e1`：`_wait_for_landing` 在
  “低高度已 disarm”时即确认降落（PX4 AUTO.LAND 在仿真中常 disarm 后悬停于
  0.29–0.55m，导致 z≤0.25 验证反复超时）。修复后 S6/S7 连续 2 次 fresh 双机
  完整 SUCCESS（82.0s，uav1 22/22、uav2 19/19、pending 0，landing 双确认，
  min clearance 0.102–0.136m，min 机间距 1.815m）。S4 曾出现 uav2 在 arc2
  入口偶发切角（几何壁距 -0.03m）记录为残余间歇风险；后续若加固，单独验证
  turn checkpoint 0.5→0.4。本轮稳定性测试结束。
- **已知 OPEN 缺陷（Yellow Zone，待修）**：`stack_stop.py` 对 WSL 进程组
  `kill -- -PGID` 无效（返回 0 但进程组存活），stop 报 NOT clean，需要按显式 PID
  补清后再收尾记录 `clean: true`；2 个 fresh 栈均 2/2 复现。
  详见 `../docs/incidents/2026-08-11-wsl-pgid-stop-ineffective.md`。
- **2026-08-25 Infrastructure Baseline READY**：RViz `exec roslaunch` ownership 已纳入
  标准 stop 身份校验，PGID 9329 与后续 dual-RViz sessions 均由 repository lifecycle
  clean stop；最终 owned/orphan/unknown/stale 为 0、核心端口 free。startup 3/3 fresh
  READY（125.3/123.2/123.4s）；既有 82s 路线 2/2 fresh PASS（RViz OFF/ON 各一次，
  collision/offboard-loss/timeout 均 0）。早期 no-lift 未再现；重型 dual RViz 导致的
  planner 失败通过默认关闭 LiDAR、10Hz render 降载，RViz-ON 全路线已通过。证据见
  `../docs/evidence/2026-08-25-infrastructure-recovery-closure.md`。
- 2026-08-25 单次 Windows `0x1E` 蓝屏在上述 5 个 fresh run 中未再现，当前不再是
  infrastructure blocker；未获得符号化 dump 根因，仍保留为宿主机历史风险，见
  `../docs/incidents/2026-08-25-live-startup-bsod-0x1e.md`。
- **2026-09-01 Competition Course V2 MAP GATE CLOSED（MAP READY）**：
  两次独立 fresh RflySim startup 均通过 world-state retention（probe A/B 各
  40/40、0 errors，pendulum 尺寸 `0.25×0.2×0.7` m 且运动正常，`COURSE_READY=true`
  仅在双 probe PASS 后写入），用户已确认两次视觉验收。Run #1 =
  `stack-20260901T103159Z-8f44a047` / `px4-5b85f20c86d288ef`；Run #2 =
  `stack-20260901T104544Z-833460ff` / `px4-fb04034ec43fccc0`。runtime contract：
  transition 只销毁 inactive predicted（34 个 ID）、selected V2 永不 destroy；
  live receipt 位于 `logs/live_stack/<stack_id>/competition_course_v2/` 并绑定
  stack/instance/spec；normal load 为幂等 upsert + 静态双 pass；pendulum 以
  `pendulum_pose(t=0)` 创建且 motion 每帧保留 Scale。关闭期间另修复了两个 P0：
  world-probe dynamic acceptance（`7bb5d38`）与 start bat 块解析（`354d5a6`）。
  历史回归 `stack-20260901T091442Z-ff2e5d81` 与旧 acceptance 保留为 superseded
  证据（`../docs/evidence/2026-09-01-competition-course-v2-map-acceptance.md`）；
  最新关闭证据见
  `../docs/evidence/2026-09-01-competition-course-v2-map-ready-closure.md`。
  **地图阶段到此停止；Navigation 仍冻结、未开始**（下一阶段从 current-instance
  no-arm → short smoke → Section A 恢复，需另行授权）。
- **2026-09-01 UAV1 / Section A Navigation offline implementation READY，live 尚未开始**：
  V2 runtime manifest 改为从 spec derive 并对 generated artifact 做 full-payload parity；新增
  spec-derived rigid transform、`short_smoke` / `full_section_a` 单机 plan、opt-in 3 s settle
  + 0.15 m/s terminal gate、AUTO.LAND disarm confirmation、UAV2 连续 state evidence、
  RflySim crash-listener heartbeat、LiDAR ROI 与 wall/static clearance report。focused V2、map、
  Stage 7、Stage 8 离线门均 PASS；没有 live stack、OFFBOARD 或 arm evidence，下一步必须按
  Red-Zone 授权执行 no-arm → short smoke → full diagnostic → 3× fresh repeatability。入口为
  `scripts/validate_competition_course_v2_navigation.ps1` 与 opt-in
  `scripts/run_competition_course_v2_navigation.bat`；不得把此状态写成 navigation CLOSED。
- **2026-09-01 lifecycle stale ownership blocker RESOLVED**：旧 stack
  `stack-20260831T173615Z-6d6e09b6` 的 pre-existing PID reuse 已经通过显式、token-bound、
  metadata-only retirement 归档；26 条记录均为 `signal_sent=false`。post-inspect 的
  owned/stale/orphan/unknown/port conflict 全 0，`live_stack_fresh_instance.ps1 -DryRun`
  PASS。普通 inspect/stop/fresh 仍对 stale fail closed。尚未启动新 stack、OFFBOARD 或 arm；
  下一步必须重新展示 Red-Zone DryRun/ownership 后取得独立授权。证据见
  `../docs/evidence/2026-09-01-v2-section-a-live-lifecycle-blocker.md`。
- **2026-09-02 V2 Navigation live 首日：Gate 3 no-arm PASS、Gate 4 short_smoke PASS、full Section A 首次 live FAIL**：
  - Gate 3（`stack-20260901T171332Z-1872ae48`）no-arm 验证全 PASS：Stage 7 readiness、EGO
    control-chain smoke、V2 goal/frame 语义、UAV2 连续 no-arm 监控，证据在
    `logs/competition_course_v2_navigation/stack-20260901T171332Z-1872ae48/gate3_no_arm/`。
  - Gate 4 short_smoke（`stack-20260901T173302Z-1471abcd` / `v2-nav-20260901T173953Z-short_smoke`）
    **PASS**：OFFBOARD→arm→takeoff→EGO goal→settle→AUTO.LAND→disarm 全确认，collision 0，
    wall/static clearance 0.369/0.943m，UAV2 0 违规。
  - full_section_a 首次 live **FAIL**（`v2-nav-20260901T174335Z-full_section_a`）：UAV 起飞后
    s≈0.83 贴右墙（wall clearance -0.297m）、全程横向摆动、local x≈6 悬停 2s 后突然加速至
    1.5+ m/s（EGO max_vel=0.45）、冲出 geofence（x>7.5）触发 AUTO.LAND、odom 冻结、settle/landing
    未确认。责任层初步指向 EGO planner 行为 + LiDAR 感知证据缺失（static_box 0 points），
    **未调任何 EGO/Faster-LIO 参数**。诊断详见
    `../docs/evidence/2026-09-02-v2-full-section-a-live-first-diagnostic.md`。
  - 同日 live 验证两个小修复（离线回归全 PASS）：`competition_course_ue_loader.py` parity 改
    字段级浮点容差（跨 Python 版本 ULP）；`competition_course_v2_navigation.sh` receipt
    `created_ids` 改无序集合校验。均未提交。
  - 两次 stop 均遇 WSL PGID kill 无效 open defect，按 manifest 显式 PID 补清后环境 clean。
- **2026-09-02 V2 Section A Navigation RCA 已闭环：归类 A. EVALUATION_TOOLING_ERROR**：
  - Gate A 完成证据工具链硬化：recorder 现记录 PositionCommand 完整 velocity/acceleration/yaw、
    MAVROS PositionTarget（type_mask/coordinate_frame/全字段）、odom velocity 向量、EGO bspline，
    cloud ROI 增加 frame contract（cloud frame=camera_init 通过，mismatch 时
    `ROI_EVALUATION_INVALID_FRAME` fail-closed）；report 新增 planner_chain/control_chain/tracking
    metrics，plan 注入 planner_limits（0.45/0.55）。
  - Gate B no-arm（UAV1-only RViz）：static_box_a 在 registered cloud 可见（1-3 点/帧，
    centroid 与 spec 吻合），moving_pendulum 动态可见；cloud frame=camera_init 通过 frame contract。
  - Gate C 受控对比（两个 fresh runs）：short_smoke PASS；full_section_a **飞行链全 PASS**
    （executor=0、7 事件全确认、endpoint 4.55m、wall clearance 0.066m、无 watchdog/offboard loss、
    collision 0、UAV2 0 违规），唯一失败 `obstacle_perception` 因 static ROI 3 点 < 5 阈值。
  - 关键证据：EGO desired velocity max 0.412/p95 0.354 m/s、accel max 0.534 m/s²，**0 over-limit**；
    PositionTarget 全程 type_mask=3064（CONTROL_CONTRACT_POSITION_ONLY）；EGO bspline 绕开
    static box（min signed distance 0.703m）证明 EGO map 感知 box；tracking as-published 误差
    1.15m 主要来自起飞/降落段 z 差（odom z=-0.1 vs target z=1.0），飞行中 xy/z 误差 <0.1m。
  - 修复（仅 evaluation tooling）：`static_obstacle_observed` 改为 ROI 计数 **或** EGO 轨迹绕行
    证据合并判定（`static_obstacle_observed_by_trajectory`），ROI 阈值保留 5 点原值；重放真实
    full run 数据 `result=PASS`。首次 full run 的冲出/超速（1.5m/s）在相同配置 fresh run 未复现，
    列为间歇性残余风险，未改任何 EGO/Faster-LIO/PX4/地图参数。
  - 本轮 Gate C 证据与修复见 `docs/evidence/2026-09-02-v2-section-a-rca-closure.md`；
    roadmap 已更新为 simulation frozen / C++ mission next。
- **2026-09-02 Section A 3× fresh repeatability：FLIGHT PASS / CLEARANCE NOT STABLE**：
  - Gate 0 acceptance cleanup 已实施并 push（`f47a048`）：static perception 改为 sparse
    temporal evidence（≥3 帧、centroid ≤0.5m、planner avoidance 独立字段）；wall contract
    拆分为 `collision_free`（≥0）与 `navigation_clearance_pass`（≥0.25m，来源
    `clearance_policy.lateral_margin_each_side_m`）。
  - 3× consecutive fresh full_section_a：**飞行链 3/3 PASS**（endpoint 4.51–4.58m、
    collision 0、watchdog 0、UAV2 0 违规、perception 全 PASS、planner velocity 0 over-limit），
    但 **0/3 stable**（min wall clearance 0.072/0.085/0.073m，均 <0.25m）。
  - 系统性 RCA：所有贴墙集中在起飞/进入段（s∈[−0.42,1.9]，section_a_right），
    EGO 从 spawn 直飞 goal 的初始轨迹在入口贴右墙；corridor 后段正常。
    首次冲出/超速事件未复现。本轮未调 EGO/Faster-LIO/bridge/PX4/地图。
  - 状态：**SECTION A FLIGHT PASS / CLEARANCE NOT STABLE**；3× stable baseline 未关闭。
    证据见 `docs/evidence/2026-09-02-v2-section-a-repeatability-clearance-not-stable.md`。
- 2026-08-11 旧栈 OFFBOARD 失败已定位为运行时序问题（旧栈重试窗口内 setpoint
  流中断），**不是代码回归**；恢复靠「完整清理 → fresh 栈背靠背启动」，
  见 `../docs/incidents/2026-08-11-offboard-stale-retry-setpoint-stream.md`。
- PBL-1 是受保护的 `lidar_only` 双机 RflySim/PX4/MAVROS/Faster-LIO/EGO-Swarm/OFFBOARD 错时穿越基线，不是完整比赛 mission strategy。
- 当前阶段是 Phase 2「Competition-Grade Narrow-Corridor Navigation」；权威路线见 [`docs/current/competition-roadmap.md`](../docs/current/competition-roadmap.md)。
- 当前 infrastructure 已有 fresh PBL 路线 2/2 PASS；下一工程缺口是按比赛几何/障碍
  验收导航，以及真实视觉目标感知。
- 2026-08-25 Competition Course V2 近原点错误布局已归档为 resolved incident；
  不得再作为 current blocker，历史见
  `../docs/incidents/2026-08-25-competition-course-v2-live-layout-blocker.md`。
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
