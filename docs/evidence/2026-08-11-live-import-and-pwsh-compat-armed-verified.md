# Live Import / PowerShell Compatibility — Armed Live Verification（2026-08-11）

> 状态：**VERIFIED（fresh-instance armed live 飞行 PASS）**
> HEAD：`5d4eaef`（修复后），基线参照 `49014cd`（计划提交）

## 1. 目的

仓库结构迁移（`external/` → `third_party/`、workspace 标准化的同时）后恢复
`dev` live 链，并完成一次受明确授权的 simulation-only armed 飞行，验证两个边界
缺陷的修复：

1. `rflysim_pointcloud_adapter.py` 在 Catkin `devel/lib` relay 下无法 import
   兄弟模块 `rflysim_cloud_contract`（模块解析被 relay 目录遮蔽）。
2. 根 CLI 在 Windows PowerShell 5.1 / PowerShell 7 下解析 schema-v2 manifest 的
   `schema_version` 整数类型不一致（`Int32` vs `Int64`）导致 `malformed`。

## 2. 离线验证（全部 PASS）

- `tests/sim_cli_check.py --project-root .`
- `tests/stage7_cloud_contract_check.py --module .../rflysim_cloud_contract.py`
- `scripts/validate_lifecycle.ps1`
- `scripts/validate_stage6c.ps1` / `validate_stage6d.ps1` / `validate_stage7.ps1` /
  `validate_stage8.ps1`
- `scripts/validate_repository.ps1`

注意：`validate_stage7.ps1` 依赖 CWD 为项目根目录（`stage7_sensor_bridge_import_check.py`
使用相对路径 `config/rflysim_sensor_uav2.json`），须从项目根执行。

## 3. Fresh-instance armed live 飞行

| 项 | 值 |
|---|---|
| stack | `stack-20260810T183443Z-e43eec5e` |
| run | `stage7-20260810T183541Z-30373` |
| simulation instance | `px4-23cbdc754ee43a76` |
| 健康门 | GUI / ROSCORE / MAVROS uav1 / MAVROS uav2 / COURSE 全部 ready |
| sensor readiness | `ready=true`，identity/schema/freshness/isolation/stationary_stability 全 pass |
| 飞行链 | FAST-LIO 双机 → EGO-Swarm 双机 → `run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only` |

执行结果（`mission_events.jsonl` / `score_summary.json`）：

- 双机 `OFFBOARD` 确认（seq5/6，各 ~0.5s 内确认）
- 双机 arming 确认（seq7/8）
- 起飞确认：uav1 0.875 m / uav2 0.995 m（目标 1.0 m）
- 穿隧道导航 14/14 段确认（uav1 7 段 + uav2 7 段），`planner_commands` 正常
- 降落确认：uav1 0.204 m / uav2 0.220 m
- `score: success=true, duration_s=41.5, offboard_loss_count=0, collision_count=0, timeout_count=0, min_uav_distance_m=0.85`

与 PBL-1 基线（2026-08-08，3× fresh-instance）签名一致。

## 4. 结论

- 两个边界缺陷的修复在离线与 live 两个层面均被验证。
- 迁移后 `dev` live 链（fastlio → readiness → ego → armed flight → clean stop）恢复。
- 已知剩余缺陷：`stack_stop.py` 对 WSL 进程组 `kill -- -PGID` 两次均无效
  （返回 0 但进程组存活），stop 报 NOT clean，需按显式 PID 补清；待 Yellow Zone 修复，
  见 `../incidents/2026-08-11-wsl-pgid-stop-ineffective.md`。

## 5. 复现/操作要点

- 失败后必须「完整清理 → fresh 栈 → fastlio → readiness → ego → flight」背靠背
  （readiness 120s 新鲜窗内），不要在同一旧栈上反复重试。
- 旧栈重试时 setpoint bridge（keepalive）可能已随上一轮 flight runner 的 EXIT trap
  退出，导致 OFFBOARD 转换时 PX4 无 setpoint 流而拒绝/回退 MANUAL，
  见 `../incidents/2026-08-11-offboard-stale-retry-setpoint-stream.md`。
