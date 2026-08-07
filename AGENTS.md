# AGENTS.md

本仓库是面向未来飞行器创新大赛的 RflySim 双无人机协同仿真工程，核心链路为 **FS-310 / RflySim / PX4 SITL / MAVROS / Faster-LIO / EGO-Swarm / multi_uav_mission**。

本文件只保存所有开发 Agent 都必须遵守的硬规则与入口。详细工程背景、架构、当前状态、调试决策树和测试阶梯见 `.agents/AGENT2READ.md`。

---

## 1. 开始任何任务前

按以下顺序建立上下文，不得只看 README 后直接改代码：

1. `AGENTS.md`
2. `.agents/AGENT2READ.md`
3. 若任务涉及 RflySim/PX4/MAVROS/WSL 启动链，再读 `.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md`
4. 与当前任务直接相关的 `docs/`
5. 当前实现、配置、测试和最近 run-scoped artifacts
6. 必要时再查历史故障文档

如果仓库文档彼此冲突，以 `.agents/AGENT2READ.md` 中的 **Truth Priority** 和最新 live evidence 为准。

---

## 2. 当前受保护基线（Protected Baseline）

截至 **2026-08-07**，项目当前应按以下事实工作：

- 双机 OFFBOARD、arming、起飞、Faster-LIO、EGO-Swarm 和错时完整穿隧道已经取得良好 live 结果。
- 该飞行链是当前 **PBL-1（Protected Baseline 1）**，后续新功能不得无声破坏它。
- 2026-08-07 引入 D435i 多传感器载荷后出现“飞机无法正常起飞”的集成回归，已按阶段策略隔离：
  `lidar_only` 模式（默认）下双机起飞已恢复；`full` 模式仍属视觉侧待办，不得默认用于飞行。
- `planner_commands=0`（`quadrotor_msgs/PositionCommand` md5 不一致）已定位并修复：
  flight runner/recorder 在 28com_uav 之后、project overlay 之前 source ego-planner-swarm devel；
  live 已复验（2026-08-07 晚 fresh-instance，以及 2026-08-08 PBL-1 3/4 fresh-instance 干净通过），
  不再作为当前 blocker。
- **当前最高优先级是 P0 Safe Live Stack Lifecycle**：live 仿真的启动、停止和 fresh-instance
  重复验证必须可控、可证明、不通过系统级扫杀破坏宿主机。
  设计见 `docs/2026-08-08-live-stack-lifecycle-design.md`，最新状态见 `.agents/AGENT2READ.md` §2.3。
- 仓库中旧的 `planner_commands=0` 无条件结论、2026-08-02 Stage 8 失败等记录属于历史诊断证据；
  除非 fresh live evidence 再次证明它们仍存在，否则不得把它们直接当作当前 blocker。

如果 fresh live evidence 与本段不再一致，立即更新 `.agents/AGENT2READ.md` 的 Current Truth，不要让旧状态继续误导后续 Agent。

---

## 3. 第一原则：保护已验证能力

出现“昨天能跑、今天坏了”的回归时，默认调查顺序为：

`最近新增功能/配置`
→ `集成接口、topic、TF、timestamp、launch/remap`
→ `资源负载与进程生命周期`
→ `watchdog/readiness/状态机`
→ `项目本地 adapter / mission logic`
→ `Faster-LIO / EGO / PX4 核心`

禁止反过来一上来重调 EGO、Faster-LIO、PX4 或整体坐标系。

任何修复都应遵循：

`复现 → 采证据 → 定位责任层 → 最小补丁 → 离线验证 → no-arm → 单机 → 双机 → 完整路线 → fresh-instance 重复`

禁止 shotgun debugging（同时改很多无关参数再看是否“碰巧好了”）。

---

## 4. D435i 开发策略

D435i 采用分阶段路线：

- **短期**：RGB / Depth 服务视觉识别和测距，不成为飞行主链的硬依赖。
- **后期**：在飞行基线稳定后，再把 Depth 作为独立升级接入 EGO 局部地图。

强制验收阶梯：

- `L0`: Mid360 / `lidar_only`，保持 PBL-1。
- `L1`: Mid360 + RGB。
- `L2`: Mid360 + RGB + Depth，但 Depth 不参与规划。
- `L3`: Depth 正式参与 EGO。

每一级必须证明不破坏前一级；不能为了视觉一次性把所有传感器和规划强耦合。

---

## 5. 安全与解锁

### 仿真

Agent 可以自主运行仿真 arming/flight，但必须同时满足：

- 当前 run 的 readiness PASS；
- 明确使用 `--simulation-only`；
- 明确使用 `--allow-arm`；
- `simulation_arm_policy.allow_arm=true`；
- run-id 与 simulation-instance-id 匹配当前实例。

任一条件不满足，不得 arm。

### 真机

- 真机始终人工 arm / 人工 Offboard。
- Agent 不得自行放宽真机安全门。
- 不得把仿真权限推导成真机权限。

### 5.1 Live Lifecycle Red-Zone

**未经用户明确授权，Agent 不得执行以下任何操作：**

1. `wsl --shutdown`（WSL distribution 级关机）；
2. 按进程名称大范围 `pkill -9 -f` / `pkill -9 -x`；
3. `taskkill /F /IM` 式名称扫杀；
4. 名称匹配后批量 `Stop-Process -Force`；
5. 为 fresh-instance 自动循环硬重启（cleanup → 立刻拉起整套栈）；
6. 删除/重建宿主机计划任务作为普通 retry 手段。

Agent 允许停止的进程必须能证明由**当前项目、当前 stack instance** 启动并拥有：
必须同时满足 PID + 进程 start-time + command-line 指纹与
`logs/live_stack/<stack_id>/stack_manifest.json` 中的 owned 记录一致（PID 复用保护）。

所有 live 启动/停止/fresh-instance 一律走 manifest 化安全入口：

```powershell
scripts\live_stack_start.ps1 -DryRun            # 或 -Execute（需用户批准）
scripts\live_stack_inspect.ps1 -Manifest <path> # 只读
scripts\live_stack_stop.ps1 -Manifest <path> -DryRun   # 或 -Execute
scripts\live_stack_fresh_instance.ps1 -DryRun
```

`scripts\cleanup_sim_stack.ps1` 与 `scripts\restart_live_stack.ps1` 已封禁为
**fail-fast hazard stub**（HAZARD-DISABLED，恒 exit 1），任何 Agent 不得恢复其旧逻辑。

遇到 unknown / stale / 端口被未知进程占用时 **fail closed**：只报告，不自动 kill；
stop/clean 验证失败时禁止自动 force retry，直接停止并向用户报告。

---

## 6. 修改权限

### Green：Agent 可自主修改并验证

- 项目内 Python / 普通 C++
- `future_aircraft_ws/src/multi_uav_mission/`
- launch / config / topic remap
- sensor bridge / adapter
- mission logic / tests / diagnostics
- Windows/WSL 启动与验证脚本
- 项目文档

### Yellow：可以调查，但修改前必须先向用户说明证据、影响面和设计

- `external/ego-planner-swarm` 源码
- Faster-LIO 核心算法/核心配置语义
- PX4 核心源码或 EKF 核心策略
- 双机统一坐标系的大改
- 大规模架构重构
- 大范围改变 watchdog / geofence 安全语义

### Red：未经用户明确授权不得执行

- 真机自动 arm
- force push
- 破坏性 git history rewrite
- 无备份覆盖外部 RflySim/CopterSim/PX4 运行资产
- 修改原 `28com_sim` / `28com_uav` 工程来“迁就”本项目

---

## 7. 固定工程约束

- 不修改 `28com_sim` 原工程；ROS 业务逻辑只放在 `future_aircraft_ws`。
- 多机命名空间固定为 `/uav1`、`/uav2`。
- 两架 UAV 当前运行独立 FAST-LIO 原点；不要假设两机轨迹天然在同一坐标系。
- EGO-Swarm 的 swarm trajectory broadcast 当前**不是可靠的机间避碰保证**。
- 机间安全当前优先依赖本机感知：Mid360 → grid map → replan / `EMERGENCY_STOP`。
- FAST-LIO `extrinsic_T=[0,0,0.1]` 是已验证约定，不得因 z 正负直觉再次“修正”。
- `/mavros/odometry/in`、`/mavros/odometry/out`、`/mavros/local_position/odom` 方向与用途不要混淆，详见 handbook。
- 传感器 JSON 保持无注释纯 JSON，必须可被 `json.loads` 校验。
- 不安装、不重新提出 UE Editor 路线；当前地图路线为 SLAMScene + 动态实体。

---

## 8. 测试与 live 纪律

默认验证顺序：

0. `scripts\validate_lifecycle.ps1`（涉及 live 生命周期/启动链/停止相关改动时）
1. 与改动直接相关的 focused test
2. `scripts\validate_stage6c.ps1`
3. `scripts\validate_stage6d.ps1`
4. `scripts\validate_stage7.ps1`
5. `scripts\validate_stage8.ps1`
6. live no-arm
7. 单机飞行（若改动影响飞行）
8. 双机起飞
9. 短导航
10. 完整穿隧道
11. fresh-instance 重复

不要为了“完整”机械跑所有阶段；但任何可能影响 PBL-1 的改动，至少要重新覆盖 Stage 7/8 相关离线测试和对应 live 阶梯。

每次 live run 必须使用当前 run-scoped artifacts，不得拿旧 readiness 报告授权新实例。

---

## 9. 推荐 live 入口

典型顺序：

```bat
scripts\live_stack_fresh_instance.ps1 -DryRun      # 先看完整序列与 inspect
scripts\live_stack_start.ps1 -Execute              # 新 stack_id + manifest + 健康门
scripts\live_stack_inspect.ps1 -Manifest logs\live_stack\<stack_id>\stack_manifest.json
scripts\run_live_fastlio_dual.bat
scripts\run_live_ego_swarm_dual.bat
scripts\run_stage7_topic_probe.bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

栈启动链（`start_predicted_course_two_uav.bat` → `start_wsl_mavros_two.bat` →
`stage2_two_mavros.sh`）现在显式产出健康状态
（`GUI_READY` / `ROSCORE_READY` / `MAVROS_UAV1_CONNECTED` / `MAVROS_UAV2_CONNECTED` /
`COURSE_READY`），任一失败 fail closed，不再依赖窗口是否出现。

停机：`scripts\live_stack_stop.ps1 -Manifest <path> -DryRun` → 确认后 `-Execute`。

禁止恢复旧的 `cleanup_sim_stack.ps1` / `restart_live_stack.ps1` 逻辑。

只读控制链取证：

```bat
scripts\run_stage8_control_chain_recorder.bat
```

不要在 readiness 未通过前跳过前置门禁直接飞。

---

## 10. Git 工作流

允许：

`inspect → edit → test → review diff → local commit`

规则：

- Agent 可以自行创建**本地 commit**。
- **未经用户明确许可不得 `git push`**。
- 不得 `force push`。
- 不得使用破坏性 `reset --hard` 清掉用户/其他 Agent 的工作。
- 不得因为工作区脏就随意 checkout 覆盖未知修改。
- 提交前检查 `git diff`，只包含当前任务必要修改。

原仓库旧规则中“直接提交 main 并 push”不再适用。

---

## 11. 文档真实性

文档分两类：

- **Current State / Current Truth**：只描述现在仍成立的事实。
- **Historical Incident**：保留过去失败和诊断经验，但不得继续作为当前 blocker。

修复一个故障后，必须同步把其状态从 Current 移到 Historical/Resolved；不要让下一任 Agent 重复修已经解决的问题。

如果 README、旧 docs 与最新 live evidence 冲突：先记录冲突，再依据 handbook 的 Truth Priority 工作，并在任务收尾时修正文档。

---

## 12. Agent 收尾格式

每个开发任务完成时，用以下五项交接：

- **Changed**：改了什么。
- **Evidence**：为什么认为问题在这里。
- **Validation**：跑了哪些测试 / live 阶梯，结果是什么。
- **Remaining Risk**：还有什么没有证明。
- **Next Recommended Step**：下一步最小动作。

禁止只回复“已修复”“应该没问题”或“测试通过”而不给证据。
