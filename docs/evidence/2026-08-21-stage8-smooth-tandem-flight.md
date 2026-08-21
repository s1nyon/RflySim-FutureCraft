# Stage 8 静态隧道双机连续丝滑穿越 — 实现与离线验证（2026-08-21）

> 状态：**OFFLINE IMPLEMENTED + VALIDATED；LIVE 待授权后复验**
> HEAD：`b7c9a19`
> 范围：仅优化 `predicted_narrow_course_v1` 静态隧道中的双机连续穿越；未改 EGO/PX4/FAST-LIO/lifecycle。

## 1. 结论

本轮完成了“checkpoint 与 planner target 解耦”的连续隧道 guidance，并修掉了
duplicate planner goal publish。离线契约、Stage 7/8 验证与 dry-run 全部通过。
Live fresh-instance 复验尚未执行：需要用户在 AGENTS.md Red-Zone 明确授权，且当前
inspect 因 2 个 stale CopterSim PID 复用而 fail-closed（见第 6 节）。

## 2. 当前机械逐点飞的根因证据（代码级，非推测）

- `mission_executor.py::_publish_planner_goal()` 对每个 logical goal 新建
  `rospy.Publisher` 并连续 publish `max(3, min(10, timeout_s*10))` 次；
  `timeout_s=5` 时为 **10 次**。EGO `waypointCallback()` 每收一条
  `PoseStamped` 即调用 `planNextWaypoint()`，`EXEC_TRAJ` 下进入
  `REPLAN_TRAJ`。→ 一个 logical goal ≈ 10 次 replan（goal storm）。
- EGO `planNextWaypoint()` 设置 `end_vel_.setZero()`，global traj 以零速度终止
  于 target。旧 Stage 8 把同一个点同时作为 publish target 与 verify checkpoint，
  因此每个 waypoint 都被当终点减速。→ “机械逐点飞”主因。
- 旧双机调度是 index 落后 1 个 waypoint（约 2.0 m 物理距离且随弯道变化），不是
  arc-length s 差。

## 3. 采用机制

- **checkpoint**：进度门（fly-through），只用于判断“已经走到哪里，可推进前方目标”。
- **look-ahead target**：真正发给 EGO 的点，始终位于 checkpoint 前方；曲率感知：
  直线 2.2 m、弯道 1.0 m、入/出弯前 0.9 m 线性 ramp。
- **arc-length s**：`course_guidance.py` 提供 `point_at_s / segment_at_s /
  width_at_s / curvature_at_s / lookahead_s` 与 fly-through gate 生成。
- **tandem**：UAV2 follower gate = 最接近 `leader_s - 1.5 m` 的前方 gate，单调
  推进；不再用 index 差。
- **single publish**：planner goal publisher 按 topic 缓存复用，一个 logical goal
  只发一条 `PoseStamped`。

## 4. Changed

- 新增 `future_aircraft_ws/src/multi_uav_mission/scripts/course_guidance.py`
- 新增 `future_aircraft_ws/src/multi_uav_mission/scripts/stage8_guidance_report.py`
- 修改 `stage7_flight_plan.py`：course 分支改为 rolling look-ahead + fly-through +
  s-gap tandem；Stage 7（course=None）行为不变。
- 修改 `mission_executor.py`：planner goal 单次发布 + publisher 缓存；导航确认事件
  记录 handoff speed。
- 修改测试：新增 `stage8_course_guidance_check.py`；重写
  `stage8_course_flight_plan_check.py`；更新 `stage7_goal_delivery_check.py`；
  更新 `stage7_flight_artifact_check.py` / `stage7_planner_control_bridge_check.py`
  的模块加载（stage7_flight_plan 现依赖同目录 course_guidance）。
- 修改 `validate_stage8.ps1`：加入 course guidance 契约检查。

## 5. Validation（离线）

```text
python tests/stage8_course_guidance_check.py ...          -> PASS
python tests/stage8_course_flight_plan_check.py ...      -> PASS
python tests/stage7_goal_delivery_check.py ...           -> PASS (1 logical = 1 publish)
python tests/stage7_persistent_navigation_subscriber_check.py -> PASS
powershell scripts/validate_stage8.ps1                   -> Stage 7 + Stage 8 PASS
python tests/script_inventory_check.py --project-root .  -> 96 scripts PASS
python tests/docs_link_check.py --project-root .         -> PASS
```

Dry-run 关键静态指标（`stage8_guidance_report.py`）：

```text
leader flythrough gates = 21
follower flythrough gates = 17
leader checkpoint spacing min/max = 0.5 / 0.8 m
follower checkpoint spacing min/max = 0.5 / 1.0 m
turn lookahead = 1.0 m（恒定）
straight lookahead max = 2.2 m
tandem min s-gap = 1.5 m
nominal centreline wall clearance = 0.475 m（几何估计，> 0.15 m 目标）
```

## 6. 定量对比（plan-level；live 指标待授权后补）

| 指标 | 旧方案 | 本轮方案 |
|---|---|---|
| 每个 logical goal 的 ROS PoseStamped 发布 | 10 次 | 1 次 |
| 中间“终点式” waypoint（target==checkpoint） | 全部（仅末点 terminal） | 0（仅 landing platform terminal） |
| 中间 checkpoint spacing | 约 2.0 m | 0.5–0.8 m |
| 双机间距语义 | index 差 1（≈2.0 m，随弯变化） | arc-length s 差 1.5 m |
| 总 logical goal | 20 | 40 |
| 总 ROS goal message | 约 200 | 40（约 5× 下降） |
| traverse time / mean speed / stop episodes / wall clearance / min UAV distance | 无本轮 live 样本 | **待 live 复验** |

## 7. Live 验证状态：BLOCKED（需要用户授权）

`sim.ps1 status` 显示 `no active stack`；WSL `RflySim-20.04` 为 Stopped。执行
fresh-instance live run 属于 AGENTS.md Red-Zone（`fresh-instance -Execute`、
`live_stack_stop.ps1 -Execute`、首次真实 live lifecycle 验证），且当前
`live_stack_fresh_instance.ps1 -DryRun` 的 inspect **fail-closed**：发现 2 个
`stale_pid_reuse` CopterSim 记录（PID 2688 / 15252），按规则只报告、不自动 kill。

未在本轮执行任何 live arm / stop / fresh-instance / 进程扫杀。恢复后最小动作：

```powershell
scripts\live_stack_fresh_instance.ps1 -DryRun        # 确认 stale 已清、无 unknown
scripts\live_stack_start.ps1 -Execute                # 需用户明确授权
scripts\run_live_fastlio_dual.bat
scripts\run_live_ego_swarm_dual.bat
scripts\run_stage7_topic_probe.bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

## 8. 九个问题的回答

1. **机械逐点飞主因**：target 与 checkpoint 是同一个点，EGO global traj 以
   `end_vel=0` 终止于每个 waypoint；叠加每 logical goal 10 次 PoseStamped 触发的
   replan storm。
2. **duplicate planner goal 是否造成额外 replan**：是。每个 logical goal 发布
   10 次，EGO 每次 `waypointCallback` 都 `planNextWaypoint`/`REPLAN_TRAJ`。
3. **连续飞行机制**：checkpoint 只做进度门，target 是曲率感知的滚动前视点；飞机
   在仍有速度时提前拿到更远 target，EGO 从当前 position/velocity/acceleration
   连续 replan（`planFromCurrentTraj`）。
4. **为何不停车**：飞机不会追到 checkpoint 才停，它一直追 checkpoint 前方的
   target；在 checkpoint 处只触发下一次 target 推进，速度不归零。
5. **两个 90° 弯如何防 cut corner**：弯道 look-ahead 收缩到 1.0 m（小于 1.41 m
   arc 长），入弯前 0.9 m 内 2.2→1.0 线性 ramp，target 落在弧上/弧内而不跨过整个
   弯；EGO occupancy 仍是最终防线。
6. **UAV2 如何保持在 UAV1 后方**：follower gate = `leader_s - 1.5 m` 的 arc-length
   gate，且 follower target 不超过同 phase leader target。
7. **推荐参数**：`max_vel=0.45 / max_acc=0.55 / max_jerk=2.0`；straight lookahead
   2.2、turn lookahead 1.0、ramp 0.9；straight/turn checkpoint 0.8/0.5；follower
   gap 1.5 m。
8. **0.50/0.55 是否保留**：第一阶段尚未在 live 证明 0.45 的 smoothness 改善前，
   保持 0.45；不得用提速掩盖调度问题。
9. **距真正的连续 corridor guidance 还差什么**：当前仍是事件驱动的静态
   checkpoint 序列（约 0.5–0.8 m 推进一次），不是基于实时 odom 的闭环 corridor
   projection / 连续 Frenet 控制；也未接入实时 gap 控制与在线 speed 自适应。

## 9. Remaining Risk

- 未做 live：目标/弯道/双机间距在真实 PX4/EGO 下的实际速度凹陷、wall clearance
  与 stop episode 尚未测。
- 静态交错调度下 leader 在 follower 落后时仍可能逐渐吃掉自身 look-ahead（次级
  等待），需 live 观察。
- `validate_repository.ps1` 的 `log_cleanup_check.py` 失败（DryRun 打印
  “remove”被判定为实际删除）；与本轮文件无关，未修改。

## 10. Next Recommended Step

用户回来后授权 fresh-instance，先做 **UAV1 单机** 完整隧道（确认无 cut corner /
无停车 / 无 goal storm），再双机 tandem，最终 3 次 fresh-instance 双机 live PASS
后按 `docs/evidence/2026-08-21-stage8-smooth-tandem-flight.md` 补 live 指标。
