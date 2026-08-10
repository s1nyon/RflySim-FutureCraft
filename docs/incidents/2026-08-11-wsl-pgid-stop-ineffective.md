# WSL 进程组 stop 失效：kill -PGID 返回 0 但进程组存活（2026-08-11）

> 状态：**OPEN（已知缺陷，待 Yellow Zone 修复）**
> 影响：`stack_stop.py`（lifecycle stop 路径），属于 change-gated lifecycle 代码

## 1. 症状

`stack_stop.py --execute` 对 manifest 归属的 WSL 进程组执行
`kill -INT/-TERM/-KILL -- -<pgid>` 后，进程组仍存活，stop 最终报：

```
[stop] NOT clean; see refused/actions/final_verification
```

manifest `stop.failure_reasons` 记录：

```
owned PGID ... (wsl:fastlio_session / wsl:sensor_bridge_uav1 / wsl:sensor_bridge_uav2 /
                wsl:fastlio / wsl:ego_swarm_session) still has N process(es) after stop
```

2026-08-11 两个 fresh 栈（`stack-20260810T173509Z-b096fe72`、
`stack-20260810T183443Z-e43eec5e`）均 2/2 复现。Windows 侧进程能正常关闭。

## 2. 观察

- 同一时刻，直接在 `wsl -d RflySim-20.04 -e bash -lic "kill -KILL -- -<pgid>"`
  手动执行同一命令，进程组立即退出。
- 差异点：`stack_stop.py` 通过 `subprocess.run(["wsl.exe","-d",distro,"-e","bash","-lic",cmd])`
  发出命令，返回值 0 但 kill 未生效；推测与 wsl.exe relay 会话/进程组命名空间
  或命令在 `bash -lic` 内的进程组归属有关，需在 WSL 侧做最小复现定位。
- PGID leader（bash 包装脚本）被杀后，其 roslaunch/子进程被 reparent 到 PID 1，
  需要按显式 PID 逐个清理，stop 脚本未覆盖这些未登记子进程。

## 3. 影响

- `live_stack_stop.ps1 -Execute` 会失败并留下 fastlio/ego 的 WSL 进程，
  占用传感器/规划链路，阻塞后续 fresh start（active manifest 判定）。
- 当前 workaround：对 manifest 中记录的 PGID 直接执行
  `kill -KILL -- -<pgid>`，再按显式 PID 清理 reparent 后的子进程
  （adapter/relay/laserMapping/ego_planner/traj_server/waypoint_generator 等），
  最后重跑 `stack_stop.py --execute` 完成 `clean: true` 记录。

## 4. 建议修复（Yellow Zone）

1. 在 WSL 侧复现 `kill -PGID` 失效的最小场景（直接 vs 经 wsl.exe relay）。
2. 修复 `WslStopBackend.stop_group`：必要时先 `kill -SIGNAL <pgid>`（leader）再
   `kill -SIGNAL -- -<pgid>`（group），或改为经 `setsid`/`killpg` 语义等价的
   明确命令；保证 stop 的进程组清理可靠、可验证。
3. 对 roslaunch 派生的未登记子进程：在 manifest 中补充 spawn_attested 登记，
   或在 stop 时按父进程结构证据清理，避免 reparent 孤儿残留。
4. 离线生命周期测试（`validate_lifecycle.ps1`）补充该场景回归。
