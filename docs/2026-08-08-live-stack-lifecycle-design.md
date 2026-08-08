# P0 Safe Live Stack Lifecycle — 设计文档

> 日期：2026-08-08
> 状态：Design + Offline Implementation（live 执行待用户批准）
> 关联事故：`docs/2026-08-08-cleanup-script-hazard.md`（强杀 GUI + `pkill -9` + `wsl --shutdown` + 计划任务循环后蓝屏）

## 1. 目标

让 live 仿真的启动、停止和 fresh-instance 重复验证变得**可控、可证明、不通过系统级扫杀破坏宿主机**：

- 危险 cleanup 入口立即失效（fail-fast stub），任何人/Agent 无法一键执行旧的
  `Stop-Process -Force` / `pkill -9 -f` / `wsl --shutdown` / `taskkill /F /IM` 组合；
- 每次启动创建唯一 `stack_id` 与 run-scoped 生命周期 manifest；
- 停止只针对 manifest 证明归属的进程（PID + start-time + command-line 三重验证）；
- inspect 只读、遇到 unknown 进程 fail closed，只报告不自动 kill；
- Session-1 启动链显式产生健康状态（GUI/ROSCORE/MAVROS×2/COURSE），任一失败 fail closed；
- fresh-instance = inspect → graceful stop → verify clean → start(new stack_id) → health gate → readiness → flight；
  停止/清理验证失败时**禁止自动 force retry**，直接停止并报告用户。

非目标：sparse route、D435i、视觉、EGO-Swarm 核心修改。

## 2. Red-Zone（AGENTS.md 同步写入）

未经用户明确授权，禁止：

1. `wsl --shutdown`（WSL distribution 级关机）；
2. 按进程名称大范围 `pkill -9 -f` / `pkill -9 -x`；
3. `taskkill /F /IM` 式名称扫杀；
4. 名称匹配后批量 `Stop-Process -Force`；
5. 为 fresh-instance 自动循环硬重启；
6. 删除/重建宿主机计划任务作为普通 retry 手段。

允许停止的进程必须能证明由当前项目、当前 stack instance 启动并拥有
（manifest + PID + start-time + command-line 指纹一致）。

## 3. 组件架构

```text
scripts/live_stack_start.ps1       启动编排：stack_id + manifest + Session-1 任务 + ownership 记录
scripts/live_stack_inspect.ps1     只读 inspect（永不 kill）
scripts/live_stack_stop.ps1        优雅 stop（默认 DryRun，-Execute 才真停）
scripts/live_stack_fresh_instance.ps1  fresh-instance 编排（默认 DryRun）
scripts/wsl/live_stack_wsl_ops.sh  WSL 只读快照 + 显式 PID kill（无 pkill / 无 wsl --shutdown）
scripts/lifecycle/*.py             纯逻辑核心（可离线测试）：
  stack_manifest.py                stack_id、manifest schema、指纹、PID 复用校验
  stack_ownership.py               创建时登记（register_process；无名称/regex 认领）
  stack_register.py                registration CLI（唯一 ownership 授予入口）
  register_launcher.ps1            Windows 进程创建即登记（Process.Start -PassThru）
  generate_sitl_wrapper.ps1        SITL wrapper 生成（GUI 创建时登记、剥离名称杀）
  process_table.py                 Windows/WSL/Fake 进程表后端
  stack_inspect.py                 只读 inspect（owned/orphan/stale/unknown，fail-closed）
  stack_stop.py                    优雅 stop（PGID-aware、最终验证 clean）
  health_gate.py                   每状态独立文件的健康门（原子写、并发安全）
  fresh_instance.py                fresh-instance 阶段序列与 gate 校验
scripts/wsl/lifecycle_common.sh    共享 stack_register() helper
scripts/cleanup_sim_stack.ps1      → 已替换为 fail-fast hazard stub
scripts/restart_live_stack.ps1     → 已替换为 fail-fast hazard stub
tests/lifecycle_*.py               离线回归测试
scripts/validate_lifecycle.ps1     lifecycle 验证入口
```

## 4. Manifest（`logs/live_stack/<stack_id>/stack_manifest.json`）

```json
{
  "schema_version": 1,
  "stack_id": "stack-20260808T120000Z-a1b2c3d4",
  "git_commit": "<40-hex or null>",
  "start_time_utc": "2026-08-08T12:00:00Z",
  "launcher": {
    "kind": "scheduled_task",
    "identity": "\\FutureAircraftSim_LiveStack_stack-20260808T120000Z-a1b2c3d4",
    "pid": 1234,
    "command_line": "cmd /c call ...\\start_predicted_course_two_uav.bat"
  },
  "ros_master": {"uri": "http://127.0.0.1:11311", "host": "127.0.0.1", "port": 11311},
  "simulation_instance_id": "px4-...",
  "windows_processes": [
    {"pid": 111, "name": "RflySim3D", "start_time_utc": "...", "command_line": "...", "role": "gui:RflySim3D", "verified_at_utc": "..."}
  ],
  "wsl_processes": [
    {"pid": 222, "pgid": 222, "name": "px4", "start_time_utc": "...", "command_line": "...", "role": "px4_sitl", "verified_at_utc": "..."}
  ],
  "required_ports": [{"port": 14600, "protocol": "udp", "owner": "uav1-mavros"}],
  "health": {"schema_version": 1, "all_ready": true, "statuses": {}},
  "stop": {"last_stop_reason": null, "last_stop_utc": null, "clean": null}
}
```

关键点：

- 不依赖裸 PID：owned 条目必须同时记录 PID、进程 start-time 与 command-line 指纹；
- 每个条目必须携带 `ownership: {granted: "at_creation", reason, granted_at_utc}`；
- `entry_matches_process(entry, proc)` = PID 相同 AND start-time 在容差内（默认 ±2s）
  AND command-line 归一化指纹相同；任一不满足即视为 **PID 复用 / 非同一进程**，
  停止时拒绝操作并 fail closed；
- `logs/` 已在 `.gitignore`，manifest 属于 run-scoped 运行产物，不入库。
- **Ownership 只在创建时授予**：禁止扫描系统进程按名称/regex 认领（P0.1）。

## 5. Inspect（只读）

状态机：

```text
owned_and_alive      manifest 条目在当前进程表中精确匹配
owned_but_exited     manifest 条目当前不存在
owned_orphan         leader 已退出但登记的 PGID 仍有进程（仍属 owned，可停）
stale_pid_reuse      PID 存在但 start-time/指纹不匹配（fail closed，报告）
unknown_suspicious   栈相关进程名但不在 manifest（fail closed，报告，绝不 kill）
port_occupied        必需端口被非 owned 进程占用（报告）
ros_master_alive / mavros_uav1_connected / mavros_uav2_connected / course_ready
```

判定规则：

- 存在任何 `unknown_suspicious` / `stale_pid_reuse` → inspect 退出码非零，报告明细，
  调用方不得继续（fail closed）；
- inspect 没有任何 kill/stop API，纯查询。

## 6. Graceful Stop（manifest-only）

每类 owned 进程按顺序：

1. 优雅关闭：WSL `kill -INT`（对**登记的 PGID**，`setsid` 独立会话）；
   Windows GUI `CloseMainWindow` /
   无 `/F` 的 `taskkill /PID`；cmd 窗口 `Stop-Process`（无 -Force）；
2. wait（默认 5s，可配）；
3. `SIGTERM`：WSL `kill -TERM -- -PGID`；Windows `Stop-Process`（无 -Force）；
4. wait（5s）；
5. 最后手段强制：仅当对**当前进程表**重新完成 PID+start-time+command-line
   验证后，WSL `kill -KILL -- -PGID` / Windows `Stop-Process -Force`，并把原因写入
   manifest `stop` 段；
6. 验证失败（PID 复用等）→ 拒绝强制，fail closed 报告；
7. **最终验证**：所有信号阶段后重新 snapshot/inspect，确认 owned alive=0、无 owned
   orphan、无 stale/identity mismatch、无 signal 失败，才写 `clean=true`；
   否则 `clean=false` 并记录 failure reasons（P0.1，stop 自身保证，不依赖调用方）。

禁止：WSL distribution 级 shutdown、全局 pkill、名称扫杀。

计划任务：stop 只删除 manifest 中记录的、属于本 stack 的唯一任务名
（`\FutureAircraftSim_LiveStack_<stack_id>`），绝不按通配/惯例删除任务。

## 7. Session-1 启动编排与健康门

现状：Session-1 任务可拉起 GUI，但 roscore/MAVROS 曾静默未就绪（需人工
`stage2_two_mavros.sh`）。修复：

- `stage2_two_mavros.sh` 启动后执行健康探测，向
  `logs/live_stack/<stack_id>/health/<STATUS>.json` 写入状态（每状态独立文件，原子写）；
- `start_wsl_mavros_two.bat` 透传 `STACK_HEALTH_DIR`，并轮询 health.json；
- `start_predicted_course_two_uav.bat` 在加载 course 后写 GUI_READY / COURSE_READY；
- 状态枚举（固定）：`GUI_READY`、`ROSCORE_READY`、`MAVROS_UAV1_CONNECTED`、
  `MAVROS_UAV2_CONNECTED`、`COURSE_READY`；
- 每个 producer 只写自己的状态文件，禁止跨 Windows/WSL 共享 read-modify-write（P0.1）；
- `all_ready` 为 false → fail closed，不进入 FAST-LIO / arming；
- 保持 `--dry-run` 兼容（validate_stage8 依赖）。

## 8. Fresh-Instance 序列

```text
1. inspect（当前 manifest）           → 只有 owned_and_alive/owned_but_exited 且无 unknown/stale
2. graceful stop owned stack          → 失败即报告，禁止自动 force retry
3. verify clean（再次 inspect）       → owned alive=0 且无 unknown 才通过
4. start new stack                    → 新 stack_id / 新 simulation_instance_id
5. health gate（5 项全 ready）
6. readiness（Stage 7 no-arm）
7. flight
```

每个 run 记录：`startup_success`、`flight_success`、`shutdown_clean`。
`fresh_instance.py` 固化该序列；任何阶段 gate 失败 → 停止并向用户报告。

## 8.1 Stack Context（P0.1）

`live_stack_start.ps1 -Execute` 写出 `logs/live_stack/<stack_id>/stack_context.env`
（STACK_ID / STACK_MANIFEST / STACK_MANIFEST_WSL / STACK_HEALTH_DIR / STACK_HEALTH_DIR_WSL）。
后续 FAST-LIO / EGO / mission / recorder 启动器通过 `--stack-id` / `--manifest`（或环境变量）
消费该 context，并**在创建进程的瞬间**用 `stack_register` 登记 PID/PGID。

## 9. 离线回归测试（接触真实 RflySim 之前必须通过）

- `lifecycle_banned_command_check.py`：静态 banned 命令契约（wsl --shutdown /
  pkill -9 / taskkill /F /IM / 名称扫杀 Stop-Process -Force / schtasks /delete 越界）；
- `lifecycle_manifest_check.py`：manifest schema、stack_id 唯一性、指纹、
  PID 复用保护、创建时登记（ownership grant）、重复登记拒绝；
- `lifecycle_ownership_check.py`：注册 API 契约；确认无扫描式认领函数残留；
- `lifecycle_inspect_check.py`：owned alive/exited/orphan、unknown fail-closed、
  stale PID reuse、无 kill API；
- `lifecycle_stop_check.py`：DryRun 零副作用且输出 PID/PGID/start-time/fingerprint/
  ownership reason/信号序列；owned A/B 停止而未登记 C 存活；同名称只停登记的；
  旧 roscore 不被认领；PGID 隔离；orphan 经 PGID 停止；signal 失败 clean=false；
  stale PID reuse 拒绝；force 重验证；clean 来自最终验证；
- `lifecycle_health_gate_check.py`：每状态独立文件、原子写、并发不丢状态、
  all_ready、fail-closed；
- `lifecycle_fresh_instance_check.py`：序列顺序、无自动 force retry。

## 10. Live 验证门槛（需要用户批准后执行）

1. 先展示 DryRun 输出与设计（本文件 + `live_stack_*.ps1 -DryRun` 输出）；
2. 用户在场监督 1 次完整：start → readiness → flight → graceful stop → verify clean；
3. 3 次 fresh-instance；稳定后扩展 5 次；
4. 每次记录 `startup_success` / `flight_success` / `shutdown_clean`。

---

## 11. P0.1 Safety Hardening（2026-08-08）

用户审阅后确认方向正确，要求进入真实 `-Execute` 前补齐安全缺口。已落地：

1. **Ownership = 创建时登记**：删除 `stack_record.py`（名称/regex 扫描认领）；
   `stack_register.py` 成为唯一授予入口；Windows 经 `register_launcher.ps1`
   （Process.Start -PassThru）与生成 SITL wrapper 登记 GUI/cmd PID；WSL 经
   `lifecycle_common.sh stack_register()` 登记 roscore/MAVROS/px4-mavlink/
   sensor bridge/FAST-LIO/EGO/mission/recorder 的 PID+PGID。
2. **WSL 独立 PGID**：受管组件用 `setsid` 独立 session；stop 目标为经过验证的
   owned PGID（`kill -SIG -- -PGID`），仅最后手段对明确 owned PID。
3. **clean=true 来自最终验证**：stop 自身重新 snapshot/inspect，owned alive=0 且
   无 orphan、无 stale、无 signal 失败才为 clean，并记录 failure reasons。
4. **health 参数链路**：修复 `start_wsl_mavros_two.bat` 清空继承的
   STACK_ID/STACK_HEALTH_DIR bug；新增 `--manifest` 透传；`live_stack_start.ps1`
   写出 `stack_context.env`。
5. **health 每状态独立文件**：`health/<STATUS>.json` 原子写，producer 只写自己的
   状态；checker 聚合，缺失即 fail closed；并发写入不丢状态。
6. **后续进程登记**：stage7 fastlio/ego/flight runner 与 stage8 recorder 在创建时
   登记到当前 stack（STACK_ID/STACK_MANIFEST context）。
7. **离线测试扩展**：`tests/lifecycle_*.py` 覆盖 10 项场景；`validate_lifecycle.ps1`
   全 PASS；Stage 2/6D/7/8 未回归。
8. **无自动 adopt**：不存在 `--adopt-existing`；unknown 一律 report + fail closed。
9. **权限**：AGENTS.md §6 更新 Green（只读 inspect/DryRun/离线测试）、
   Yellow（lifecycle/launcher 代码修改）、Red（真实停止/PGID 强杀/计划任务/fresh-instance
   -Execute/首次 live 验证）。

**live 状态**：仍未执行。第一次 live 前展示 DryRun 输出、目标 PID/PGID、ownership 证明、
stop 顺序与 fail-closed 条件；第一次 live 周期为 start → health gate → no-arm readiness →
graceful stop → inspect clean（不飞行）。
