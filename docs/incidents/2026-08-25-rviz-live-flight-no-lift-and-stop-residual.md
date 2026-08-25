# RViz live ownership、无升力飞行失败与 stop 残留（2026-08-25）

> 状态：**RESOLVED / HISTORICAL**
> 运行实例：`stack-20260825T081042Z-756ce781`
> Stage 7 run：`stage7-20260825T081141Z-2768`
> manifest 记录的启动提交：`e55535334e5e8b53d2aedc6943b25e725c1abd1d`

> 2026-08-25 收尾：RViz `exec roslaunch` 身份片段已纳入标准 stop 验证；PGID 9329
> 经仓库正式 lifecycle 清理。随后 3/3 fresh startup 与 2/2 完整路线通过（一次 RViz
> OFF、一次轻量 dual RViz ON），no-lift 未再现。详见
> [`2026-08-25-infrastructure-recovery-closure.md`](../evidence/2026-08-25-infrastructure-recovery-closure.md)。

## 1. 本轮范围和结论

本轮实现了项目 RViz 的 lifecycle ownership 修复并完成一次 live 节点/manifest
验证；随后使用既有 Stage 7/8 路线尝试双机飞行。飞行未成功，不能计入 baseline
regression。没有修改 mission、setpoint 数值、TF、PX4、MAVROS、Faster-LIO 或
EGO-Swarm 算法。

标准 stop 关闭了主仿真栈并释放全部受控端口，但 RViz PGID `9329` 仍存活；manifest
最终记录 `clean=false`。因此当前环境不能称为 clean fresh-start 起点。

## 2. RViz ownership 问题与修复

最初的 `scripts/run_rflysim_rviz.bat dual` 直接启动 WSL roslaunch，没有在创建时登记
当前 stack manifest。Inspector 正确报告 5 个 `unknown_suspicious`（roslaunch、双
RViz、双 adapter）并禁止 arming。关闭 GUI 后 roslaunch 与两个 adapter 仍然存活；
经用户明确授权，只精确终止已核对 PID/start-time/command-line 的 Windows RViz
launcher 链，没有名称扫杀。

最小修复：

- Windows launcher 现在要求显式 `--stack-id` 和 `--manifest`；
- 新增 `scripts/wsl/rviz_live.sh`，source 既有 overlay 后在创建时登记自身
  PID/PGID 为 `wsl:rviz_session`，再 `exec roslaunch`；
- ROS setup 完成后才启用 Bash nounset，避免 Noetic setup 读取未定义
  `ROS_DISTRO` 时失败；
- RViz 仍然 optional、OFF by default，不进入 READY/health/control path。

Live 证据：

```text
manifest role: wsl:rviz_session
pid/pgid: 9329/9329
ROS nodes:
  /future_aircraft_uav1_rviz
  /future_aircraft_uav2_rviz
  /rviz_frame_adapter_uav1
  /rviz_frame_adapter_uav2
inspector: fail_closed=false, unknown_suspicious=0
UAV1 path frame: uav1_camera_init
UAV2 path frame: uav2_camera_init
```

这只证明 ownership、节点与 per-UAV frame label；没有形成 RViz ON 完整飞行性能 PASS。

## 3. 飞行尝试

第一次调用 flight runner 被 run-scoped readiness freshness gate 拒绝：旧报告超过
120 秒，`stale report`，两机保持 disarmed。随后用标准
`stage7_sensor_readiness.py --backend ros` 在同一 run/instance 下重新只读采样：

```text
identity=pass
schema=pass
freshness=pass
isolation=pass
stationary_stability=pass
uav1.armed=False
uav2.armed=False
ready=True
simulation_instance_id=px4-393679cc154db9cb
```

一次尝试在 UAV1 OFFBOARD 确认前超时，未 arm。诊断重试期间两机 raw-local
setpoint 实测约 20 Hz；mission events 进一步证明：

```text
uav1 OFFBOARD confirmed
uav2 OFFBOARD confirmed
uav1 armed=true confirmed
uav2 armed=true confirmed
```

但 UAV1 在 8 秒 takeoff 验证窗口内始终没有升高：

```text
takeoff altitude >= 0.70m not confirmed
last_altitude_m=-0.106
watchdog: armed=true, mode=OFFBOARD, decision=continue, reason=ok
```

失败后 runner 请求安全 landing；最终飞行进程、setpoint bridge 和 watchdog 均退出。
这份证据说明问题不是“CLI 未授权 arm”或“setpoint topic 完全无流量”，但尚不足以区分
PX4 actuator output、CopterSim 执行/暂停状态或当前长生命周期实例的运行时异常。不得
据此翻转 z、修改坐标系或调整 protected mission。

## 4. 标准 stop 结果

用户要求结束开发后执行：

```powershell
.\sim.ps1 stop -Execute
```

外层工具在 120 秒超时，但 manifest stop 子进程继续并自然结束。最终只读状态：

```text
owned_and_alive=0
unknown_suspicious=0
ports 14600/14601/14610/14611/11311 = free
roscore_alive=false
mavros_uav1_connected=false
mavros_uav2_connected=false
```

残留：

```text
owned_orphan: wsl:rviz_session, PGID 9329
manifest stop.clean=false
failure: owned PGID 9329 (wsl:rviz_session) still has 1 process(es) after stop
```

实际 PGID leader 与子进程仍包括 roslaunch、双 RViz 和双 adapter。这是
[`2026-08-11-wsl-pgid-stop-ineffective.md`](2026-08-11-wsl-pgid-stop-ineffective.md)
已知缺陷在新 RViz role 上的再次复现。本轮没有使用 `pkill`、`taskkill`、
`wsl --shutdown` 或自动 force retry。

## 5. Validation

PASS：

- `tests/rviz_project_contract_check.py`
- `tests/rviz_frame_adapter_check.py`
- `bash -n scripts/wsl/rviz_live.sh`
- RViz launcher dry-run
- `scripts/validate_lifecycle.ps1`
- `scripts/validate_stage7.ps1`
- `scripts/validate_stage8.ps1`
- `tests/docs_link_check.py`

`scripts/validate_repository.ps1` 的外层工具在 180 秒超时；子进程已推进到
`sim_cli_check.py` 并随后自然退出，但本轮没有得到完整 validator 的最终 exit code。
因此不得写 repository validation PASS。

## 6. 下一步

1. 在任何 fresh start 前，按 Yellow Zone 处理 RViz PGID 9329 残留；未经明确方案不得
   直接 force kill 或把 manifest 改写为 clean。
2. 修复/验证 WSL PGID stop 对 `wsl:rviz_session` 的行为，覆盖 roslaunch 子进程。
3. 获得真正 clean 后，先 RViz OFF fresh no-arm，再做双机起飞/hover；若仍无升力，
   记录 PX4 actuator output 与 CopterSim input/运行状态，再决定责任层。
4. 只有起飞/hover 通过后才恢复原路线 full regression 和 RViz ON 性能验收。
