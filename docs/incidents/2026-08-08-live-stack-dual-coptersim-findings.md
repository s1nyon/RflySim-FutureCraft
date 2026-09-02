# 2026-08-08：双机启动只加载一架 CopterSim 的取证与修复设计

> 状态：**Resolved**（修复已实施并经 5 次连续 live cycle 验证，2026-08-08）
> 关联任务：P0 Live Stack Lifecycle 第一次完整真实 closure
> 关联文档：`docs/architecture/2026-08-08-live-stack-lifecycle-design.md`、`docs/incidents/2026-08-08-cleanup-script-hazard.md`
> 取证时间：2026-08-08 16:25 前后（Session 1 真实宿主进程状态）
> 修复提交：`0f5af43`（CopterSim 实例化）、`a84c44f`（stage2 fail-fast/批次根因）、
>  `d787480`（拓扑健康门）、`2c21b88`（ownership/stop 硬化）、`fd54835`（回归测试接入）

---

## 1. 症状

使用正式 lifecycle 入口（`start_predicted_course_two_uav.bat` → 生成 SITL wrapper →
`start_rflysim_sitl_two.bat`）启动双机栈时，**GUI 侧只加载了一架 CopterSim**，
但 WSL 侧 PX4 SITL 却正确启动了两架。

比赛是双机协同（PBL-1 双机飞行基线），当前 wrapper 启动状态无法支撑双机飞行。

## 2. 取证（2026-08-08 16:25，真实宿主机）

### 2.1 进程表

```text
pid 17944  CopterSim.exe 1 1 310 0 2 SLAMScene 0 -0.7 16 90 1 Mavlink_Vision   (唯一一架 CopterSim)
pid 20928  QGroundControl.exe -noComPix
pid 18912  RflySim3D.exe -cmd=RflyChangeMapbyName-SLAMScene                     (15:58 启动，属上一 stack)
```

### 2.2 当前 stack manifest（stack-20260808T081159Z-6a60f968）

- `windows_processes`：1 个 `gui:CopterSim`（pid 17944）；RflySim3D **不在**本 stack
  manifest（属上一 stack 残留，对本 stack 为 unknown）；
- `wsl_processes`：`wsl:px4_uav1`（pid 215）与 `wsl:px4_uav2`（pid 417，另含
  `px4-simulator` pid 496），均以 **spawn_attested** 自动登记成功，五重证据完整
  （marker / start-after-parent / exe / cmdline instance index / transaction）；
- `health`：只有 `GUI_READY`、`COURSE_READY`；`ROSCORE_READY` /
  `MAVROS_UAV1_CONNECTED` / `MAVROS_UAV2_CONNECTED` 缺失（Stage2 未完成）。

### 2.3 SITL wrapper trace（%TEMP%\sitl_wrapper_trace.txt）

```text
copter registered pid=17944
copter done
copter done
```

第二轮迭代没有注册任何 pid，直接跳过。

## 3. 根因

### 3.1 主因：wrapper 循环内按全局进程名跳过（generate_sitl_wrapper.ps1）

为替代 28com 原 `UAVSITL.bat` 中 `taskkill /im CopterSim.exe` 的名称扫杀，
`generate_sitl_wrapper.ps1` 在 CopterSim 循环**内部**插入：

```bat
tasklist|find /i "CopterSim.exe" >nul && echo [STACK] CopterSim already running; ... && goto copter_done
```

第 1 架 CopterSim 启动后，第 2 轮迭代的 `tasklist|find` 立即命中，直接
`goto copter_done`，**第 2 架永不启动**。该守卫同时破坏了 28com 原脚本
“先清干净再逐架启动”的两机语义。

### 3.2 次因：wrapper 生成到 %TEMP%，`%~dp0\UAVSITL.py` 路径失效

`start_rflysim_sitl_two.bat` 把生成的 wrapper 写到
`%TEMP%\future_aircraft_stage2_uavsitl.bat`，其中：

```bat
start /B /separate %PSP_PATH%\Python38\python.exe "%~dp0\UAVSITL.py"
```

`%~dp0` 解析为 TEMP 目录，而 `UAVSITL.py` 实际在
`28com_sim\28com_SITL\UAVSITL.py`，导致 UAVSITL.py 自动加载链失效
（仿真参数下发/额外初始化缺失）。

## 4. 同轮其他现场观察（记录供后续排查）

1. **stack-20260808T080422Z-44412b33（16:04，.failed）**：
   实际 5 项 health 全部 `ready=true`（含 MAVROS 双机 connected），但当时 commit
   `f0d4e8b` 的 manifest 没有 PX4 spawn_attested 条目 → 该轮按 fail-closed 判 failed；
   说明 Stage2 自动启动链在 16:04 曾自然完成过一次。
2. **stack-20260808T081159Z-6a60f968（16:12）Stage2 悬挂**：
   `start_wsl_mavros_two.bat`（pid 19952）于 16:12:31 启动，`mavros_launch.log`
   首行在 16:20:05 才写出，且只有 `STACK_ID/HEALTH_DIR/MANIFEST` 一行；
   后续 `HEALTH_DIR_WSL` / `MANIFEST_WSL` / `launching stage2` 均未写出，
   Stage2 未启动（manifest 无 roscore/mavros 条目）。断点疑似集中在
   STACK_HEALTH_DIR 的 PowerShell 路径转换步骤，待下轮用真实日志定位。
3. **RflySim3D 残留**：pid 18912 属上一 stack（15:58），本 stack 未认领，
   `stack_inspect` 会将其报告为 unknown → fail closed。符合预期，但 fresh-instance
   前必须 verify clean。
4. **上一轮 closure 不能作为成败样本**：live 过程中工具执行环境超时触发 WSL VM
   重启，污染了进程/端口状态，该轮结果不计入 lifecycle closure 结论。

## 5. 修复设计（最小改动，Yellow 区，实施前需用户确认）

### 5.1 按本 stack + 架次判断，不再按全局进程名

去掉循环内 `tasklist|find "CopterSim.exe" → skip` 守卫，改为：

- pid 文件放入 `logs/live_stack/<stack_id>/pids/copter_<cntr>.pid`（stack 隔离，
  不跨 stack 误判）；
- 文件不存在或对应进程已退出 → 启动并登记该架；
- 文件存在且进程存活 → 跳过（防同一 stack 重复拉起）；
- 无 STACK_ID 的 plain 模式保持原语义直接启动。

### 5.2 修正 `%~dp0\UAVSITL.py` 路径

wrapper 生成时把 `%~dp0` 替换为真实 `28com_SITL` 源目录，恢复 UAVSITL.py 加载链。

### 5.3 保留单实例守卫但明确 unknown

RflySim3D / QGC 的“已运行则跳过”逻辑保留（GUI 本来就应单实例），跳过时明确
记录为 unknown，由 `stack_inspect` fail-closed 把关。

### 5.4 验证顺序

1. `scripts\validate_lifecycle.ps1`（含 lifecycle 静态契约）全 PASS；
2. 相关 Stage 验证不回归；
3. 真实机：clean host → 自然启动 → 双 CopterSim 登记 → PX4 双机 spawn_attested →
   Stage2 5 项 health → 只读 inspect → stop DryRun → 报用户批准后第一次真实 stop。

## 6. 状态与下一步

- **已修复并 live 验证**（见 `docs/evidence/2026-08-08-lifecycle-p0-fix-live-validated.md`）：
  - §5.1 双 CopterSim 实例化已落地（stack-scoped pid 文件 + `gui:CopterSim/uavN` role +
    `--instance-marker`，循环内不再有全局名称守卫）；
  - §5.2 `%~dp0\UAVSITL.py` 已改为经 `UAV_SITL_DIR`（28com_SITL 真实绝对路径）解析；
  - 现场 trace 证实：`copter uav1 registered` / `copter uav2 registered` 两架独立登记，
    PID 互异；
  - 5 次连续 fresh start → READY → stop clean 全部通过。

## 7. 追加根因（live 验证过程中定位）

单 CopterSim 的直接根因是 wrapper 循环内的名称守卫；但 live 首轮验证又暴露了
**第二个致命根因**：`start_wsl_mavros_two.bat` DRY-RUN 块内 echo 文本中的括号
`(GUI_READY/...)` 提前关闭 `if (...)` 块，使 `exit /b 0` 无条件执行——mavros
wrapper 在 step A 后静默退出，stage2（roscore/MAVROS）从未启动。同一类括号 bug
还存在于 step B/C/D 失败块与 stage8 recorder dry-run 块。修复后 stage2 全链路
正常（step A→E trace 齐全，health gate ready）。详见开发日志。
