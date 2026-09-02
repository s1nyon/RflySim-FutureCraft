# 2026-08-08：live 栈硬清理脚本隐患与蓝屏事件记录

> 状态：**Hazard / Historical Incident**（危险操作记录，不是当前 blocker）
> 相关文件：`scripts/cleanup_sim_stack.ps1`、`scripts/restart_live_stack.ps1`
> （2026-08-08 曾为 untracked；现已提交并**替换为 fail-fast hazard stub**，见 §7）
> 触发背景：2026-08-08 00:41 之后 AI 为做“fresh-instance 重复验证”编写了这两个脚本，并在 00:41–00:57 之间反复硬重启整套仿真栈，最终于 00:57 左右触发系统蓝屏（重启时间 00:58:24）。

---

## 1. 事件时间线（本地时间 UTC+8）

| 时间 | 事件 |
| --- | --- |
| 2026-08-07 23:35 – 2026-08-08 00:10 | p05_r1..r4 系列 live 复测（期间出现少量失败） |
| 2026-08-08 00:15 | 新增 `scripts/wsl/stage8_chain_recorder_once.sh`（untracked） |
| 2026-08-08 00:18 – 00:39 | p05_r5/r5b/r5c/r5d 连续报 `PX4 simulation instance changed after Stage 7 readiness collection.` |
| 2026-08-08 00:41:20 / 00:41:45 | 创建 `scripts/cleanup_sim_stack.ps1` 与 `scripts/restart_live_stack.ps1`，开始“清理→计划任务重启”循环 |
| 2026-08-08 00:43 – 00:56 | p05_f1 / g1 / h1 / h2 四轮重启验证；h1 报 UAV2 FAST-LIO odom 60s 未发布；h2 报 UAV2 arming 失败（result=1） |
| 2026-08-08 00:49 | 修改 `scripts/wsl/stage7_run_context.sh`（px4 实例哈希改为 `pgrep -x px4`，未提交） |
| 2026-08-08 00:56:46 – 00:56:49 | WSL FAST-LIO 日志与 `p05_h2_ego.out` 最后写入 |
| 2026-08-08 00:57 前后 | **蓝屏**，00:58:24 系统重启 |

---

## 2. 主要隐患：`scripts/cleanup_sim_stack.ps1`

该脚本（untracked，未评审、未提交）以“idempotent cleanup”为名，实际包含多个高风险行为：

### 2.1 强制终止 GUI 仿真进程

```powershell
Get-Process | Where-Object { $simGuiPatterns -contains $_.ProcessName } |
    Stop-Process -Force
```

- `Stop-Process -Force` 直接强杀 RflySim3D（UE4）/CopterSim/QGC，不给正常退出与状态落盘机会。
- UE4 渲染进程被强杀后，与 WSL2 GPU / NVIDIA 驱动（当前 32.0.15.6094）之间可能遗留异常状态；本次蓝屏发生在该脚本循环使用期间，二者高度相关（无法 100% 归因，但按文档纪律先记录为高危操作）。

### 2.2 WSL 内 `pkill -9` 整链

```bash
pkill -9 -f stage7_live_fastlio ...
pkill -9 -f roscore
pkill -9 -x px4
```

- 对 roscore / px4 / mavros / sensor bridge 全部 SIGKILL，无优雅关停：残留 pid 文件、socket、`.ros/log` 状态，下一次启动容易出现“表面活着实则不通”的假象（这正是 00:41 之后多轮复测失败的重要原因）。

### 2.3 `wsl --shutdown`（最危险的一条）

```powershell
wsl --shutdown
```

- `wsl --shutdown` 会关闭**宿主机上所有 WSL 发行版**，不只是 RflySim-20.04。若用户其他 WSL 里正跑着任务，会被一并强杀，存在数据丢失风险。
- 蓝屏前后反复执行“强杀 UE4 + `pkill -9` + `wsl --shutdown` + 计划任务立刻重启整套栈”，是本机当时负载与崩溃场景的直接操作组合。

### 2.4 删除计划任务

```powershell
schtasks /delete /tn "\FutureAircraftSim_LiveStack_Session1" /f
```

- 该计划任务是 Session 1 交互桌面启动 GUI 栈的唯一可用通道（见 `.agents/AGENT2READ.md`）；脚本同时“创建任务→运行任务→再删除任务”，如果某一步在蓝屏/中断时停在半路，会留下已启用、还会自动触发的一次性任务（见 §4）。

---

## 3. 派生问题：`restart_live_stack.ps1`

`scripts/restart_live_stack.ps1`（untracked）第一步就是无条件调用 `cleanup_sim_stack.ps1`，等于把上述全部风险“一键化”，并且在 `$LASTEXITCODE -ne 0` 时直接 `throw`，容易把问题链拉长。**当前约定：不再使用这两个脚本**；需要重启仿真栈时，用标准入口 `scripts/start_predicted_course_two_uav.bat`，并在确认没有重复 cmd / WSL 实例的情况下执行。

---

## 4. 残留物（蓝屏中断导致）

1. **计划任务（已处理）**
   `\FutureAircraftSim_LiveStack_Session1` 曾处于启用状态（`Next Run Time = 2026-08-08 23:59:00`，动作是 `cmd /c call ...\start_predicted_course_two_uav.bat`，Session 1 / HIGHEST），若不管它会在今晚 23:59 **自动拉起整套仿真栈**。
   → **2026-08-08 已由用户确认删除**：`schtasks /delete /tn "\FutureAircraftSim_LiveStack_Session1" /f` 执行成功，`schtasks /query` 已确认任务不存在。

2. **字面量目录 `$STAGE7_RUN_DIR/`**
   仓库根目录出现一个名字就是 `$STAGE7_RUN_DIR` 的空目录（变量未展开的产物，untracked）。说明某条命令在 Windows 侧把 `$STAGE7_RUN_DIR` 当成了普通字符串；相关脚本引用 `$STAGE7_RUN_DIR` 时应改用 `%STAGE7_RUN_DIR%`（bat）或先展开再拼路径。
   → **2026-08-08 已删除**（定向 `git clean`，目录为空）。

3. **杂散文件 `pos_cmd`**
   仓库根目录 `pos_cmd`（94 字节）内容是某脚本 dry-run 输出 `[DRY-RUN] 5. run stage8_ego_chain_analyzer.py ...`，属于重定向误写，应删除。
   → **2026-08-08 已删除**。
   根因（2026-08-08 定位）：`scripts/run_stage8_control_chain_recorder.bat --dry-run` 的
   echo 文本含未转义的 `->`，cmd 把 `>` 当成重定向，落盘出 `pos_cmd`；
   已改为 `-^>`（commit `8e777b1`），validate_stage8 复跑不再生成该文件。

4. **`.ros/log` 超 1GB**
   roscore 启动时提示 `disk usage in log directory [/root/.ros/log] is over 1GB`，长时间不清理会影响 WSL 磁盘与启动速度（可 `rosclean` 或手动归档，操作前先确认没有正在运行的必要日志）。

---

## 5. 当前 live 验证结论（2026-08-08 01:10–01:22，fresh instance）

不使用上述清理脚本，走标准入口复测，全链路**通过**：

- 启动：`schtasks /run` 触发 `FutureAircraftSim_LiveStack_Session1`（Session 1 桌面）→ RflySim3D/SLAMScene + CopterSim×2 + QGC 正常；课程动态实体加载成功（object_count=34）。
- 注意：本次计划任务拉起后 **roscore/MAVROS 未自动就绪**（静默失败），手动执行 `scripts/wsl/stage2_two_mavros.sh` 后 ROS 层正常。这是又一个值得后续排查的编排问题。
- no-arm 门禁：run `stage7-20260807T171608Z-2812`，五项 gates 全 pass（identity/schema/freshness/isolation/stationary_stability），双机 unarmed，FAST-LIO 双链路 ~10 Hz 稳定。
- 完整飞行：`run_live_ego_swarm_dual.bat` + `run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`
  - `score_summary.json`: `success=true`，`duration_s=41.5`，`collision_count=0`，`min_uav_distance_m=0.85`，`offboard_loss_count=0`，`failure_reasons=[]`
  - `flight_report.json`: arming/offboard/takeoff/navigation/landing 双机全部 confirmed，executor exit 0
  - 与 AGENTS.md 记录的 PBL-1 基线（41.5 s、最小间距 0.85 m、零失败）一致。

**结论**：飞行链路本身没有回归；00:41 之后出现的“instance changed / uav2 odom 未发布 / uav2 arming 失败”是反复硬重启（cleanup 脚本 + `wsl --shutdown`）导致的实例/进程状态污染与系统不稳定，不是代码回归。未提交的 `stage7_run_context.sh`（`pgrep -x px4` 哈希）在本次 fresh instance 下工作正常（readiness 与 flight 的 instance id 一致）。

> 注：`stage7_run_context.sh` 的 `pgrep -x px4` 修改随后已**提交**（commit `8c74d51`）。

---

## 6. 建议处理

1. 删除/归档 `scripts/cleanup_sim_stack.ps1`、`scripts/restart_live_stack.ps1`（或改为“只优雅关停、不 `wsl --shutdown`”的评审版）。
   → **2026-08-08 已完成**：两个脚本替换为 fail-fast hazard stub（HAZARD-DISABLED，恒 exit 1），
   新的 manifest 化生命周期入口见 §7。
2. 删除 `$STAGE7_RUN_DIR/` 与 `pos_cmd`。
   → **2026-08-08 已完成**。
3. ~~经用户确认后删除今晚 23:59 会自动触发的计划任务~~ → **已完成（2026-08-08）**。
4. 决定 `scripts/wsl/stage7_run_context.sh` 的未提交修改是保留（本次实测可用）还是回退。
   → **2026-08-08 已完成**：保留并提交（`8c74d51`）。
5. 排查 `start_wsl_mavros_two.bat` 在 Session 1 计划任务下 roscore/MAVROS 静默不启动的问题。
   → **2026-08-08 已完成（offline）**：启动链显式产出健康状态并 fail closed（见 §7）；
   live 复验待用户批准后进行。

---

## 7. P0 处置结果（2026-08-08，Safe Live Stack Lifecycle）

设计文档：`docs/architecture/2026-08-08-live-stack-lifecycle-design.md`。

- **封禁**：`scripts/cleanup_sim_stack.ps1`、`scripts/restart_live_stack.ps1` 已替换为
  fail-fast hazard stub（`HAZARD-DISABLED`，恒 exit 1）；静态契约
  `tests/lifecycle_banned_command_check.py` 禁止 `wsl --shutdown`、`pkill -9`、
  `taskkill /F`、名称扫杀 `Stop-Process -Force`、`schtasks /delete` 越界；
- **Red-Zone**：`AGENTS.md` §5.1（未经明确授权不得执行上述操作；
  可停进程必须为 manifest 证明的当前 stack owned 进程，PID + start-time + command-line 验证）；
- **Ownership**：`scripts/lifecycle/stack_manifest.py` +
  `stack_ownership.py` + `stack_record.py`，每次启动创建唯一 `stack_id` 与
  `logs/live_stack/<stack_id>/stack_manifest.json`（Windows/WSL owned PID + start-time +
  command-line 指纹、simulation_instance_id、ROS master、launcher/任务身份）；
- **Inspect**：`stack_inspect.py`（只读，owned alive/exited、stale/PID-reuse、
  unknown fail-closed、端口占用、ROS/MAVROS 状态）；
- **Graceful stop**：`stack_stop.py`（manifest-only；INT/close → TERM →
  重验证后 KILL 并记录原因；禁止 WSL distribution 级 shutdown 与全局 pkill）；
- **Health gate**：`health_gate.py` + `health_probe.py`；启动链显式产出
  `GUI_READY` / `ROSCORE_READY` / `MAVROS_UAV1_CONNECTED` / `MAVROS_UAV2_CONNECTED` /
  `COURSE_READY`，任一失败 fail closed；
- **Fresh-instance**：`fresh_instance.py` + `live_stack_fresh_instance.ps1`
  （inspect → graceful stop → verify clean → start new → health → readiness → flight；
  失败禁止自动 force retry）；
- **入口**：`live_stack_start.ps1` / `live_stack_inspect.ps1` /
  `live_stack_stop.ps1` / `live_stack_fresh_instance.ps1`（默认 DryRun，`-Execute` 需批准）；
- **离线验证**：`scripts/validate_lifecycle.ps1` 全部 PASS；Stage 2/6D/7/8 现有验证未回归。

**live 状态**：尚未执行。第一次涉及真实宿主机进程停止/计划任务修改的 live 操作前，
先展示 DryRun 输出与设计并获得用户批准；随后用户在场监督 1 次完整周期，
再做 3 次（稳定后 5 次）fresh-instance，每次记录
`startup_success` / `flight_success` / `shutdown_clean`。

## 7.1 P0.1 Safety Hardening（2026-08-08）

用户审阅后要求进入真实 `-Execute` 前补齐安全缺口，已全部落地（offline 验证通过，
详见设计文档 §11）：

- **Ownership 创建时登记**：删除扫描式 `stack_record.py`；`stack_register.py` 为唯一
  授予入口；Windows GUI/cmd 经 `register_launcher.py`/生成 SITL wrapper 在创建瞬间
  登记；WSL 组件经 `lifecycle_common.sh stack_register()` 登记 PID+PGID（`setsid` 独立
  session）；
- **stop 按 owned PGID**（`kill -SIG -- -PGID`），`clean=true` 来自 stop 自身最终验证；
- **health 每状态独立文件**（原子写、并发安全），修复启动链 STACK_ID/HEALTH_DIR 继承；
- **后续 FAST-LIO/EGO/mission/recorder 创建时登记**到同一 stack（stack context）；
- **离线回归**：`validate_lifecycle.ps1` 全 PASS，Stage 2/6D/7/8 未回归；
  **live 仍未执行**（Red 操作需用户批准）。
