# 未来飞行器室内狭窄通道环境下多飞行器智能协同导航与作业挑战赛仿真

## 1. 任务背景

本任务面向《第十二届中国研究生未来飞行器创新大赛》挑战赛道赛题：室内狭窄通道环境下多飞行器智能协同导航与作业挑战赛。

当前计划以 `28com_sim` 中的真实飞机硬件代码框架为基础开展仿真开发。该框架原用于第二十八届中国机器人及人工智能大赛空地协同赛道，已有 FS-310 无人机实机工程，包含 PX4/MAVROS 控制、Mid360 雷达定位、D435i 视觉、下视相机、YOLOE 检测、行为树任务决策等模块。

本项目不从零重写飞行系统，而是在保留 `28com_uav` 主体架构的基础上，将原有单机 `ego-planner` 局部规划模块替换为 `ego-swarm`，扩展为多机协同仿真任务框架。

## 2. 总体目标

建立一套可在 RflySim 平台中运行的多无人机仿真系统，用于验证挑战赛道赛题一的核心能力：

- 采用 2 架fs-310无人机自主起飞。
- 多机进入室内狭窄通道并避免机间碰撞、障碍物碰撞。
- 多机协同完成目标识别与作业。
- 多机穿越通道后在指定降落区有序降落。
- 使用日志记录任务状态、轨迹、识别结果、规划输出和飞控状态。

### 2.1 首期最小闭环 MVP

首期不同时推进所有模块，先建立一个可重复运行、可观测、可判定成败的最小系统闭环：

```text
RflySim + PX4 SITL + MAVROS namespace
    -> /uav1、/uav2 独立 OFFBOARD
    -> 固定航点错峰起飞、悬停、降落
    -> mission.log + uav1.bag + uav2.bag + score_summary.json
```

MVP 不要求接入 `ego-swarm`、视觉识别和完整行为树，但必须证明以下能力：

- 两架无人机可以被同一套上层任务程序独立控制。
- `/uav1`、`/uav2` 话题、参数、MAVROS 连接和 PX4 sysid 不冲突。
- setpoint 发布频率稳定，不触发 OFFBOARD 丢失。
- 日志系统能记录每架无人机的 state、odom、setpoint 和任务阶段事件。
- 每次运行均可通过结构化评分文件判断成功或失败。

### 2.2 总体成功判据

除阶段性验收外，最终系统应满足以下可量化标准：

- 双机完整任务连续运行 10 次，成功次数不少于 8 次。
- 任意时刻双机最小间距不小于 0.6 m。
- 任意无人机与静态障碍物的最小距离不小于 0.3 m，除非赛题规则另有定义。
- 起飞至稳定悬停位置误差不大于 0.3 m。
- 降落点水平误差不大于 0.5 m。
- 每次运行必须生成 `mission.log`、`uav1.bag`、`uav2.bag`、`target_results.json`、`score_summary.json`。
- 发生碰撞、越界、OFFBOARD 丢失、识别失败、超时等情况时，日志中必须有明确事件记录。
## 3. 基准工程

参考工程：

```text
D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\28com_sim\UAV_demo\28com_uav
```

重点复用模块：

- `mission_pkg`：行为树任务调度、动作节点、感知节点。
- `mavros_cnt`：MAVROS 状态订阅、Offboard 指令发布、解锁与模式切换接口。
- `faster-lio-main`：激光 SLAM 定位框架。
- `object_det`：视觉目标检测框架。
- `livox_ros_driver2`：Mid360 雷达驱动。
- `sensor_pkg`：仿真或实机传感器聚合入口。

需要替换或重构模块：

- 使用 `ego-swarm` 替换原 `ego-planner`。
- 将单机 MAVROS/任务节点扩展为多机 namespace 架构。
- 将原 28com 行为树任务改写为 futureAircraftSim 任务行为树。

## 4. 仿真环境与地图策略

### 4.1 初期地图

初期使用 RflySim 已有 `ChallengeMap` 做算法验证。

该地图可用于验证：

- 室内环境飞行。
- 起降点。
- 立柱、门洞、方框等静态障碍。
- 动态小车或动态目标。
- ArUco/二维码类视觉目标。

但它不是赛题一官方地图，不能视为严格复现。

### 4.2 近似比赛地图

在官方地图细则未发布前，自建近似场景，按 PDF 已公开约束设计：

- 通道长度不小于 3 m。
- 通道宽度不大于 1.5 m。
- 转弯半径不大于 1 m。
- 起飞区至少包含 2 个起飞点。
- 通道内包含静态障碍物与动态障碍物。
- 通道内包含 3 类作业目标：颜色标签、二维码、温度模拟源。
- 降落区包含不少于无人机数量的 ArUco 降落平台。

## 5. 目标系统架构

```text
RflySim3D / CopterSim / PX4 SITL
        |
        v
MAVROS namespace:
  /uav1/mavros/...
  /uav2/mavros/...
        |
        v
multi_uav_mission
        |
        +-- mission_pkg behavior tree
        +-- ego-swarm planner adapter
        +-- perception adapter
        +-- task allocation / collision avoidance policy
        +-- logging and scoring recorder
```

实机迁移时，保留同一套上层 ROS 话题与任务接口，将仿真传感器源替换为真实硬件：

- RflySim 图像/点云 -> D435i / Mid360 / 下视相机
- PX4 SITL -> 真实 PX4 飞控
- 仿真 MAVROS -> 实机 MAVROS

### 5.1 多机 namespace 与接口契约

所有新开发节点必须默认支持 `uav_id` 或 `namespace` 参数，禁止在任务逻辑中硬编码 `/mavros`。

| 接口 | 类型 | 坐标系 | 频率/触发 | 生产者 | 消费者 |
| --- | --- | --- | --- | --- | --- |
| `/uavX/mavros/state` | `mavros_msgs/State` | 无 | MAVROS 默认 | MAVROS | mission_pkg、logger |
| `/uavX/mavros/local_position/odom` | `nav_msgs/Odometry` | ROS ENU，`map` 或 `odom` | >= 30 Hz | MAVROS / 定位源 | ego_swarm_adapter、mission_pkg、logger |
| `/uavX/mavros/setpoint_raw/local` | `mavros_msgs/PositionTarget` | ROS ENU，经 MAVROS 转 PX4 | >= 20 Hz | mavros_cnt / trajectory_tracker | PX4 |
| `/uavX/planner/goal` | 自定义或标准 goal 消息 | `map` ENU | 任务阶段触发 | mission_pkg | ego_swarm_adapter |
| `/uavX/planner/trajectory` | 轨迹消息 | `map` ENU | planner 输出 | ego_swarm_adapter | trajectory_tracker、logger |
| `/mission/events` | 结构化事件 | 无 | 阶段切换或异常 | mission_pkg | logger、score_recorder |
| `/targets/results` | JSON 或 ROS msg | `map` ENU | 识别完成触发 | perception adapter | mission_pkg、score_recorder |

接口设计原则：

- `mission_pkg` 只关心任务阶段、目标分配和结果，不直接依赖某个规划器内部实现。
- `ego_swarm_adapter` 负责屏蔽 `ego-swarm` 的话题、消息、坐标和参数差异。
- `perception adapter` 负责在理想目标位置和真实视觉识别之间切换，任务树不直接读取仿真内部对象。
- `logger` 和 `score_recorder` 从第一阶段就接入，不等完整系统完成后再补。

### 5.2 坐标系与时间同步约束

坐标系问题必须作为早期风险处理，不能等到多模块集成后再排查。

- ROS 上层统一使用 ENU 坐标，推荐全局 frame 为 `map`，机体系为 `uavX/base_link`。
- PX4 内部 NED 与 ROS ENU 的转换只允许集中在 MAVROS 或明确的 adapter 中完成。
- RflySim 世界坐标、PX4 local position、SLAM odom、视觉目标坐标之间必须记录固定转换关系。
- D435i、下视相机、Mid360 的外参应以 `tf` 或配置文件形式保存，不写死在算法代码中。
- 所有关键日志必须记录 ROS time、任务阶段时间戳和无人机编号。
## 6. 主要开发任务

### 6.1 工程整理

- 在 `future_aircraft_ws` 中建立可编译 ROS1 工作区。
- 不复制 `28com_uav` 原工程主体，优先在 `future_aircraft_ws` 下开发仿真专用 ROS 包、launch、配置与 adapter。
- 保留原始 28com 工程不直接破坏，避免影响已有实机代码。
- 在 `future_aircraft_sim` 目录下建立 `.bat` 启动脚本、运行说明和日志目录规范。
- 所有新增包必须能独立说明输入、输出、依赖和启动方式。

### 6.2 多机 MAVROS 接口重构

当前 `mavros_cnt` 是单机单例模式，需要改造为多实例或 namespace 参数化。

目标：

- 支持 `/uav1/mavros/state`、`/uav2/mavros/state`。
- 支持 `/uav1/mavros/local_position/odom`、`/uav2/mavros/local_position/odom`。
- 支持分别向每架无人机发布 `/uavX/mavros/setpoint_raw/local`。
- 每架无人机独立解锁、切换 OFFBOARD、降落。

### 6.3 ego-swarm 接入

使用 `ego-swarm` 替换原 `ego-planner`。

需要完成：

- 确认 ego-swarm ROS 版本、依赖和可编译状态。
- 适配 RflySim/PX4 坐标系。
- 对接每架无人机的里程计、目标点、局部地图或深度感知输入。
- 输出每架无人机的规划轨迹或位置控制指令。
- 建立 `ego_swarm_adapter`，隔离 planner 与 mission_pkg 的接口差异。

### 6.4 赛题一行为树设计

基于原 `mission_pkg/config/full_competition.xml` 重写futureAircraftSim 任务树。

建议任务阶段：

1. `MultiTakeoff`：多机 20 秒内完成自主起飞。
2. `EnterCorridor`：多机编队或错峰进入通道。
3. `CollaborativeNavigate`：ego-swarm 协同穿越狭窄通道并避障。
4. `CollaborativeTargetWork`：分配并识别颜色标签、二维码、温度模拟源。
5. `ExitCorridor`：有序通过出口。
6. `ArucoLanding`：识别降落平台并定点降落。
7. `MissionReport`：输出识别结果、目标坐标、耗时、碰撞状态和日志。

### 6.5 感知接口

初期仿真可先使用理想目标位置或 RflySim 目标对象位置，后续再接真实视觉识别。

目标识别模块：

- 颜色标签识别。
- ArUco/二维码识别。
- 温度模拟源识别。
- 目标点相对于通道坐标系的位置估计。

需要保留对真实硬件的迁移接口：

- D435i RGB/Depth。
- 下视相机。
- Mid360 点云。
- 机载计算机 ROS1 环境。

### 6.6 日志与评分

记录内容：

- 每架无人机起飞时间、降落时间。
- 每架无人机轨迹。
- MAVROS state、odom、setpoint。
- ego-swarm 规划目标、轨迹、状态。
- 目标识别结果与目标坐标。
- 任务阶段切换事件。
- 碰撞、越界、超时状态。

输出建议：

```text
logs/
  YYYYMMDD_HHMMSS/
    mission.log
    uav1.bag
    uav2.bag
    target_results.json
    score_summary.json
```

### 6.7 启动脚本与仿真编排

仿真启动脚本是核心交付物之一，不能作为临时命令散落在终端历史中。

建议在 `future_aircraft_sim` 下维护：

```text
scripts/
  start_single_uav.bat
  start_two_uav.bat
  start_mavros_uav1.bat
  start_mavros_uav2.bat
  start_mission.bat
  record_logs.bat
  kill_all.bat
```

每个脚本需要明确：

- 启动顺序。
- 依赖的环境变量和 ROS workspace。
- PX4 sysid、MAVROS 端口、namespace、起飞点参数。
- 日志输出目录。
- 失败后的清理方式。

### 6.8 关键决策门禁与 fallback

为避免关键依赖阻塞整体进度，建立以下决策门禁：

| 风险点 | 判断条件 | 首选方案 | fallback |
| --- | --- | --- | --- |
| `ego-swarm` 编译失败 | 2 个工作日内无法稳定编译 Noetic demo | 固定官方仓库可用 commit 并记录依赖 | 暂用固定航点/简单避障继续推进 MAVROS 与任务树 |
| 双机 MAVROS 冲突 | 任一无人机无法稳定独立 OFFBOARD | 先排查 sysid、端口、namespace、setpoint 频率 | 退回单机脚本，逐项恢复双机 |
| 坐标系不一致 | 轨迹方向、尺度或高度异常 | 建立 frame 检查脚本和可视化标定点 | 在 adapter 中集中修正，禁止分散补偿 |
| 视觉识别不稳定 | 识别结果导致任务无法闭环 | 视觉结果作为 target provider 接入 | 保留理想目标位置 provider 作为对照和回归测试 |
| 行为树改造过大 | 多机状态侵入原单机节点过深 | 新建 futureAircraftSim 任务节点 | 原节点只作参考，不强行兼容所有旧逻辑 |

### 6.9 主要风险清单

- `ego-swarm` 官方版本与 ROS1 Noetic、Eigen、PCL、CMake 版本存在依赖冲突。
- 多 PX4 SITL 与多 MAVROS 实例的端口、sysid、参数文件容易冲突。
- RflySim、PX4、MAVROS、SLAM、视觉之间坐标定义不统一。
- OFFBOARD setpoint 发布频率不足会导致模式丢失或控制中断。
- 原 `mission_pkg` 如果强绑定单机状态，直接改多机可能导致逻辑复杂度快速上升。
- 过早依赖真实视觉识别会掩盖任务调度和飞控链路问题。
- 后期自建地图如果缺少评分与回放机制，难以判断算法进步是否真实。
## 7. 阶段划分

### 阶段 0：启动编排与工作区骨架

目标：

- 建立 `future_aircraft_ws` ROS1 Noetic 工作区。
- 建立 `future_aircraft_sim/scripts`、`config`、`logs` 目录规范。
- 准备单机和双机启动脚本骨架。

验收：

- 可以通过脚本启动基础 ROS 环境和日志目录。
- 所有脚本参数、端口、namespace 有明确注释或配置文件。
- 不破坏原始 `28com_uav` 实机工程。

### 阶段 1：单机 MAVROS 闭环

目标：

- 在 `future_aircraft_ws` 中跑通单机 takeoff、goto、land。
- 确认原 `mission_pkg` 或仿真专用最小 mission 节点能在当前环境编译。
- 确认 RflySim `ChallengeMap` + PX4 SITL + MAVROS 可正常闭环。

验收：

- 单架无人机可进入 OFFBOARD。
- setpoint 发布频率稳定在 20 Hz 以上。
- 可完成起飞、航点飞行、降落。
- 起飞悬停误差不大于 0.3 m，降落点水平误差不大于 0.5 m。
- 日志可记录 odom、state、setpoint 和任务阶段事件。

### 阶段 2：双机 MAVROS namespace

目标：

- 同时启动 2 架无人机。
- 建立 `/uav1`、`/uav2` 命名空间控制。
- 完成双机错峰起飞、悬停、降落。

验收：

- 两架无人机可独立解锁和控制。
- 两架无人机不会因话题、端口、sysid 或参数冲突互相抢控制。
- 双机最小距离不小于 0.6 m。
- 连续运行 5 次，成功次数不少于 4 次。
- 每次运行均生成 `mission.log`、`uav1.bag`、`uav2.bag`、`score_summary.json`。

### 阶段 3：日志与评分最小版

目标：

- 建立任务事件、轨迹、状态和异常的统一记录格式。
- 建立最小 `score_summary.json` 输出。

验收：

- 可记录起飞时间、降落时间、任务耗时、最小机间距离、OFFBOARD 丢失次数、碰撞/越界状态。
- 任何失败运行都能从日志中定位失败阶段。
- 日志目录按 `YYYYMMDD_HHMMSS` 自动生成。

### 阶段 4：ego-swarm 最小接入

目标：

- 编译并运行官方 `ego-swarm`。
- 完成单独 demo 验证后，再接入本项目双机 odom 与目标点。
- 建立 `ego_swarm_adapter`，隔离 planner 与 mission_pkg 的接口差异。

验收：

- 双机可规划到不同目标点。
- 轨迹可转换成 MAVROS setpoint 或 trajectory tracker 输入。
- 基础避碰有效，最小机间距离不小于 0.6 m。
- planner 输入、输出和失败状态均可被日志记录。

### 阶段 5：futureAircraftSim 行为树

目标：

- 完成 futureAircraftSim 多阶段行为树。
- 实现目标点分配与任务阶段调度。
- 保留固定航点模式作为 planner fallback。

验收：

- 双机可按任务树完成起飞、进入通道、目标作业、出口降落。
- 每个行为树阶段都有开始、成功、失败、超时事件。
- 任一无人机失败时，系统能进入明确的中止、等待或降落策略。

### 阶段 6：感知 target provider

目标：

- 初期使用理想目标位置 provider 保证任务闭环。
- 在仿真环境中逐步接入颜色标签、二维码/ArUco、温度模拟源识别。
- 任务树只依赖统一目标接口，不直接依赖具体识别算法。

验收：

- 理想目标位置与视觉识别结果可以通过配置切换。
- 识别结果包含目标类型、目标坐标、置信度、识别无人机编号和时间戳。
- 视觉识别失败不会导致飞控链路失控，应触发重试、跳过或任务失败策略。

### 阶段 7：近似比赛场景与完整评测

目标：

- 自建近似赛题一地图。
- 加入静态/动态障碍、3 类目标、ArUco 降落平台。
- 输出完整评分摘要。

验收：

- 满足 PDF 已公开场景约束。
- 双机完整任务连续运行 10 次，成功次数不少于 8 次。
- `target_results.json` 与 `score_summary.json` 能反映目标识别、任务耗时、碰撞、越界、降落误差和失败原因。
## 8. 实机安全约束

本任务初期只面向仿真。任何迁移到真实飞机前必须满足：

- 默认禁止自动解锁真实飞机。
- 螺旋桨拆除或固定保护后再做地面联调。
- PX4 参数、MAVROS 连接、定位源切换必须单独验证。
- 安全边界必须开启。
- 必须保留人工急停链路。
- 真实飞行前先完成单机悬停，再做多机协同。

## 9. 待确认事项

开始写代码前需要确认：

1. 首期是否只做 2 架无人机，还是预留 3 架以上( 已经确认最终比赛也只需要两架无人机 )
2. ego-swarm 使用已有本地版本，还是需要新拉取外部仓库。 用户回答: 去github拉取官方最新仓库 
3. 初期是否允许使用理想目标位置，后续再接视觉识别。 用户回答: 我期望的是在仿真环境中进行视觉识别, 初期在官方赛题还未公布细则时可以先采用理想目标位置
4. 是否继续使用 ROS1 Noetic 作为统一开发环境。用户回答: 是的
5. 是否把 `28com_uav` 复制到 `future_aircraft_ws`，还是以引用方式复用原目录。 用户回答: 不要复制,直接在future_aircraft_ws下进行ros环境的代码开发,将  来在 D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\future_aircraft_sim 目录下进行.bat等启动脚本的开发
6. 仿真阶段是否允许自动解锁；实机阶段默认应禁用。 用户回答: 是的,仿真阶段自动解锁, 实机采用遥控器手动arm并切offboard模式

## 10. 本轮结论

建议采用以下路线：

```text
启动脚本与 ROS 工作区骨架
    -> 单机 MAVROS 闭环
    -> 双机 namespace + 固定航点 MVP
    -> 日志与评分最小版
    -> ego-swarm 最小 demo
    -> ego_swarm_adapter 双机接入
    -> futureAircraftSim 行为树
    -> 理想目标 target provider
    -> 仿真视觉识别 target provider
    -> RflySim ChallengeMap 初测
    -> 自建近似比赛地图
    -> 形成可迁移到真实 FS-310 硬件的多机任务系统
```

核心原则：

- 先建立可重复运行的最小闭环，再逐步替换规划、感知和任务策略。
- 接口契约先行，所有模块通过 namespace、adapter 和统一消息边界解耦。
- 日志与评分从第一阶段接入，用量化结果判断每次修改是否进步。
- 对 `ego-swarm`、视觉识别、坐标系、多 MAVROS 等高风险点设置 fallback，避免单点阻塞整体进度。
- 以后每次修改代码需要在 `agent2Read.md` 中同步方案、接口变化、验收结果和新的风险判断。


## 11. 执行记录

### 2026-07-26 阶段 0 脚本与工作区骨架

已完成：

- 建立 `future_aircraft_ws/src`、`config`、`scripts`、`logs` 目录骨架。
- 新增 `config/env_template.bat`，统一 RflySim 根路径、仿真目录、ROS workspace、ROS master 和仿真自动解锁开关。
- 新增 `config/uavs.json`，定义 `/uav1`、`/uav2` 的 namespace、PX4 sysid、MAVROS URL、起飞位置、悬停高度、机间安全距离和 setpoint 频率。
- 新增 `scripts/validate_stage0.ps1`，检查阶段 0 所需文件、JSON 配置、脚本契约和全部 `--dry-run` 调用。
- 新增 `start_single_uav.bat`、`start_two_uav.bat`、`start_mavros_uav1.bat`、`start_mavros_uav2.bat`、`start_mission.bat`、`record_logs.bat`、`kill_all.bat`。
- 新增 `README.md`，记录验证命令、dry-run 命令和当前限制。

验证结果：

```text
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
[PASS] Stage 0 scaffold validation passed.
```

当前限制：

- 非 `--dry-run` 模式尚未接入真实 RflySim、PX4 SITL、MAVROS 和 mission launch 命令。
- 下一步应进入阶段 1：确认本机 ROS/RflySim/PX4 启动命令，并将 `start_single_uav.bat` 从 dry-run 骨架扩展为单机 MAVROS 闭环启动脚本。

### 2026-07-26 阶段 1 单机仿真启动链路

已完成：

- 参考 `28com_sim/28com_SITL/UAVSITL.bat`，确认 Windows 侧原始流程会启动 RflySim3D、QGroundControl、CopterSim 和 PX4 SITL。
- 参考 `28com_sim/UAV_demo/WinWSLRunDemo.bat` 与 `28com_uav/shfiles/demo.sh`，确认 WSL 侧通过 `RflySim-20.04`、VcXsrv、xterm 启动 ROS 链路。
- 新增 `config/stage1_single_uav.json`，记录 Stage 1 单机任务的 launch 契约。
- 扩展 `config/env_template.bat`，加入 `PSP_PATH`、`PSP_PATH_LINUX`、`RFLYSIM_WSL_DISTRO`、`RFLYSIM_UAV_SITL_SCRIPT`、`REF_28COM_UAV_DIR`、`REF_28COM_UAV_WSL_DIR`、`FUTURE_AIRCRAFT_SIM_WSL_DIR` 等路径。
- 新增 `scripts/start_vcxsrv.bat`、`scripts/start_rflysim_sitl_single.bat`、`scripts/start_wsl_ros_single.bat`。
- 重写 `scripts/start_single_uav.bat`，使其编排 VcXsrv、SITL、等待启动、WSL ROS 任务链。
- 新增 `scripts/wsl/stage1_single_uav.sh`，在 WSL 中启动 `sensor_pkg/main.py` 与 `mission_pkg basic_test.launch enable_logging:=true`。
- 新增 `scripts/validate_stage1.ps1`，验证 Stage 1 配置、路径、dry-run 和 WSL 脚本契约。

验证结果：

```text
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
[PASS] Stage 0 scaffold validation passed.

powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
[PASS] Stage 1 single-UAV launch validation passed.
```

当前限制：

- 已完成 dry-run 与脚本契约验证，尚未在本轮实际打开 RflySim3D/QGroundControl/CopterSim 做 live 验证。
- Stage 1 仍复用原 28com 单机 `/mavros` 命名空间；多机 `/uav1`、`/uav2` namespace 改造进入阶段 2。

### 2026-07-26 阶段 2 双机 SITL 与 MAVROS namespace

已完成：

- 新增 `config/stage2_two_uav.json`，定义 `/uav1`、`/uav2` 的 namespace、PX4 sysid、MAVROS fcu URL、GCS URL 和起飞配置。
- 扩展 `config/env_template.bat`，加入 `STAGE2_POS_X_STR`、`STAGE2_POS_Y_STR`、`STAGE2_YAW_STR`、`STAGE2_BOOT_WAIT_SECONDS`。
- 新增 `scripts/start_rflysim_sitl_two.bat`，运行时从原始 `28com_sim/28com_SITL/UAVSITL.bat` 生成临时双机 SITL wrapper，不修改原文件。
- 新增 `scripts/start_wsl_mavros_two.bat` 与 `scripts/wsl/stage2_two_mavros.sh`，在 WSL 中启动 `ROS_NAMESPACE=uav1` 和 `ROS_NAMESPACE=uav2` 两个 MAVROS 实例。
- 更新 `scripts/start_mavros_uav1.bat`、`scripts/start_mavros_uav2.bat`，支持单独启动对应 namespace 的 MAVROS。
- 更新 `scripts/start_two_uav.bat`，编排 VcXsrv、双机 SITL、等待启动、双 MAVROS namespace。
- 新增 `scripts/validate_stage2.ps1`，验证双机配置、原始 SITL marker、dry-run、临时 SITL 生成和 WSL MAVROS 命名空间契约。

验证结果：

```text
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
[PASS] Stage 0 scaffold validation passed.

powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
[PASS] Stage 1 single-UAV launch validation passed.

powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
[PASS] Stage 2 two-UAV namespace validation passed.
```

当前限制：

- 已完成 dry-run、双机 SITL 临时脚本生成和 namespace 启动契约验证，尚未在本轮实际打开 RflySim/QGC/CopterSim/WSL 做 live 验证。
- Stage 2 只建立双机 MAVROS namespace 基础，不包含双机任务树、错峰起飞控制或 ego-swarm。
