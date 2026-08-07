# Future Aircraft Sim — Agent Engineering Handbook

> 适用仓库：`s1nyon/RflySim-FutureCraft`
>
> 角色：本文件是本仓库面向开发 Agent 的**详细权威工程手册**。根目录 `AGENTS.md` 保存硬规则，本文件解释当前工程事实、架构、决策依据、调试方法和开发路线。涉及 RflySim/PX4/MAVROS/WSL 工具链细节时，同时读取 `.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md`，不要在本文件里凭经验重建外部工具链约定。
>
> 状态基准：2026-08-07，结合仓库当前 `main` 与用户对最新 live 状态的明确确认整理。

---

## 0. Agent 进入仓库后的 5 分钟规则

第一次进入任务时，不要马上改代码。先回答下面五个问题：

1. **当前任务属于哪一层？**
   - simulator / sensor bridge / localization / MAVROS/PX4 / planner / mission / vision / tooling / docs
2. **它是否可能破坏当前 Protected Baseline？**
3. **最近一次可信的 live evidence 是哪个 run / 哪个 simulation instance？**
4. **当前看到的“问题”是 current regression，还是历史文档里的旧问题？**
5. **最小能够证明/反驳当前假设的实验是什么？**

如果这五个问题还答不出来，优先读取证据，不要开始“试参数”。

---

# 1. Project Mission

本项目面向未来飞行器创新大赛的双无人机室内协同任务，目标是在 RflySim 仿真环境中建立可逐步迁移到真实 FS-310 平台的完整能力链。

核心目标不是单独把某个算法“跑起来”，而是建立可重复、可诊断、可扩展的系统能力：

```text
RflySim environment
    ↓
Mid360 / D435i / IMU / down camera
    ↓
per-UAV sensor isolation
    ↓
Faster-LIO localization
    ↓
MAVROS / PX4 external odometry & flight state
    ↓
EGO-Swarm local planning
    ↓
setpoint bridge
    ↓
PX4 OFFBOARD control
    ↓
dual-UAV mission execution
    ↓
vision / task logic / behavior tree
```

当前工程的长期方向是：

- 双机能在狭窄环境中稳定、平滑、自主运动；
- 视觉能够识别比赛目标并提供任务信息；
- 比赛细则和地图公布后，将运动能力和视觉能力组合为完整任务系统；
- 仿真中验证过的接口、坐标、控制和感知约定尽量保持真实硬件可迁移性。

---

# 2. Current Truth — 当前唯一有效工程状态

这是本文件最重要的一节。

## 2.1 User-confirmed latest state（最高优先级）

截至 2026-08-07，用户已明确确认：

- 2026-08-07 的双机仿真结果本身**非常好**；
- 双机穿隧道能力不应再被视为“尚未攻克”；
- 之后因为引入 D435i 多传感器载荷，当前工程出现了新的集成回归；
- 该回归已按阶段策略隔离：`lidar_only` 模式下双机起飞已恢复；D435i 全载荷导致的 UE4 渲染过载/odom 断流问题已有项目侧最小修复（sensor-mode 切换，见 docs/d435i_sensor_parity_2026-08-07.md）；
- 最新 live run（`stage7-20260807T084232Z-2599`）在 `lidar_only` 下双机 OFFBOARD/arming/takeoff 全部成功，导航阶段失败 `planner_commands=0`；
- `planner_commands=0` 根因已在 2026-08-07 取证：**EGO 发布端（ego-planner-swarm devel）与 Python 消费端（28com_uav devel）的 `quadrotor_msgs/PositionCommand` md5 不一致**（`4712f060…` vs `44d620d9…`），ROS 直接丢弃连接，setpoint bridge/executor 收不到 planner 指令。修复：flight runner 与 stage8 recorder 在 28com_uav 之后、project overlay 之前 source ego-planner-swarm devel；live 复测待做。
- 2026-08-07 晚间状态更新：上述修复曾被短暂 revert（`5067c8a`），随后按用户决定重新落地（runner/recorder 的 source 顺序与 `tests/stage7_quadrotor_msgs_overlay_check.py` 静态回归检查重新加入代码），并已完成 fresh-instance live 复测（run `stage7-20260807T124153Z-22785`，实例 `px4-7e4ed24fa0881265`）：双机 OFFBOARD/arming/takeoff 成功，UAV1 导航确认 `planner_commands=190/383/116`（不再为 0），`ego_swarm_dual.log` 无任何 md5/Dropping connection。**`planner_commands=0` 的 md5 根因已 live 验证修复**。
- 当前剩余 live 阻塞（新观察，与 md5 无关）：同一 run 中 UAV1 导航进行到第 4 个 goal（`(7.9,4.7)`）时 executor 的 `/uav1/mavros/local_position/odom` 订阅在 45s 内收不到消息（`wait_for_message` 超时），executor 判失败并 AUTO.LAND/disarm；随后 UAV 快速下降触发 geofence watchdog AUTO.LAND 请求（`uav1_geofence_watchdog.log`）。
 取证要点（run `stage7-20260807T124153Z-22785`，master.log 与 watchdog 事件）：
  - **odom 流本身未断**：watchdog 事件全程 `odom_age_s` 恒 <0.034s（30Hz 连续），UAV1 实际飞到了 (7.88,4.63) 才因失败被降落；
  - executor 前 3 段导航确认成功（距离 0.293/0.298/0.300 m，`planner_commands=190/383/116`），证明 odom/pos_cmd 连接在 seq 12/14/16 正常；
  - master.log 显示 executor 从 seq 18 起以 ~60-70 次/秒的 +SUB/-SUB（odom 与 pos_cmd 交替）空转近 58s，即 `wait_for_message` 每次都在订阅连接建立窗口内收不到消息而立即超时；
  - 同窗 watchdog 与 planner 连接均正常 → 这是 executor 进程订阅连接层的失效（rospy `wait_for_message` 反复新建/销毁 subscriber 的已知低效模式在长时连接后出现问题），不是 odom 发布端/MAVLink 流问题。
  待办：复飞复现（第二次 cold-start 复飞被 readiness 10s topic 超时挡下，见下），或对 executor 改为持久订阅/缓冲 odom 后验证。

## 2.2 验证流程观察（2026-08-07 复飞时发现）

- `stage7_live_fastlio_dual.sh` 的 readiness `READINESS_TOPIC_TIMEOUT_SEC` 默认 10s。**cold-start**（上一轮 fastlio roslaunch 已清理、FAST-LIO 从零起）时，`/uav1/mavros/odometry/out`（odom_frame_relay）需要 lidar bridge → adapter → FAST-LIO 初始化后才开始输出，实测冷启动下 10s 不够，readiness 会 `timeout exceeded while waiting for message on topic /uav1/mavros/odometry/out` 失败（run `stage7-20260807T125936Z-13072`）。
- 此前多次成功是因为复用上一轮已运行的 fastlio/relay 链路（topic 已热）或时序恰好够。复飞前如清理了旧 fastlio roslaunch，应把 `STAGE7_READINESS_TOPIC_TIMEOUT_SEC` 提高到 30-60s，或等 `/uav1/slam/odometry_raw` 出现后再跑 readiness。
- 非交互会话中若同时存在自动编排与手动启动，会出现两个 `rflysim_ego_swarm_dual.launch` 互相以 “new node registered with same name” 挤掉对方（ROS 同名节点注册冲突），表现为 executor 报 `planner goal topic has no subscribers`。启动前必须确认只有一个 stage7 runner 实例。

## 2.3 P0 修复状态（2026-08-08）

- `mission_executor.py` 的 `_verify_planned_navigation()` 已改为持久 `rospy.Subscriber` +
  内存缓存（`TopicCache`，条件变量等待新消息），不再在循环内反复
  `wait_for_message()`；语义保持：goal tolerance 0.3 m、planner_commands 按
  verify 窗口内收到的新 PositionCommand 计数、45 s 超时行为与失败消息不变。
- 新增离线回归测试 `tests/stage7_persistent_navigation_subscriber_check.py`
  （5 个连续 navigation goal 只创建 1 个 odom subscriber + 1 个 planner
  subscriber），并已接入 `scripts/validate_stage7.ps1`；
  `tests/stage7_planner_control_bridge_check.py` 同步改为新语义。
- cold-start readiness：`stage7_live_fastlio_dual.sh` 在启动 FAST-LIO
  roslaunch 后新增 odom relay publisher-presence 初始化等待
  （`STAGE7_ODOM_INIT_TIMEOUT_SEC`，默认 60 s），与 readiness 的
  per-topic message timeout（10 s）分离；不再需要为提高冷启动而放大
  消息超时。
- 离线验证：`validate_stage6c/6d/7/8.ps1` 全部 PASS。
- 待办：fresh-instance lidar_only live 阶梯（cold-start readiness → 双机
  takeoff → 短导航 → 完整双机错时穿隧道）→ 至少 3 次 fresh-instance
  PBL-1 重复。

因此当前工作模型必须是：

```text
GOOD BASELINE
双机定位 + OFFBOARD + EGO-Swarm + 错时穿隧道
        ↓
CURRENT BLOCKER
executor 长航段导航 subscriber 失效（odom/planner command 收不到）
        ↓
FIX
持久 Subscriber + 内存缓存（禁止循环 wait_for_message）
```

而不是：

```text
Stage 8 从未成功
→ EGO-Swarm 仍不可用
→ 重新设计整条飞行链
```

后者是错误心智模型。

## 2.4 当前 Protected Baseline

定义：

### PBL-1 — lidar-only 双机飞行基线

PBL-1 包含：

- 双 UAV RflySim/PX4/MAVROS 启动；
- 两机独立传感器链；
- Faster-LIO 工作；
- OFFBOARD / arming / takeoff；
- EGO-Swarm 局部规划；
- 双机错时完整穿越当前窄通道/隧道路线；
- 无碰撞或不可接受的控制异常；
- 感知式机间避碰机制不被破坏。

**PBL-1 是受保护资产。**

D435i、视觉、行为树、后续群体协同增强都必须在不无声破坏 PBL-1 的前提下演进。

## 2.5 当前回归的初始责任假设

当前“加入 D435i 后无法起飞”应首先视为以下层面的集成回归候选：

1. 多传感器渲染/仿真负载；
2. RflySim `VisionCaptureApi` sensor loading；
3. sensor bridge 进程生命周期；
4. topic relay / namespace；
5. depth/RGB 帧率、timestamp 或 transport；
6. odometry freshness 受到资源竞争影响；
7. readiness / watchdog 在起飞窗口被 stale odom 触发；
8. full mode 引入后启动时序变化。

只有证据排除这些层后，才升级调查 EGO/Faster-LIO/PX4 核心。

## 2.6 仓库当前存在 documentation debt

当前 `README.md` 和旧 `.agents/AGENT2READ.md` 同时保留了：

- “双机错时穿隧道全程成功”；
- 后续 `planner_commands=0` / Stage 8 blocker 的旧记录。

这些记录在时间线上都有意义，但把它们同时写在 Current State 会让 Agent 误判。

本 handbook 的规则是：

- 历史失败保留为 diagnosis knowledge；
- 最新成功/回归才进入 Current Truth；
- 已被后续结果 supersede 的故障不得继续驱动任务优先级。

---

# 3. Truth Priority — 信息冲突时听谁的

当用户描述、README、docs、代码注释、历史日志相互矛盾时，按以下优先级处理：

1. **当前 fresh live evidence**
2. **当前 run-scoped artifacts**
3. **用户明确确认的最新工程状态**
4. **当前代码 / launch / config 的实际行为**
5. **当前离线测试结果**
6. **README / handbook Current State**
7. **历史 incident docs / 旧日志 / 旧 TODO**
8. **推测、经验和“看起来应该”**

注意：第 1 和第 3 有时顺序会互换。

- 如果 fresh live 是用户刚刚跑的、证据明确，则 live evidence 优先。
- 如果仓库里的所谓 “latest live” 实际是较早 run，而用户明确告诉你之后又跑出了新结果，则用户确认的更新状态 supersede 旧 run。

## 3.1 不允许的错误

禁止：

- 看到旧 `planner_commands=0` 就自动开始修 planner；
- 看到一份 readiness PASS 就用于另一个 simulation instance；
- 看到 README TODO 就默认该 TODO 仍未完成；
- 把离线通过当 live 通过；
- 把“曾经成功一次”自动等同“当前改动没有回归”。

---

# 4. System Architecture

## 4.1 仿真与飞控

主要组件：

- RflySim3D
- CopterSim
- PX4 SITL
- MAVROS
- WSL / ROS1 Noetic

典型多机命名空间：

```text
/uav1/...
/uav2/...
```

MAVROS 使用独立链路，不复用 CopterSim/PX4 的 Rfly SIL 端口。

当前约定：

```text
UAV1 MAVROS: udp://:14601@127.0.0.1:14600
UAV2 MAVROS: udp://:14611@127.0.0.1:14610
```

Rfly SIL/CopterSim 相关端口（如 `16540/17540`、`16541/17541`）不要拿来给 MAVROS 复用。

## 4.2 传感器层

每机主要能力：

- Mid360 LiDAR + IMU
- D435i RGB
- D435i Depth
- down-facing camera

当前 sensor config：

- `config/rflysim_sensor_uav1.json`
- `config/rflysim_sensor_uav2.json`

RflySim `VisionCaptureApi` 对 `SeqID`/`TypeID` 发布绝对 topic，因此项目需要显式 namespace relay。

重要类型：

```text
TypeID 1  -> RGB image
TypeID 2  -> depth image
TypeID 23 -> Mid360 lidar
```

## 4.3 Localization

当前定位使用 Faster-LIO。

每机有独立 local frame / origin。

FAST-LIO 原始数据和项目 normalization/relay 的关键区分见后续 Coordinate Model。

## 4.4 Planning

局部规划使用项目外部算法仓库：

```text
external/ego-planner-swarm
```

项目侧 integration 位于：

```text
future_aircraft_ws/src/multi_uav_mission/
```

主要负责：

- topic/namespace 适配；
- goal/mission 入口；
- setpoint bridge；
- planner readiness / probe；
- route / course contract；
- 双机 mission orchestration；
- run-scoped evidence。

## 4.5 Mission & task layer

任务层已经有：

- behavior tree runner
- target provider abstraction
- simulation vision provider
- mission executor
- flight plan
- score/report artifacts

但当前阶段不要让视觉/行为树成为 PBL-1 的启动前提。

---

# 5. Repository Map

## 5.1 根目录

```text
AGENTS.md                  强制硬规则
README.md                  面向人的项目概览
.agents/                   Agent handbook / toolchain notes
config/                    JSON 配置、地图和阶段契约
scripts/                   Windows 启动、验证、WSL wrapper
future_aircraft_ws/src/    项目 ROS1 源码
external/                  独立算法仓库（谨慎修改）
tests/                     离线 contract / regression tests
docs/                      设计、事故记录、决策
logs/                      live run evidence（运行生成）
generated/                 deterministic course artifacts（运行生成）
```

## 5.2 `multi_uav_mission` 关键 launch

```text
future_aircraft_ws/src/multi_uav_mission/launch/
├── predicted_narrow_course.launch
├── rflysim_ego_swarm_dual.launch
├── rflysim_ego_swarm_single.launch
├── rflysim_fastlio_dual.launch
└── rflysim_mavros_px4.launch
```

## 5.3 `multi_uav_mission/scripts` 关键模块

飞行/任务：

```text
mission_executor.py
stage7_flight_plan.py
ego_swarm_adapter.py
ego_swarm_setpoint_bridge.py
mavros_setpoint_keepalive.py
behavior_tree_runner.py
```

定位/坐标/契约：

```text
odom_frame_relay.py
odom_tf_contract_check.py
rflysim_pointcloud_adapter.py
rflysim_cloud_contract.py
```

传感器：

```text
rflysim_sensor_bridge.py
stage7_sensor_readiness.py
stage7_topic_probe.py
```

安全/诊断：

```text
course_geofence.py
course_geofence_watchdog.py
stage8_control_chain_recorder.py
stage8_dynamic_lidar_probe.py
check_swarm_obstacle.py
flight_event_recorder.py
```

证据/报告：

```text
stage7_run_artifacts.py
stage7_flight_report.py
score_summary.py
```

视觉/目标：

```text
target_provider.py
sim_vision_target_provider.py
```

---

# 6. Protected Baseline Model

以后不要只用 “Stage 7 / Stage 8 完成了吗” 描述能力。

使用 **PBL — Protected Baseline** 管理已经验证过的系统能力。

## 6.1 PBL 的意义

一个能力进入 PBL 后：

- 后续 feature 默认不得改变其行为；
- 任何可能影响它的改动必须做 regression validation；
- 发现回归时首先 diff 新 feature；
- 不允许以“新功能更先进”为理由接受旧能力退化，除非用户明确同意 tradeoff。

## 6.2 当前 PBL-1

```text
PBL-1 = lidar_only dual-UAV tunnel-flight baseline
```

必须保护：

- sensor isolation
- Faster-LIO stability
- MAVROS connection
- odom freshness
- OFFBOARD entry
- arming
- takeoff
- EGO planning
- setpoint bridge
- staggered dual route
- geofence/watchdog semantics
- perception-based collision avoidance

## 6.3 如何升级 PBL

D435i 修复后可以形成：

```text
PBL-2 = PBL-1 + RGB enabled without flight regression
PBL-3 = PBL-2 + depth transport enabled without planner dependency
PBL-4 = PBL-3 + validated depth-to-EGO fusion
```

不要跳级。

---

# 7. D435i Development Policy

用户选择的路线是 **C**：

> RGB/Depth 都要，但当前先完成视觉侧独立能力；后面再把 Depth 正式并入 EGO。

## 7.1 为什么这样分层

EGO 的核心 occupancy map 当前可由 LiDAR cloud 驱动。

D435i Depth 是增强输入，不是 PBL-1 的必要条件。

因此：

- D435i 不应成为“飞机能不能起飞”的硬依赖；
- 视觉开发应尽量与 flight-critical chain 解耦；
- Depth→EGO 必须作为单独 integration milestone 验证。

## 7.2 强制传感器阶梯

### L0 — lidar_only

```text
Mid360 + IMU
→ Faster-LIO
→ EGO cloud map
→ flight
```

验收：PBL-1 完整通过。

### L1 — RGB enabled

```text
L0 + front RGB
```

要求：

- RGB topic 正常；
- 不拖垮 odom；
- 不影响 readiness；
- 双机仍可完成 PBL-1。

### L2 — RGB + Depth transport

```text
L1 + depth stream
```

但：

```text
Depth NOT required by planner
```

要求：

- unique publisher；
- mono16 / expected resolution；
- timestamps monotonic；
- frame rate 达到 contract；
- non-zero depth；
- 与场景几何大体一致；
- 不引起 takeoff regression。

### L3 — Depth → EGO

Depth 正式进入 planner map。

要求：

- 证明 depth callback/fusion 真正触发；
- 对比 cloud-only 与 cloud+depth；
- 不破坏 Mid360 perception-based UAV avoidance；
- 不让 depth transport 成为单点故障导致完全不能飞。

## 7.3 当前 D435i 回归的首要检查

如果 full mode 无法起飞，先做：

```text
A. lidar_only 是否仍能起飞？
B. RGB only 是否能起飞？
C. 加 down camera 是否能起飞？
D. 加 depth transport 后是否失败？
```

这比一上来调 planner 参数更有信息量。

---

# 8. Coordinate Model — 双机坐标系

这是本项目最容易被误解的地方之一。

## 8.1 两机 Faster-LIO 原点独立

当前两架 UAV 各自运行 Faster-LIO。

每台 local frame 的原点与自身起飞/初始化位置相关。

因此：

```text
uav1 local trajectory coordinates
!=
uav2 local trajectory coordinates
```

即使数值看起来相似，也不能默认可直接相减。

## 8.2 EGO-Swarm swarm trajectory caveat

EGO-Swarm 的 swarm trajectory coordination 通常假设各 UAV 共享可比较的空间坐标。

当前工程中，两机独立 FAST-LIO frame 使跨机 trajectory subtraction / clearance 判断不天然成立。

另外还存在 start-time window 等约束。

因此当前规则：

**不要把 `/broadcast_bspline` / swarm trajectory broadcast 当作当前可靠防撞保证。**

## 8.3 当前机间避碰来源

当前可靠的工程逻辑是：

```text
other UAV
    ↓ sensed by local Mid360
local point cloud / grid map
    ↓
EGO collision checking
    ↓
replan or EMERGENCY_STOP
```

`check_swarm_obstacle.py` 是重要验证工具。

## 8.4 未来真正做 swarm coordination 的正确顺序

如果后面要让 swarm trajectory coordination 真正可靠：

1. 先统一/映射 odom frames；
2. 验证两个 UAV 的 trajectory 都在同一几何 frame；
3. 再评估 broadcast timing；
4. 最后才 patch EGO-Swarm swarm logic。

**不要先 patch EGO 的时间窗口来掩盖坐标系不一致。**

---

# 9. Odometry / MAVROS Semantics

## 9.1 关键 topic 不要混淆

项目中存在多种 odometry topic：

```text
/uavX/slam/odometry_raw
/uavX/mavros/odometry/out
/uavX/mavros/odometry/in
/uavX/mavros/local_position/odom
```

它们方向和用途不同。

不要仅凭名字中的 `in/out` 猜数据方向。

## 9.2 当前 flight-critical odom

watchdog / executor navigation verification / preflight topic wait 以：

```text
/uavX/mavros/local_position/odom
```

作为主要飞行位置来源。

FAST-LIO raw odom 保留在：

```text
/uavX/slam/odometry_raw
```

## 9.3 TF contract 是硬门

`odom_tf_contract_check.py` 用于验证 MAVROS odom plugin 所需的 TF 关系，并检查日志错误。

不要看到 topic 有消息就认为 external odometry contract 已经正确。

## 9.4 已确认的不要重复“修”

以下属于已知正确约定，除非 fresh evidence 明确反驳，不要随意更改：

```text
FAST-LIO extrinsic_T=[0,0,0.1]
```

以及 `/mavros/odometry/in` 某些 ENU-side z 表现本身不等于坐标错误。

---

# 10. EGO-Swarm Integration Semantics

## 10.1 Cloud 是主输入

当前 planner map 可由：

```text
/uavX/slam/cloud_registered
```

构建。

这也是为什么此前没有真实 depth callback 时 EGO 仍可运行。

## 10.2 Depth 是增强，不是 PBL-1 前提

Depth + odom 可以用于投影/滤波增强。

但本阶段不可把 depth stream availability 变成“没有 depth 就完全不启动 planner”的硬耦合，除非用户后续明确更改架构策略。

## 10.3 `pose_type`

当前 fork 的参数语义必须以源码 `grid_map.h` 为准，而不是网上其他 EGO fork：

```text
POSE_STAMPED = 1
ODOMETRY    = 2
```

当前 integration 使用 ODOMETRY 模式。

## 10.4 外部源码修改原则

如果 bug 看起来在 EGO：

先证明：

- goal 确实到达 planner chain；
- odom 正常；
- cloud 正常；
- FSM state 合理；
- project wrapper/remap/config 无误；
- last-known-good 与 current EGO build/params 有实际差异。

只有这时才能建议修改 `external/ego-planner-swarm`。

---

# 11. Mission / Route Philosophy

当前穿隧道成功并不意味着最终 route abstraction 已经理想。

## 11.1 当前路线的角色

当前窄通道/隧道路线主要用于：

- 验证飞行链；
- 验证狭窄环境稳定性；
- 验证双机错时执行；
- 建立可重复 regression baseline。

因此现阶段**不要为了“更智能”而破坏已经好用的路线**。

## 11.2 中期目标：减少“写死航点感”

比赛细则和地图尚未完整公布时，中期研发应把能力从：

```text
密集 waypoint 序列
```

逐渐抽象为：

```text
任务级 goal
+ corridor / gate / region constraints
+ EGO local replanning
```

方向是让上层告诉 UAV：

- 穿哪个门；
- 进入哪个区域；
- 保持哪种队形/先后关系；

而不是逐厘米告诉 planner 怎么走。

## 11.3 什么时候允许优化路线抽象

满足以下条件后再做：

- D435i 回归已隔离；
- PBL-1 可重复；
- route abstraction 有独立 test；
- 能随时 fallback 到已验证路线比较。

---

# 12. Live Run Lifecycle

每次仿真重启都视为**新 simulation instance**。

不得复用上一次 readiness 去授权下一次飞行。

典型顺序：

```bat
scripts\start_predicted_course_two_uav.bat
scripts\run_live_fastlio_dual.bat
scripts\run_live_ego_swarm_dual.bat
scripts\run_stage7_topic_probe.bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

如果只做基础双机而非 course，可以按任务选择对应 `start_two_uav.bat` 等入口，但 safety gates 不变。

## 12.1 no-arm readiness

`run_live_fastlio_dual.bat` 产生 run-scoped readiness evidence。

核心门：

- identity
- schema
- freshness
- isolation
- stationary_stability

五项未全部通过，不进入规划/飞行阶段。

## 12.2 topic probe

`run_stage7_topic_probe.bat` 是只读诊断入口。

优先用它判断：

- sensor bridge
- Faster-LIO
- MAVROS
- EGO-Swarm
- flight gate

哪一层失效。

## 12.3 control chain recorder

如果出现：

- planner 输出异常；
- setpoint z 异常；
- OFFBOARD 丢失；
- planner 和 PX4 状态互相矛盾；

运行：

```bat
scripts\run_stage8_control_chain_recorder.bat
```

它应保持只读：订阅、记录、不发布、不 arm。

---

# 13. Regression Debugging Protocol

## 13.1 “最近能跑，现在坏了”时的固定流程

### Step 1 — Freeze the symptom

先写清楚实际症状：

错误示例：

> D435i 把 EGO 弄坏了。

正确示例：

> full sensor mode 下，两机 readiness/odom 在起飞窗口出现 freshness failure，flight runner 未完成正常 takeoff。

描述**观测**，不要把猜测写成结论。

### Step 2 — Identify last-known-good

找：

- last known good commit/config；
- last known good sensor mode；
- 对应 run / artifacts；
- current commit/config。

### Step 3 — Diff

优先比较：

```text
sensor JSON
launch XML
stage7 config
sensor bridge args
relay/remap
topic names
process count
resource mode
watchdog threshold changes
```

不要先 diff EGO 数千行源码。

### Step 4 — Binary isolate

把新 feature 拆开：

```text
lidar only
→ +RGB
→ +bottom camera
→ +depth transport
→ +depth planner fusion
```

找到最小失败增量。

### Step 5 — Collect evidence

根据层级使用：

- readiness json
- topic probe
- control chain recorder
- MAVROS state
- odom timestamps
- sensor receive rate
- process / CPU / rendering behavior
- watchdog JSONL
- runner/executor logs

### Step 6 — Minimal patch

修最小责任层。

### Step 7 — Regression ladder

focused offline → Stage 7/8 → no-arm → flight ladder。

---

# 14. Fault Decision Trees

## 14.1 飞机无法起飞

按顺序问：

```text
[1] Simulator/PX4/MAVROS 都活着吗？
          ↓ yes
[2] readiness 五门 PASS 吗？
          ↓ yes
[3] /mavros/local_position/odom fresh 吗？
          ↓ yes
[4] watchdog 是否先发 land/no_autoland？原因？
          ↓ no
[5] OFFBOARD 是否进入？
          ↓ yes
[6] arm 是否成功？
          ↓ yes
[7] takeoff setpoint 是否发布且持续？
          ↓ yes
[8] PX4 是否跟随 setpoint？
```

如果在 [2]-[4] 已失败，**planner 很可能尚不是主因**。

当前 D435i regression 优先集中在 [2]-[4]。

## 14.2 能起飞，但不导航

再进入：

```text
mission goal
→ waypoint/FSM trigger
→ EGO goal acceptance
→ planner odom/cloud input
→ /planning/pos_cmd
→ setpoint bridge
→ /mavros/setpoint_raw/local
→ PX4 response
```

用 control-chain recorder 定位第一处断点。

## 14.3 `planner_commands=0`

不要把这个数字单独当故障。

先判断：

- UAV 是否已经在 goal tolerance 内？
- command counter 的统计窗口是什么？
- planner 是否实际需要输出新的命令？
- goal 是否未达到而 planner 又真的没有输出？

只有最后一种才是明确 planner-chain failure。

已取证的一种明确 failure（2026-08-07 live run `stage7-20260807T084232Z-2599`）：

- 症状：双机 takeoff 成功，导航阶段 `planner_commands=0`，EGO 日志却显示 `Triggered!` 与 GEN/REPLAN/EXEC 状态循环；
- 根因：`ego_swarm_dual.log` 出现
  `Client [...ego_swarm_setpoint_bridge...] wants topic /uav1/planning/pos_cmd to have datatype/md5sum [44d620d9...], but our version has [4712f060...]. Dropping connection.`
  —— 28com_uav devel 与 ego-planner-swarm devel 的 `quadrotor_msgs/PositionCommand` 定义不同（28com 带 `goal_pos`）；
- 修复：`stage7_live_slam_ego_swarm_flight.sh` 与 `run_stage8_control_chain_recorder.bat` 在 28com_uav 之后、project overlay 之前 source
  `$EGO_SWARM_WSL_DIR/devel/setup.bash`，使 Python 侧 md5 与 EGO 发布端一致；
- 回归保护：`tests/stage7_quadrotor_msgs_overlay_check.py` + `validate_stage7.ps1` / `validate_stage8.ps1` 静态检查 source 顺序。

## 14.4 stale odom

先判断：

- 是 sensor/renderer 负载造成输入间断？
- Faster-LIO process 是否卡住？
- relay 是否卡住？
- MAVROS odom 是否断而 raw odom 正常？
- timestamp 是否异常而 receive wall time 正常？

不要直接增大 watchdog timeout 把问题藏起来。

允许合理 threshold 修正，但必须有数据支持。

## 14.5 异常高度 / 坐标

先记录：

- raw odom z
- MAVROS local z
- planner z
- setpoint_raw z
- frame/type mask
- PX4 mode

不要凭“ENU/NED 应该是正/负”直接改符号。

---

# 15. Testing Ladder

测试必须按风险逐级升级。

## T0 — Static/offline

- JSON parse
- Python import
- unit/contract tests
- launch XML parse
- deterministic course generation

## T1 — Stage validations

与任务相关至少跑：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

如果只改纯文档，不机械跑 live。

## T2 — no-arm

验证：

- sensor identity
- isolation
- odom freshness
- TF
- planner inputs
- D435i transport（按 sensor mode）

## T3 — single UAV

任何可能影响控制/飞行的风险改动，优先单机验证。

## T4 — dual takeoff

两机只验证：

- OFFBOARD
- arm
- takeoff
- stable hover
- safety watchdog

## T5 — short navigation

短距离 planner/control loop。

## T6 — full PBL route

完整双机错时隧道路线。

## T7 — fresh-instance repeatability

重要 milestone 至少做跨新实例重复。

建议：

- 开发阶段：1 次成功可继续下一级；
- 宣布 baseline 稳定：至少 3 次 fresh-instance；
- 关键赛前里程碑：优先 5 次并统计 clean-run rate。

---

# 16. Live Evidence Discipline

每次重要 live run 应能回答：

```text
run_id
simulation_instance_id
git_commit
sensor_mode
course/base_map
readiness status
UAV1 final state
UAV2 final state
armed/offboard transitions
odom freshness failures
planner timeout/failure
emergency stop count
collision count
minimum separation
mission completion
```

## 16.1 Run-scoped artifacts

优先依赖当前 `$STAGE7_RUN_DIR` 下的：

```text
sensor_readiness.json
topic_probe_report.json
flight_report.json
mission_events.jsonl
executor_trace.json
score_summary.json
stage8_control_chain.jsonl
stage8_control_chain_summary.json
watchdog / runner / executor logs
provenance.json
```

文件名具体以当前脚本输出为准。

## 16.2 禁止“肉眼通过”替代证据

可以说：

> 画面上飞行很平滑，且 flight_report 记录 ready=true、无 OFFBOARD loss。

不要只说：

> 看起来挺好，所以通过。

视觉观察是证据的一部分，不是唯一 evidence。

---

# 17. Safety / Watchdog Policy

## 17.1 safety 不应被新功能随意牺牲

遇到 watchdog abort：

先找 root cause。

禁止默认做法：

- 关 watchdog；
- 无限增加 threshold；
- 把 geofence 扩大到失去意义；
- 忽略 unreasonable position 后强制 LAND。

## 17.2 unreasonable position

位置明显不可相信时：

```text
no_autoland / unreasonable_position
```

比对垃圾位置执行自动返航/降落更安全。

该语义不要随意改变。

## 17.3 simulation arming

仅允许：

```text
--simulation-only
--allow-arm
simulation_arm_policy.allow_arm=true
current readiness PASS
```

## 17.4 real hardware

真机仍然：

- manual arm；
- manual Offboard authorization；
- Agent 不自主执行危险动作。

---

# 18. Modification Boundaries

## 18.1 Green Zone

Agent 可自主：

- Python bugfix
- project C++ adapter bugfix
- launch/remap
- JSON config
- sensor bridge
- diagnostics
- tests
- mission orchestration
- docs
- local commit

前提：遵守 regression ladder。

## 18.2 Yellow Zone

调查可以自主，但修改前先向用户说明：

- 证据；
- 为什么 project-side patch 不够；
- 预计影响范围；
- fallback/rollback；
- 如何验证 PBL。

范围：

```text
external/ego-planner-swarm
Faster-LIO core
PX4 core / EKF policy
shared-frame architecture
large watchdog/geofence redesign
large-scale mission architecture rewrite
```

## 18.3 Red Zone

未经明确授权：

- real aircraft arm
- force push
- history rewrite
- destructive reset
- overwrite external simulator assets broadly
- modify original 28com project as workaround

---

# 19. Git Workflow

标准流程：

```text
git status
→ inspect relevant diff/history
→ edit
→ focused tests
→ broader validation
→ git diff
→ local commit
```

Agent 允许本地 commit。

**禁止未经用户许可 push。**

## 19.1 工作区保护

如果看到未知修改：

- 不要自动丢弃；
- 先判断是否与当前任务相关；
- 不用 `reset --hard`；
- 不用 checkout 覆盖整个目录；
- 自己的 commit 只包含自己任务的修改。

## 19.2 不自动改 main 历史

即便当前开发都在 main，也不意味着 Agent 有权限重写 main 或自动 push。

旧 handbook 中“改完直接 push”的惯例已废止。

---

# 20. Current Development Roadmap

D435i 回归修复后，两条线并行。

## 20.1 Motion Track

### M0 — Restore protected baseline after sensor regression

目标：

- lidar_only 始终可运行；
- D435i 的存在不破坏基础飞行。

### M1 — Repeatability

- fresh-instance 3–5 次；
- clean-run rate；
- min separation；
- OFFBOARD loss；
- timeout；
- odom dropout。

### M2 — Smooth narrow-space motion

保持当前成功路线作为 reference，不直接删掉。

实验：

- 更稀疏 task goals；
- corridor/gate constraints；
- planner local autonomy；
- velocity/acceleration continuity；
- wall clearance。

### M3 — Better dual-UAV coordination

研究：

- stagger timing；
- role/priority；
- corridor occupancy coordination；
- shared/world frame strategy；
- eventually valid swarm trajectory coordination。

不要把 “EGO-Swarm” 名字本身等同于当前已经完成真正统一坐标的多机 trajectory optimization。

## 20.2 Vision Track

### V0 — RGB stable transport

保证不影响 flight。

### V1 — Detection

目标检测/识别算法独立开发。

### V2 — RGB-D ranging

使用 depth 做目标距离/空间定位。

### V3 — Task perception

二维码、标志物、任务目标等根据比赛细则落地。

### V4 — Depth planning fusion

最后再把 depth 纳入 EGO local map。

## 20.3 Mission Integration

比赛地图/任务细则明确后：

```text
Motion
+ Vision
+ task rules
+ Behavior Tree / mission executor
= competition mission system
```

不要在规则未公布时过度写死高层任务树。

---

# 21. What NOT to Optimize Yet

除非当前任务明确需要，暂时不要：

- 换掉 EGO-Swarm；
- 重写 PX4 控制器；
- 为未来地图做复杂全局规划系统；
- 一次性统一所有坐标系；
- 把 D435i Depth 变成 flight startup 硬依赖；
- 把视觉、planner、behavior tree 强耦合；
- 因为“更高级”就删掉已验证 waypoint baseline；
- 重做 RflySim 地图工具链；
- 再提出安装 UE Editor。

当前原则：

> 已有能力先稳定，新能力做可逆增量。

---

# 22. Historical Incidents — 只作为经验，不作为当前 blocker

以下历史事件有诊断价值，但其状态不得自动继承到现在。

## 22.1 2026-07-29 / 07-30 MAVROS bring-up

经验：

- WSL 启动脚本要保持 session alive；
- dual MAVROS 要使用 dedicated links；
- `connected: True` 只说明链路，不说明 mission 可飞；
- Windows nested quoting / `timeout /t` 等曾导致启动问题。

这些是启动编排知识，不是当前 D435i root cause 的默认结论。

## 22.2 2026-08-01 Stage 7 成功

历史 run 证明：

- dual OFFBOARD/arming/takeoff；
- short EGO segment；
- landing/disarm；
- perception-based inter-UAV obstacle behavior。

它是工程可行性的早期证据。

## 22.3 2026-08-02 Stage 8 failure

曾出现：

- UAV2 异常高度；
- ALTCTL；
- `planner_commands=0`；
- 路线未完成。

保留相关 docs 用于以后如果**相同症状重新出现**时快速复用 diagnostics。

但当前用户已经确认后续双机穿隧道状态非常好，所以该事故不再是 Current Blocker。

## 22.4 2026-08-07 D435i integration lessons

已知有价值的事实：

- RflySim sensor JSON 不只是普通 JSON schema；`VisionCaptureApi` 有额外协议约束；
- full 多传感器负载曾伴随明显 odom gap；
- lidar_only 能显著降低传感器/renderer 压力；
- depth transport 与 planner fusion 必须分开验证；
- 28com 仿真本身主要依靠 LiDAR cloud 运行 EGO，Depth 不是 cloud planning 的先决条件。

当前回归应优先利用这些经验。

## 22.5 2026-08-07 `planner_commands=0` PositionCommand md5 不匹配（已修复，live 已验证）

- 症状：`lidar_only` 下双机 takeoff 成功，导航阶段 UAV1 `planner_commands=0`（run `stage7-20260807T084232Z-2599`）；
- 证据：`ego_swarm_dual.log` 大量 `md5sum [44d620d9...] but our version has [4712f060...] Dropping connection`；
  实测两个 workspace：28com_uav devel 的 `PositionCommand` md5=`44d620d9…`（含 `goal_pos`），
  ego-planner-swarm devel 的 md5=`4712f060…`（无 `goal_pos`），EGO 节点发布端与 28com devel 不一致；
- 根因：`stage7_live_slam_ego_swarm_flight.sh` 只 source 28com_uav devel + project overlay，未 source ego-planner-swarm devel，
  Python 侧拿到 28com 的消息定义，与 EGO 发布端 md5 不匹配导致连接被 ROS 丢弃；setpoint bridge 与 executor 均收不到 pos_cmd；
- 修复：flight runner 与 stage8 recorder 在 28com_uav 之后、project overlay 之前 source ego-planner-swarm devel；
- 验证：WSL 实测修复后 Python 侧 md5=`4712f060…`（与 EGO 一致），`multi_uav_mission` 仍可解析；
  `validate_stage7.ps1` / `validate_stage8.ps1` 通过；新增 `tests/stage7_quadrotor_msgs_overlay_check.py` 静态回归保护；
- 2026-08-07 晚间复验记录：修复曾短暂 revert（`5067c8a`）后按用户决定重新落地；重新验证 `tests/stage7_quadrotor_msgs_overlay_check.py` PASS、WSL 实测 28com-only=`44d620d9…` / 28com+ego+project=`4712f060…`（`rosmsg md5` 与 genpy 均一致），`validate_stage7.ps1` / `validate_stage8.ps1` PASS。
- live 复测（2026-08-07 晚间，run `stage7-20260807T124153Z-22785`）：readiness 五项 PASS → 双机 OFFBOARD/arming/takeoff 成功 → UAV1 导航确认 `planner_commands=190/383/116`、`navigation_confirmed=true`，`ego_swarm_dual.log` 中 md5/Dropping connection 计数为 0。**该故障已由 live 证据关闭。**
- 遗留观察：同一 run 导航中段 `/uav1/mavros/local_position/odom` 出现瞬态断流导致 executor 判失败（详见 2.1 当前状态），需另行取证。
- 操作经验（2026-08-07 晚间，供后续 Agent 参考）：从 agent 会话经 `nohup` 多次启动 fastlio/ego 脚本时，曾出现重复 roslaunch 实例竞争（`new node registered with same name`）导致 planner 节点重启、`/planning/goal` 短暂无订阅者；再次出现此症状时先清理所有 `rflysim_ego_swarm_dual.launch`/`rflysim_fastlio_dual.launch` 相关进程再重试，避免同一时刻多个 planner 实例。

---

# 23. D435i Regression Playbook（视觉线待办，非当前 P0）

当任务是“修好今天 D435i 导致无法起飞”时，推荐 Agent 严格按以下顺序。

## Phase A — Prove PBL still exists

1. fresh simulator instance；
2. `lidar_only`；
3. readiness；
4. dual takeoff；
5. 短 navigation；
6. 必要时完整 PBL route。

如果 L0 已失败：

- 比较 D435i commit 是否无意修改了 lidar path；
- 不要假设问题只是 full mode。

## Phase B — Isolate sensor increment

依次：

```text
L0 lidar only
L1 lidar + RGB
L1b lidar + RGB + down camera
L2 lidar + RGB + down + depth transport
```

每一级至少检查：

- process alive；
- odom rate/freshness；
- renderer/system load signal；
- readiness；
- takeoff；
- sensor topic frequency。

## Phase C — Fix smallest responsible layer

可能修复点：

- bridge 只 load 必需 SeqID；
- 调整 sensor mode/启动顺序；
- 避免重复 publisher；
- 避免不必要 relay/copy；
- 降低测试阶段 sensor 开销；
- 修 timestamp / topic contract；
- 将视觉进程从 flight-critical readiness 解耦。

不要先做：

- EGO source patch；
- PX4 source patch；
- FAST-LIO extrinsic 变化；
- route rewrite。

## Phase D — Restore gradual capability

修复完成后必须证明：

```text
L0 pass
L1 pass
L2 pass
```

然后再计划 L3 Depth→EGO。

---

# 24. Motion Development Playbook

D435i 修复后，若任务回到“让双机飞得更丝滑、不是笨拙密集 waypoint”：

## 24.1 不直接删 baseline route

保留当前 route 作为 regression oracle。

建立新的 experiment mode，与 baseline A/B 比较。

## 24.2 上层只表达必要约束

优先探索：

- tunnel entrance gate；
- tunnel exit gate；
- corridor center region；
- altitude band；
- UAV priority / time separation；
- terminal task region。

让 EGO 负责：

- obstacle-aware local trajectory；
- continuous replanning；
- velocity/acceleration smoothness；
-局部偏移。

## 24.3 衡量“丝滑”

不要只凭视觉。

建议记录：

- path length；
- traversal time；
- velocity peaks；
- acceleration peaks；
- jerk proxy；
- minimum wall clearance；
- number of replans；
- emergency stop count；
- number of high-level goals。

如果减少 waypoint 后安全性明显下降，不要因为“看起来更智能”就接受。

---

# 25. Vision Development Playbook

## 25.1 Vision first, planner later

当前优先顺序：

```text
RGB transport
→ detector
→ target output contract
→ depth ranging
→ task logic
→ optional planner fusion
```

## 25.2 视觉接口保持解耦

优先通过 target provider/interface 将 detector 输出给任务层。

不要让 mission executor 直接依赖某个具体 YOLO 节点内部实现。

## 25.3 Depth 两种用途要分开

```text
Depth for target ranging
```

和

```text
Depth for EGO occupancy fusion
```

是两项不同功能，必须独立验证。

前者成功不能证明后者成功，反之亦然。

---

# 26. Environment / Toolchain Notes

当前开发环境约定来自 RflySim 安装：

Windows 侧常见：

```text
D:\PX4PSP\RflySimAPIs
D:\PX4PSP\RflySim3D
D:\PX4PSP\CopterSim
D:\PX4PSP\Firmware
D:\PX4PSP\Python38\python.exe
D:\PX4PSP\WinWSL
D:\PX4PSP\VcXsrv
```

WSL 常见变量：

```text
RFLYSIM_WSL_DISTRO=RflySim-20.04
PSP_PATH_LINUX=/mnt/d/PX4PSP
```

项目路径和 28com reference path 以当前 `config/env_template.bat` / 本机实际环境为准，不要把 handbook 中路径字符串当跨机器绝对真理。

## 26.1 Windows/WSL 脚本历史坑

已知经验：

- `.sh` 保持 LF；
- 启动 WSL 用 `bash -lic` 以正确 source 环境；
- 启动 session 需要 `wait` 时不要漏；
- `cmd /k` nested quoting 要谨慎；
- 非交互 wrapper 中避免不可靠 `timeout /t`，已有脚本偏向 PowerShell sleep。

---

# 27. Course / Map Policy

当前 course 权威几何：

```text
config/maps/predicted_narrow_course_v1.json
```

动态 course 用于 RflySim 视觉/LiDAR 场景。

注意：

- dynamic walls 不等同 CopterSim terrain；
- 验收障碍物优先看 LiDAR visibility / geometric clearance；
- 不要擅自覆盖 CopterSim 外部地图资产；
- UE Editor 路线已经明确搁置，不要再次建议安装 UE Editor。

---

# 28. Documentation Maintenance

## 28.1 Current vs Historical

文档必须明确分区：

### Current

只保留当前仍然影响开发的事实。

### Historical / Resolved

记录：

- symptom；
- root cause；
- fix；
- reusable lesson；
- superseded date/evidence。

## 28.2 修复后必须“移动问题”

如果 D435i takeoff regression 修好：

错误做法：

> 在 Current State 继续写“飞机无法起飞”，然后下面再加一句“已经修好”。

正确做法：

- Current State 更新为最新能力；
- 把无法起飞事件移动到 Historical Incident；
- 记录原因和验证方式。

## 28.3 README 不应成为事故日志

README 只保留：

- 项目定位；
- 技术栈；
- 当前稳定状态；
- 入口；
- 关键约束。

详细事故放 docs / handbook historical section。

---

# 29. Agent Task Workflow

每次任务建议按以下 template 执行。

## Phase 1 — Understand

```text
Task goal:
Current symptom:
Protected baseline affected?: yes/no
Relevant layer:
Last-known-good:
Current evidence:
```

## Phase 2 — Hypotheses

列 2–4 个按证据排序的假设。

不要列十几个无优先级猜测。

## Phase 3 — Smallest experiment

每个实验最好只区分一个假设。

## Phase 4 — Patch

只改责任层。

## Phase 5 — Validation

按照 Testing Ladder。

## Phase 6 — Documentation

如果状态、接口、运行方式变了，同步 handbook/README/docs 中相关位置。

## Phase 7 — Handoff

固定输出：

### Changed

具体文件和行为。

### Evidence

问题为何定位在这里。

### Validation

具体测试/run。

### Remaining Risk

未验证内容。

### Next Recommended Step

下一最小动作。

---

# 30. Agent Communication Rules

## 30.1 不夸大

如果只离线验证：

写：

> offline contracts pass; live not yet verified.

不要写：

> feature completed.

## 30.2 不隐瞒回归

如果新功能工作但 PBL 失败：

不能宣布任务完成。

## 30.3 明确“证据”和“推测”

推荐用词：

```text
Observed:
Evidence suggests:
Hypothesis:
Not yet verified:
```

## 30.4 重大改动先沟通

涉及 Yellow Zone 时，先提交简短设计：

```text
Problem
Evidence
Why project-side fix is insufficient
Proposed core change
Risks
Rollback
Validation plan
```

等待用户同意后再动核心算法。

---

# 31. Fast Checklists

## 31.1 Before editing

- [ ] 读过 `AGENTS.md`
- [ ] 读过本 handbook Current Truth
- [ ] 确认当前任务不是旧 incident
- [ ] 确认是否影响 PBL-1
- [ ] 找到最小责任层
- [ ] 检查工作区已有修改

## 31.2 Before live no-arm

- [ ] fresh simulation instance
- [ ] run-id 新建
- [ ] sensor mode 明确
- [ ] MAVROS links correct
- [ ] 两机 namespace isolated
- [ ] readiness artifact path current

## 31.3 Before simulation arm

- [ ] readiness PASS
- [ ] `--simulation-only`
- [ ] `--allow-arm`
- [ ] policy allow_arm=true
- [ ] current run/instance matched
- [ ] watchdog running
- [ ] geofence sane
- [ ] no real hardware path involved

## 31.4 Before declaring D435i fixed

- [ ] L0 lidar-only pass
- [ ] L1 RGB pass
- [ ] L2 depth transport pass
- [ ] no takeoff regression
- [ ] no unacceptable odom gaps
- [ ] fresh-instance repeat
- [ ] Depth→EGO 未验证时明确写“not yet integrated/validated”

## 31.5 Before local commit

- [ ] focused tests pass
- [ ] relevant Stage 7/8 validation pass
- [ ] diff only contains intended changes
- [ ] docs state not stale
- [ ] no secrets / generated logs accidentally staged
- [ ] no push without user permission

---

# 32. Key Commands Reference

## Offline

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

## Course startup

```bat
scripts\start_predicted_course_two_uav.bat
```

## Live localization

```bat
scripts\run_live_fastlio_dual.bat
```

## Planner

```bat
scripts\run_live_ego_swarm_dual.bat
```

## Read-only probe

```bat
scripts\run_stage7_topic_probe.bat
```

## Simulation flight

```bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

## Control-chain recorder

```bat
scripts\run_stage8_control_chain_recorder.bat
```

## MAVLink gate when relevant

```bat
scripts\run_stage2_1_mavlink_check.bat
```

---

# 33. Key Topic Reference

Planner goals:

```text
/uav1/planning/goal
/uav2/planning/goal
```

Planner commands:

```text
/uav1/planning/pos_cmd
/uav2/planning/pos_cmd
```

PX4/MAVROS setpoint inspection:

```text
/uav1/mavros/setpoint_raw/local
/uav2/mavros/setpoint_raw/local
```

Flight state:

```text
/uav1/mavros/state
/uav2/mavros/state
```

Primary flight odom:

```text
/uav1/mavros/local_position/odom
/uav2/mavros/local_position/odom
```

FAST-LIO raw odom:

```text
/uav1/slam/odometry_raw
/uav2/slam/odometry_raw
```

FAST-LIO cloud:

```text
/uav1/slam/cloud_registered
/uav2/slam/cloud_registered
```

D435i topics 具体 SeqID 以 sensor config 为准；当前项目配置中曾使用 UAV1 depth SeqID 3、UAV2 depth SeqID 13。不要把 SeqID 写死到新代码里而忽略 config source of truth。

---

# 34. Source-of-Truth Files by Domain

## Course geometry

```text
config/maps/predicted_narrow_course_v1.json
```

## Sensor definitions

```text
config/rflysim_sensor_uav1.json
config/rflysim_sensor_uav2.json
```

## Live Stage 7 config

```text
config/stage7_live_slam_ego_swarm.json
```

## EGO integration

```text
future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch
future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_single.launch
```

## Faster-LIO / sensor relay

```text
future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch
future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py
future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py
```

## Mission flight

```text
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py
future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_setpoint_bridge.py
```

## Safety

```text
future_aircraft_ws/src/multi_uav_mission/scripts/course_geofence_watchdog.py
future_aircraft_ws/src/multi_uav_mission/scripts/odom_tf_contract_check.py
```

## Diagnostics

```text
future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py
future_aircraft_ws/src/multi_uav_mission/scripts/stage8_control_chain_recorder.py
```

---

# 35. Final Engineering Principles

如果只记住十条，就记住这些：

1. **最新 live truth 高于旧故障文档。**
2. **双机穿隧道是当前受保护基线，不是尚未解决的问题。**
3. **D435i 当前是集成回归，先隔离新增层。**
4. **Depth 当前不是 EGO 能运行的必要条件。**
5. **新功能必须分层接入：L0 → L1 → L2 → L3。**
6. **先证据、后修改；先最小 patch、后重构。**
7. **两机 FAST-LIO frame 独立，swarm trajectory broadcast 不等于可靠机间避碰。**
8. **安全门不能为了“跑通”随便放宽。**
9. **Agent 可以仿真 flight 和本地 commit，但不能自行真机 arm 或 git push。**
10. **文档必须及时把已解决问题从 Current 移到 Historical。**

本项目当前最需要的不是更多“聪明代码”，而是让每次能力增加都建立在可重复、可回滚、可证据化的稳定基线上。
