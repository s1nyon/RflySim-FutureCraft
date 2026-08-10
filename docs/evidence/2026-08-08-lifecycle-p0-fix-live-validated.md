# P0 Live Stack Lifecycle 修复与 live 验证（2026-08-08）

> 状态：**Resolved（live 已验证）**
> 提交：`0f5af43` `a84c44f` `d787480` `2c21b88` `fd54835`（均未 push）
> 验收：5 次连续 fresh start → READY → stop clean 全部通过

## 1. Confirmed root causes

### RC1：单 CopterSim（第二架被跳过）

- 现象：GUI 只有一架 CopterSim；wrapper trace `copter registered pid=17944 /
  copter done / copter done`；manifest 只有一个 `gui:CopterSim`。
- 直接原因：`generate_sitl_wrapper.ps1` 在**每个** CopterSim 循环迭代内插入
  `tasklist|find /i "CopterSim.exe" >nul && ... goto copter_done`。第一架启动后，
  第二架迭代命中"任意 CopterSim.exe 已存在"即跳过。pid 文件还是共享的
  `%TEMP%\copter.pid`。
- 为什么之前 health gate 没发现：GUI_READY 只按
  `(Get-Process RflySim3D,CopterSim).Count -ge 2` 计数（1 架 CopterSim +
  RflySim3D 就通过），从不检查 manifest role/实例计数/ownership。

### RC2：wrapper 相对路径语义被破坏

- 现象：wrapper 生成在 `%TEMP%\future_aircraft_stage2_uavsitl.bat`，其中
  `%~dp0\UAVSITL.py` 解析到 TEMP，而 UAVSITL.py 在 `28com_sim\28com_SITL\`。
- 直接原因：生成位置与原始 28com BAT 的 `%~dp0` 依赖冲突。
- 修复：wrapper 注入 `UAV_SITL_DIR=<28com_SITL 绝对路径>`，所有 `%~dp0` 替换为
  `%UAV_SITL_DIR%\`；不再依赖 wrapper 所在目录。

### RC3：Stage2 从未启动（mavros wrapper 静默退出）——live 首轮验证定位

- 现象：`start_wsl_mavros_two.bat` 只写出 step 0/step A 后不再继续；
  `mavros_launch.log` 缺 `HEALTH_DIR_WSL`，stage2（roscore/MAVROS）未启动，
  health gate 永远 NOT_READY。
- 直接原因（经 DBG 行级追踪确认）：DRY-RUN 块 echo 文本中的括号
  `(GUI_READY/.../COURSE_READY)` **提前关闭 `if "%DRY_RUN%"=="1" (` 块**，使块内
  `exit /b 0` 变成无条件执行 → 批处理在 step A 后直接退出 0（`cmd /k` 下表现为
  挂起在提示符）。同一类括号 bug 也存在于 step B/C/D 失败块与
  `run_stage8_control_chain_recorder.bat` dry-run 块。
- 为什么之前 health gate 没发现：ROSCORE_READY/MAVROS 状态缺失 → gate fail-closed
  是对的，但 wrapper 侧"挂死"没有 fail-fast、没有逐行 trace，无法定位。

### RC4：health gate 缺双机拓扑 invariant

- 现象：即使双 PX4/双 MAVROS 连接，单 CopterSim 也能通过旧 gate。
- 直接原因：`health_gate.py` 只聚合 5 个布尔状态；GUI_READY producer 按名称计数；
  无 manifest role / 实例计数 / ownership 校验。

### RC5（live 验证过程追加）：WSL identity / 端口归属 / PID 复用

- `ps lstart` 是本地时间，`parse_lstart_iso` 曾当 UTC 用 → WSL 进程 start-time 与
  manifest（真 UTC）差 8 小时 → 所有 spawn_attested PX4 身份校验失败、stop 拒绝。
- manifest 条目缺 `start_time_raw` 而 WSL 进程表总有 raw → `entry_matches_process`
  把"单侧有 raw"当不匹配 → 永远失败（已改为两侧都有 raw 才比较 raw，否则 UTC）。
- WSL2 localhost 转发把 PX4 UDP 端口反射为 Windows 侧幻影 "px4" 进程（无 exe/
  cmdline）→ 必需端口在 Windows 侧永远"被 unknown 占用" → READY 栈无法过
  pre-stop inspect（已按"端口 owner 对应的栈内组件 owned_and_alive/orphan"语义归属）。
- stage2 顶层 bash 未登记、roslaunch 的 mavros_node 子进程未登记 → unknown
  fail-closed（已加 stage2 自登记 + "owned 进程的直接子进程豁免"）。
- 进程停止后 PID 被无关进程（如 WeGame browser）复用 → "identity mismatch after
  stop" 曾被当成失败且 stale 条目永久卡死后续 stop（已改为：PID 复用证明原进程
  已死，不算失败；clean 后自动退役 stale 条目，绝不杀新占用者）。

## 2. Changed（按文件）

- `scripts/lifecycle/generate_sitl_wrapper.ps1`：双 CopterSim 实例化（stack-scoped
  pid 文件、`gui:CopterSim/uavN` role、`--instance-marker`、无名称守卫）、
  `UAV_SITL_DIR` 注入、RflySim3D 渲染子进程 attach、manifest WSL 路径转换改
  `to_wsl_path.ps1`。
- `scripts/lifecycle/register_launcher.py`：`launch`/`attach-children` 子命令、
  `--instance-marker`；Windows spawn-attested 子进程登记（parent-pid 结构证据）。
- `scripts/start_wsl_mavros_two.bat`：逐 step A–E trace、`to_wsl_path.ps1`+`for /f`
  转换、`run_wsl_bounded.ps1` 超时 watchdog、批次括号 bug 修复、CRLF。
- `scripts/start_two_uav.bat`：mavros wrapper 恢复 `/k call`（PID 稳定供 stop）。
- `scripts/lifecycle/launch_stage2.ps1` / `scripts/wsl/stage2_two_mavros.sh`：
  step trace、stage2 顶层进程自登记。
- `scripts/lifecycle/stack_topology.py` + `health_probe.py` + `live_stack_start.ps1`：
  双机拓扑 invariant（CopterSim uav1/uav2、PX4 uav1/uav2 各恰好一个 owned alive、
  PID 互异、PID 复用即 NOT READY），`topology_report.json`。
- `scripts/lifecycle/process_table.py`：`parse_lstart_iso` 本地→UTC。
- `scripts/lifecycle/stack_manifest.py`：`entry_matches_process` raw 双侧比较。
- `scripts/lifecycle/stack_stop.py`：stage2 角色 argv 变换豁免、close 失败不致命、
  stop 后 PID 复用自动退役（绝不杀新占用者）。
- `scripts/lifecycle/stack_inspect.py`：WSL2 幻影端口语义归属、owned 子进程豁免。
- `scripts/lifecycle/to_wsl_path.ps1` / `run_wsl_bounded.ps1`：新 helper。
- `scripts/wsl/stage7_run_context.sh`：pgrep stderr 静音。
- `tests/lifecycle_topology_check.py`、`tests/lifecycle_wrapper_generation_check.py`、
  `tests/lifecycle_{manifest,inspect,stop}_check.py` 扩展；`validate_lifecycle.ps1`
  接入新测试。

## 3. Safety properties（保持/新增）

- 无全局杀：仍无 `taskkill /im`、`pkill`、`wsl --shutdown`；banned-command 契约 PASS。
- stack-scoped ownership：所有停止目标必须 PID+start-time+cmdline 与 manifest
  匹配（或已登记 PGID/已知 argv 变换）。
- instance-scoped CopterSim：role `gui:CopterSim/uavN` + 独立 pid 文件 + 独立 PID。
- PID 复用保护：pre-stop 遇到 stale 一律 fail-closed；stop 后复用自动退役但绝不杀
  新占用者（live 实证：WeGame browser 占用 QGC 旧 PID，未被触碰）。
- fail-safe unknown：unknown/stale/端口冲突 → inspect 非零，禁止继续。

## 4. Live validation（2026-08-08，Session 1）

每轮 = clean → fresh start → 双 CopterSim → 双 PX4 → 双 MAVROS → READY → stop →
owned=0。

| Cycle | stack_id | CopterSim uav1/uav2 | PX4 uav1/uav2 | health | stop |
|---|---|---|---|---|---|
| 1 | 76ca63d1 | 28816 / 31112 | 215 / 417 | 5/5+TOPOLOGY | clean（一次性退役 1 个 pre-自动退役 stale 条目） |
| 2 | aabf3d7a | 32348 / 36156 | 215 / 417 | 5/5+TOPOLOGY | clean 首次 |
| 3 | 346c1b27 | 38796 / 35136 | 270 / 472 | 5/5+TOPOLOGY | clean 首次 |
| 4 | 27b84427 | 33644 / 39800 | 215 / 417 | 5/5+TOPOLOGY | clean 首次 |
| 5 | 166e18be | 37308 / 11720 | 215 / 417 | 5/5+TOPOLOGY | clean 首次 |

每轮 CopterSim 均 PID 互异、cmdline 第二参数为实例索引（1/2）；PX4 均 spawn_attested；
stop 后 Windows/WSL/计划任务零残留。

## 5. Remaining risks / not yet tested

- **未验证**：READY 之后的 FAST-LIO/EGO/飞行链（本轮只做 lifecycle 闭环，未动飞行）；
  因此 PBL-1 飞行不受本轮验证背书，恢复飞行前需按原阶梯重验。
- 批次括号类 bug 属于 cmd 解析脆性，静态测试无法穷尽；新增 wrapper 生成契约测试
  覆盖已发现的模式，但未来新增 .bat 块内 echo 时需复查。
- WSL2 幻影端口归属依赖"端口 owner 对应组件 owned_and_alive/orphan"语义；若未来
  增加新端口/新组件，需同步更新 `OWNER_ROLE_PREFIXES`。
- PID 复用自动退役只发生在 stop clean 后；pre-stop 的 stale 仍 fail-closed（符合设计）。
- 之前发现的 7.5 分钟"首行日志延迟"与 16:54 wrapper 生成未执行的环境性现象，无法
  在本次环境中复现，记录为 historical suspicion，不视为当前 blocker。

## 6. Git

```text
fd54835 add lifecycle regression tests to validation entry
2c21b88 harden ownership/stop safety ...
d787480 enforce dual-stack readiness invariants ...
a84c44f harden stage2 fail-fast tracing ...
0f5af43 fix lifecycle CopterSim instance spawning ...
```

pushed: no
