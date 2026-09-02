# Competition Course V2 Navigation Baseline — 设计文档

> 日期：2026-09-01
> 状态：Design Approved with implementation amendments
> 前置门：Competition Course V2 `MAP READY`
> 范围：UAV1 / Section A / LiDAR-driven EGO / no truth-assisted avoidance

## 1. 目标与关闭条件

建立 Competition Course V2 的第一个可信、可重复单机导航基线。完整能力链为：

```text
UAV1 spawn -> takeoff -> EGO goal -> Section A
-> static box -> moving pendulum -> endpoint settle
-> AUTO.LAND -> confirmed disarm
```

本轮依次完成：

1. 1 次 Section A 前段 clear-path short smoke；
2. 1 次完整 Section A diagnostic success；
3. 3 次连续 fresh-instance 完整 Section A success。

只有以上全部通过且 collision/clearance evidence 足够，状态才可写为 `CLOSED`。飞行成功但
repeatability 或 collision evidence 不完整时必须写 `PARTIAL`；sensor/planner/integration 或
受保护层阻塞时写 `BLOCKED`，并指出责任层。

## 2. 非目标与冻结边界

本阶段不包含：

- Corner A、Section B/C 或完整 corridor；
- UAV2 飞行或双机协调；
- 动态障碍相位、轨迹或时间真值注入；
- EGO-Swarm 内部、EGO 参数或 Faster-LIO 参数调整；
- 新 shared-world TF；
- mission C++、现有双机任务行为或 PBL-1 route 修改；
- lifecycle、ownership、spawn attestation 或 cleanup 语义修改。

保持已验证的双机基础设施、传感器、定位和 planner 进程，但只允许 UAV1 进入 OFFBOARD、
arm 和接收 planner goal。UAV2 在整个 active flight interval 必须持续受监控并保持
`armed=false`、`mode!=OFFBOARD`。

## 3. 架构选择

采用隔离的 V2 单机 opt-in 入口：新增 V2 navigation config、plan generator、runner、
只读 evidence collector/report 与 focused tests，复用现有 Faster-LIO、EGO、setpoint bridge、
mission executor 和 MAVROS/PX4 safety gate。

现有 `stage7_flight_plan.py`、Stage 8 PBL route、PBL-1 runner 和双机 mission behavior
保持不变。不另写 mission framework，也不复制 OFFBOARD/takeoff executor。

## 4. Gate 0：runtime map contract hardening

`config/maps/competition_course_v2.json` 继续是 runtime single source of truth。
RflySim loader 不得无条件信任 generated entity manifest：runtime 从 validated spec 调用
`build_entity_manifest(spec)` 得到 expected entities。generated manifest 仅为 debug、preview
和 parity evidence；若 loader 仍读取它，必须逐字段比较完整 payload，任何缺失、增加、排序外
内容变化或 metadata mismatch 都 fail closed。只比较 `spec_sha256` 不够。

`competition_course_ue_loader.py --dry-run` 必须在输出前完成：

1. spec validation；
2. expected manifest derivation；
3. generated/expected full parity；
4. entity payload validation。

删除 `_create_marker` 内重复的 `asset_transaction` assignment，不扩展 loader/lifecycle 架构。

## 5. 地图和坐标数据流

```text
competition_course_v2.json
        |              \
        v               v
runtime entity derive   V2 plan generator
        |               |
        v               v
RflySim geometry    UAV1 local EGO goal
        |               |
        +-> Mid360 -> Faster-LIO/local map -> EGO -> PositionCommand
```

plan generator 从 spec 读取 spawn、spawn yaw、Section A start/end、obstacle metadata 和
clearance policy。navigation config 只定义 altitude、timeouts、tolerance、settle policy 和
diagnostic mode，不复制 `20.5/22.0/23.0` 等地图坐标。

world ENU 到单机 local 的 canonical planar rigid transform 为：

```text
delta_world = world_point - spawn_world
local_xy = R(-spawn_yaw) * delta_world_xy
```

inverse 使用 `world_xy = spawn_xy + R(spawn_yaw) * local_xy`。必须测试 yaw `0/+90/-90/180°`、
非零 translation、Section A endpoint，以及 local→world→local round trip。当前 V2 UAV1
spawn `(16.0,-0.7)`、yaw `0°`，Section A endpoint `(23.0,0.0)`，因此测试期望 local
endpoint 约 `(7.0,0.7)`；runtime 仍必须从 spec derive。该 helper 不发布 TF，也不改变
两机独立 localization origin。

## 6. V2 plan profiles 与执行序列

同一 plan generator 支持两个显式 profile：

- `short_smoke`：目标由 Section A start 加一个沿线 offset 派生，且经几何检查位于
  `static_box_a` 和 `moving_pendulum` 之前；
- `full_section_a`：只发布真实 Section A endpoint。

共同序列为：

1. current-run readiness/stack/simulation identity validation；
2. 等待 UAV1 MAVROS、odometry、Faster-LIO、registered cloud、EGO topics；
3. 复用 warmup setpoint → OFFBOARD → arm → direct MAVROS takeoff setpoint；
4. 切入 EGO，仅发布一个 profile terminal planner goal；
5. 记录 Section A along-track progress 和 obstacle-region passage；
6. 对真实 terminal point 执行 position/speed continuous settle；
7. 调用 AUTO.LAND，确认 touchdown/low altitude 和 disarm；
8. 生成 run-scoped report。

进入导航后，EGO/setpoint bridge 是唯一导航 position command 来源。runner/mission 不得持续
发布竞争 MAVROS position setpoint。UAV2 不生成 OFFBOARD、arm、planner goal 或 navigation
action，只作为 safety/evidence monitored vehicle。

stage 语义使用 `preflight/takeoff/v2_navigation/terminal_settle/landing/report` 或等价单机
名称，不冒充 `collaborative_navigate` 或已经发生双机任务。

## 7. Progress evidence 与 terminal acceptance

沿线 progress 与 terminal settle 是两个独立证据：

- progress history 证明 UAV 穿过 entrance、static obstacle region 和 dynamic obstacle region；
- terminal acceptance 始终使用 endpoint point-goal 的 3D Euclidean distance。

`verify_planned_navigation` 现有 point-distance 与 `course_s` 是二选一语义，不能用 progress
代替 endpoint acceptance。V2 terminal verify 不使用 `course_s` success predicate；progress
由只读 recorder/report 独立计算。

允许在受保护的 `mission_executor.py` 增加两个 opt-in、向后兼容字段：

- `settle_duration_s = 3.0`；
- `maximum_speed_mps = 0.15`。

V2 同时使用现有 `tolerance_m = 0.25`（3D Euclidean）。只有 position inside tolerance 且
speed 不超过上限连续成立满 settle duration 才成功；任一条件失效，timer 清零。旧 plan
未提供字段时保持立即成功行为。planner command 计数在 settle 等待期间继续累计并保留。

风险是稳定计时错误导致提前通过或延迟降落；rollback 是删除这两个可选字段及其 focused
tests。验证覆盖旧行为、连续成功、speed reset、position reset、intermittent non-accumulation、
timeout 和 planner evidence preservation，再运行 Stage 7/8 regression。

## 8. AUTO.LAND 和 disarm contract

V2 landing action 显式设置：

```text
require_disarmed: true
disarm_timeout_s: bounded value
```

成功必须同时具有 AUTO.LAND request/confirmation、touchdown/low-altitude condition 和最终
`armed=false`。report 记录独立 `disarm_confirmed` evidence。旧 plan 未启用
`require_disarmed` 时维持当前 landing behavior。

focused tests 覆盖：低高度但仍 armed 不完成、touchdown 后自动 disarm 完成、等待 disarm
timeout，以及旧计划不变。该 opt-in 改动与 terminal settle 同属已批准的最小 Yellow-Zone
executor 修改。

## 9. Runtime data 与 evaluation truth 隔离

规划/mission 只允许使用 Mid360、Faster-LIO/EGO local map、MAVROS odometry、planner state/
command、watchdog 和 geofence。摆障相位、周期真值、未来轨迹和 simulator entity pose 不得
进入 goal、wait、avoidance 或 control decision。

独立只读 recorder/report 可以使用 spec、RflySim entity pose、simulator vehicle pose 和生成
几何进行 post-flight clearance、passage、collision assessment 和 evidence annotation，但不得
发布任何 planner/control ROS topic。report 必须写：

```text
runtime_decision_source = lidar_driven
evaluation_truth_used = true | false
```

动态障碍成功不能只由 topic activity 推断。至少关联 LiDAR temporal change、PositionCommand、
UAV passage time 和实际 trajectory；可靠同步 entity truth 可用于 evaluation-only dynamic
clearance，否则写 `dynamic_clearance_m = unavailable`。

## 10. Evidence collector 与报告

新增 run-scoped 只读 collector，active flight interval 持续采样 UAV2 `/mavros/state`，记录
sample count、interval、first/final state 和 violations。任一样本 `armed=true` 或
`mode=OFFBOARD` 都使 run 失败。不得修改 UAV2 planner/launch。

V2 report 不读取 generic executor 的 synthetic `min_uav_distance=0.85` 作为任何实测指标。
本阶段无 inter-UAV distance KPI。

collision/clearance 字段必须标明 `measured/derived/simulator_evaluation/unavailable`。缺少权威
collision signal 时，不能因“无 collision log”写 `collision_count=0`。优先用 time-aligned UAV
trajectory 加 wall/static polygons 计算并至少报告：

- `minimum_wall_clearance_m`；
- `minimum_static_obstacle_clearance_m`。

如果没有足够强的 collision evidence，即使导航成功也只能写
`NAVIGATION SUCCESS / COLLISION EVIDENCE INCOMPLETE`，不能关闭 baseline。

## 11. 单次 full Section A success contract

UAV1 必须证明：current stack/instance identity、OFFBOARD、arm、takeoff altitude、goal accepted、
planner commands > 0、meaningful along-track progress、通过 static/dynamic regions、到达真实
endpoint、0.25 m tolerance、0.15 m/s maximum speed、3 s settle、AUTO.LAND、low altitude 和
disarm。

UAV2 必须在整个 active interval 保持 disarmed 且非 OFFBOARD。

安全证据必须证明无 unexpected OFFBOARD loss、watchdog/geofence trip、executor error 和
known collision，并具有可接受的 wall/static clearance。感知/规划证据必须包含 static region
LiDAR、dynamic temporal change、navigation PositionCommand 和 obstacle-region trajectory，且
明确没有 truth-assisted avoidance。

## 12. Gate 与 failure policy

```text
Gate 0  runtime map parity hardening
  -> Gate 1  offline plan/executor/runner/report contracts
  -> Gate 2  focused + Stage 7/8 + map/loader regression
  -> Gate 3  current-instance no-arm planner-chain verification
  -> Gate 4  armed short smoke
  -> Gate 5  full Section A diagnostic
  -> Gate 6  3 x fresh-instance repeatability
```

full diagnostic 遇到摆障失败时先分类：LiDAR 未观察、cloud→EGO 输入断、occupancy 更新/清除、
无可行 trajectory、bridge/control 未执行、或物理无安全窗口。默认冻结 EGO/Faster-LIO。
只有 evidence 证明是 V2 integration bug 才直接修复；若 blocker 属于当前 planner/config
behavior，报告 `BLOCKED_BY_CURRENT_PLANNER_BEHAVIOR`，不偷偷调 EGO 参数。

重复验收使用完全相同 map spec、V2 config、planner/Faster-LIO config 和 thresholds。任一次失败
将连续计数清零，RCA/修复后从 1/3 重启。

## 13. Red-Zone 执行边界

任何真实 stack start/stop/fresh-instance、OFFBOARD 或 arm 前，必须展示 exact command、
DryRun、stack id、simulation instance id、owned PID/PGID、ownership evidence、stop order 和
fail-closed 行为，并取得用户明确授权。

unknown/stale ownership 或未知端口占用时 fail closed；不 kill unknown process、不自动 force
retry、不名称扫杀 PX4/ROS/RflySim、不执行 `wsl --shutdown`。授权范围不自行扩大。

## 14. 实现与验证边界

预期新增/修改：

- V2 navigation config、canonical transform helper 和 plan generator；
- V2 opt-in Windows/WSL runner；
- run-scoped safety/evidence collector 与 report；
- mission executor opt-in terminal settle/disarm contract；
- loader runtime manifest hardening；
- focused tests、authoritative docs 和 acceptance evidence。

offline 至少运行 executor focused tests、V2 transform/plan/report tests、Stage 7/8 relevant
regression、map validator 和 loader dry-run/parity tests。Gate 3 no-arm 验证 current identity、
MAVROS state、odom freshness、Faster-LIO、registered cloud、EGO topics、PositionCommand path 和
V2 goal/frame semantics；stale/unknown instance fail closed。

实现完成后只关闭 `Competition Course V2 Navigation Baseline — UAV1 Section A`，随后停止；
不得继续 Corner A、其余 corridor、UAV2 navigation、双机、OpenVINS、视觉识别或精准降落。
