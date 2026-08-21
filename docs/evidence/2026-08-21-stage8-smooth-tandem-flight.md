# Stage 8 静态隧道双机连续丝滑穿越 — 实现与离线验证（2026-08-21）

> 状态：**Stage 8 双机静态隧道 baseline 可冻结**。UAV2 飞出地图已关闭；
> 出口提前横切（Case B）已修复并 **live 验证通过**；环境“卡地板/lidar 缺失”
> 已定位为 arena_floor 碰撞板与 CopterSim 生成平面重叠，修复后 live 恢复。
> HEAD：`9025aab`
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

## 11. Live 验证尝试（2026-08-21 第二轮，用户已授权 simulation-only Red-Zone）

### 11.1 stale PID 处理（完成）

- 读取出旧 manifest（`stack-20260820T152416Z-b8d9f1e3`）2 个 `stale_pid_reuse`：
  PID 2688 现在是 `svchost.exe`（netprofm，10:28 启动），PID 15252 现在是
  `uhssvc.exe`（Update Health Tools，10:30 启动），与 8/20 CopterSim 记录
  （start-time/cmdline）完全不匹配 → 只退役 stale metadata，未触碰这两个系统进程。
- 备份 `stack_manifest.json.bak-20260821` 后用 lifecycle 自带分类逻辑移除 2 条 stale
  记录；旧栈 `live_stack_stop.ps1 -Execute` 收尾 `clean=true`。

### 11.2 fresh start 尝试（INFRA-INVALID）

- 新栈 `stack-20260821T045707Z-bb330115`：GUI_READY / ROSCORE_READY / COURSE_READY
  = READY，但 MAVROS_UAV1/UAV2 持续 NOT_READY（300s），健康门 fail-closed。
- 取证：SITL wrapper（`%TEMP%\future_aircraft_stage2_uavsitl.bat`）trace 停在
  `rfly3d done` 后；子进程树显示 `choice.exe /t 3 /d y /n` 永久挂起；CopterSim 与
  PX4 SITL 从未启动；`px4_mavlink_1.log` 报 `PX4 daemon not running yet`；
  stage2 因此未走到 MAVROS，WSL 会话随后结束。
- 隔离复现：本会话中 `Start-Process cmd -ArgumentList '/c','choice /t 3 /d y /n >nul ...'`
  在新控制台 8s 不返回；同一 shell 管道内 `choice /t 2` 21ms 返回；
  `timeout /t 2 /nobreak` 在新控制台约 2s 正常完成；`WScript.Shell.AppActivate`
  返回 False → 当前 agent 会话无法交互桌面控制台。
- 结论：canonical SITL wrapper 的 `choice /T` 依赖交互控制台，在本环境必然挂起；
  这是环境/console 限制，不是 guidance 代码回归（本轮 3 个 commit 未触碰启动链）。

### 11.3 恢复 clean（完成）

- 挂起栈 `live_stack_stop.ps1 -Execute`：`clean=true`，owned 进程全部退出
  （RflySim3D 需 TERM，原因已记录），scheduled task 删除。
- `sim.ps1 status` = `no active stack`；inspect `fail_closed=false`，
  `stale=0 unknown=0 ports_unknown=0`。

### 11.4 解除阻塞的两个选项

1. 在可交互桌面会话中运行 canonical start（`live_stack_start.ps1 -Execute` 或
   `live_stack_fresh_instance.ps1 -Execute`），让 SITL wrapper 的 `choice` 正常走完；
2. 或由用户授权一个 **安全中性** 的最小 wrapper 兼容修改：
   `generate_sitl_wrapper.ps1` 将 `choice /t N /d y /n` 替换为
   `timeout /t N /nobreak`（已证明在本环境新控制台可用；不改任何 safety gate、
   ownership、fail-closed 逻辑）。此修改当前**未执行**，等待用户明确授权。

### 11.5 本轮未做

- 未 arm、未起飞、未调 guidance 参数（0.45/0.50/0.55 均未在 live 验证）。
- 未修改 lifecycle / launcher / 28com 参考工程。

## 12. Live 验证结果（2026-08-21 下午，多轮 fresh-instance）

### 12.1 wrapper console 阻塞修复

`279531b` 将生成的 SITL wrapper 中 `choice /T` 替换为 `timeout /T /nobreak`
后，canonical fresh stack 可以正常启动（health + dual topology ready）。

### 12.2 Run A（commit `4756bae`：course_s progress verify + leader-first 顺序，
follower verify 仍阻塞）

- **双机 mission SUCCESS**（80.5s；collision/offboard/timeout = 0；
  navigation/landing 双机均 true）。
- 无 goal storm：uav1 logical=22 observed=22，uav2 logical=18 observed=18。
- Tandem：overlap 35.98s；min gap_s 1.548m（≈1.5 目标）；median gap_s 2.154m；
  min physical distance 1.553m（≥0.8/0.9 ✓）。
- **不达标**：uav1 mid-course stops=3（s≈5.39 停 5.5s、s≈6.03 停 1.3s、
  s≈8.87 停 1.2s）；uav2 stops=1；min wall clearance uav1=0.015m、
  uav2=0.039m（<0.10 硬门槛；两机在 arc1/arc2 切内角，max cross-track≈0.46m）。
- 原因：follower 进入隧道前的 verify（约 8–10s）阻塞 leader 下一 target 发布；
  leader 吃光 look-ahead 后在弧内停车；turn lookahead 1.0m 让 target 跨弯导致切角。

### 12.3 Run B / Run C（commit `de1a42a`：follower verify 改为 2s 非阻塞 pending；
turn lookahead 1.0→0.9）

- Run B：uav1 全程正常；uav2 起飞后在原点悬停约 25s，随后慢速爬行并发生
  odom/mode loss → **INFRA-INVALID**。
- Run C（fresh）：uav1 **完美**（22/22 navigation confirmed 含 terminal）；
  uav2 **仅 1/17 confirmed、16 次 navigation_pending**，实际没有进入隧道推进；
  最终 terminal verify 失败：`last_distance=60.159m planner_commands=133`，
  score `success=false / missing_mission_end`。用户现场观察：uav2 跟随距离
  过远并飞出地图。
- **根因**：non-blocking follower verify 移除了 follower 的 progress gate；
  follower 的 target 按 leader 节奏每 ~2s 前进，与 uav2 真实进度无关。uav2
  落后时其 look-ahead 目标持续跑远，EGO 最终朝 60m 外的目标规划 → 出图。
- **结论**：follower 的 checkpoint 必须继续作为硬 progress gate（阻塞），
  不能用 2s pending 语义解耦；已回退该改动。

### 12.4 当前 HEAD（回退后）保留的修复

- `course_s` along-track progress verify（leader/follower 均可，late verify
  仍能在通过后立即确认）。
- leader-first 顺序：leader 在自身 verify 后、follower verify 前先拿到下一
  look-ahead target。
- turn lookahead 0.9m（防切角方向，尚未在健康双机 run 中单独验证）。
- 1 logical goal = 1 ROS publish（live 证实，uav1/uav2 counts 与 logical 完全一致）。

### 12.5 仍 OPEN 的问题（后续最小实验，一次一类）

1. **leader 在 follower 进入期停车**：follower 进隧道 verify 约 8–10s，
   阻塞了 leader 下一 target；建议在保持 follower verify 阻塞的前提下，
   让 leader 的 look-ahead runway ≥ follower 最坏 verify 时长 × 巡航速度
   （例如 straight lookahead 2.4 + straight checkpoint 0.9，或 leader 在
   follower verify 前多发一个 gate 的 target）。
2. **弯道切内角 / wall clearance 0.015m**：建议 turn checkpoint 0.5→0.4
   （保持 turn lookahead 0.9），单变量验证。
3. uav2 偶发起飞后悬停/慢速（Run B）按基础设施处理，fresh 重试前先确认
   uav2 EGO/FAST-LIO odom 与 pos_cmd 健康。

### 12.6 本轮 live 过程记录

- 每个 fresh 周期都遇到已知 WSL PGID stop 缺陷（`kill -- -PGID` 无效），
  通过 manifest 校验后按显式 PID 补清并再次 `live_stack_stop` 至 `clean=true`。
- 最终栈 `stack-20260821T064346Z-bea0584f` 已按用户要求停机，`clean=true`；
  `sim.ps1 status` = `no active stack`。
- 所有记录/日志保留在
  `logs/stage7_live/stage7-20260821T061301Z-5311`（Run A）与
  `logs/stage7_live/stage7-20260821T064449Z-4953`（Run C）。

## 13. UAV2 pre-entry staging（commit `7a5ea52`）— 2× fresh dual SUCCESS

### 13.1 改动

- 双机 takeoff 后、正式 tandem traversal 前，给 UAV2 发布一次性非阻塞 staging
  target：world `(17.5, 0.4, 1.0)`（入口 `(18.5,0)` 前 1.0m、向 uav2 侧偏
  0.4m，处于开放 approach 区，不与 UAV1 入口轨迹重合）。
- staging 只有 publish、没有 verify，UAV1 完全不被阻塞。
- 正式 follower 目标与 verify 保持 hard blocking progress gate；未恢复任何
  non-blocking pending。
- 其它参数冻结：`max_vel=0.45 / max_acc=0.55 / max_jerk=2.0`、straight lookahead
  2.2、turn lookahead 0.9、gap_s 1.5；未改 turn checkpoint。

### 13.2 Run S1（fresh，`stage7-20260821T071110Z-22152`）

```text
mission: success=true 81.0s  collision=0 offboard_loss=0 timeout=0
uav1:   22/22 navigation confirmed（含 terminal）
uav2:   18/18 navigation confirmed，0 pending
goals:  uav1 logical=22 observed=22；uav2 logical=19（18+staging）observed=19
traverse time: uav1 44.94s / uav2 44.90s
min wall clearance: uav1 0.117m / uav2 0.138m
max cross-track:    uav1 0.358m / uav2 0.387m
tandem:  min distance 1.590m；median gap_s 2.636；p05 1.718；p95 3.174；
         overlap 35.91s
stops:   uav1 2（s≈6.05 1.2s、s≈9.04 0.7s）；uav2 2（同位置 1.2s/0.6s，
         均为 arc 出口短暂减速，非长时间停车）
```

### 13.3 Run S2（fresh repeat，`stage7-20260821T072342Z-4287`）

```text
mission: success=true 81.0s  collision=0 offboard_loss=0 timeout=0
uav1:   22/22 navigation confirmed
uav2:   18/18 navigation confirmed，0 pending
goals:  uav1 logical=22 observed=22；uav2 logical=19 observed=19
traverse time: uav1 44.40s / uav2 44.21s
min wall clearance: uav1 0.130m / uav2 -0.111m（几何估计）
max cross-track:    uav1 0.355m / uav2 0.636m
tandem:  min distance 1.539m；median gap_s 2.485；p05 1.844；p95 3.138；
         overlap 35.44s
stops:   uav1 2；uav2 1
```

### 13.4 结论与判断

- **follower catastrophic failure 已解决**：两轮 fresh 中 uav2 均 18/18
  confirmed、0 pending、不出图、完整穿越并 landing。
- UAV1 保持用户满意的连续飞行（22/22，仅在 arc 出口有 0.7–1.2s 短暂减速）。
- 双机同时穿隧道（overlap ≈35.5–35.9s），min physical distance 1.54–1.59m。
- Run S2 的 uav2 几何壁距低点位于 **出口直道 s≈14.5–14.9**（cross-track 最大
  0.636m），不是弯道切角；因此按证据原则**未做 turn checkpoint 0.5→0.4**。
  该问题记为剩余风险，下一迭代应针对出口/terminal 过渡（例如最后 flythrough
  target 的 clamp 位置或 terminal 发布时机）单独验证。

### 13.5 本轮 live 记录

- 两次 fresh 均为 canonical lifecycle；每轮仍遇到已知 WSL PGID stop 缺陷，按
  显式 PID 补清后 `clean=true`；最终 `sim.ps1 status` = `no active stack`。
- 记录保留在 `logs/stage7_live/stage7-20260821T071110Z-22152` 与
  `logs/stage7_live/stage7-20260821T072342Z-4287`。

## 14. UAV2 出口 clearance 异常：Case B（真实提前横切）与最小修复

### 14.1 离线诊断（Run S2，`stage7-20260821T072342Z-4287`）

对 UAV2 全部 34 个 `clearance < 0.10m` 样本逐点检查：

```text
world_x：28.83 ~ 29.09（全部 < 29.3，即尚未越过 corridor exit）
最后一段 straight 纵向位置：4.03 ~ 4.29 / 4.5（仍在墙体纵向范围内）
world_y：5.33 ~ 5.54（已明显向 platform2 y=5.9 偏移）
min clearance：-0.111m（机体边缘几何进入北墙带）
```

**结论：metric artifact 排除，是真实提前横切。** UAV2 的最后一条 tunnel
fly-through gate 在 s≈13 确认后，terminal platform2 立即发布；EGO 在飞机仍处于
最后一段墙体纵向范围内时就开始斜切向 platform2。

### 14.2 最小修复（commit `c013ca1`）

- UAV2 在 terminal platform2 发布前增加**出口 fly-through progress gate**
  （blocking verify，`checkpoint_s = total_length`，`exit_gate=True`），确认
  越过 corridor exit 后才发布 platform2。
- UAV1 terminal 顺序与行为完全不变；UAV2 staging、follower blocking progress
  verify、gap 1.5m、0.45/0.55/2.0 与 lookahead 2.2/0.9 全部冻结。
- 不修改 turn checkpoint（异常位置在出口直道，不在弯道）。

### 14.3 离线验证

```text
stage8 course flight plan: PASS（含 exit gate 顺序契约）
validate_stage8.ps1：Stage 7 + Stage 8 全 PASS
```

### 14.4 Live 复验：INFRA-INVALID（环境 lidar 未发布）

- 两次 fresh 实例均在 readiness 前失败：CopterSim 的 Mid360 lidar 点云未发布
  （sensor bridge 只有 IMU 消息），FAST-LIO 无输入、readiness 超时后 roslaunch
  退出；MAVROS/PX4 正常。
- 失败发生在任何 mission/planner 参与之前，与 `c013ca1` 无关；今天早前同一链路
  曾连续 5+ 次成功，判定为当前环境传感器/仿真器状态退化。
- 已按 canonical lifecycle 停机，两次均 `clean=true`。

### 14.5 Current Truth

- UAV2 飞出地图问题：**已关闭**（staging + blocking follower verify）。
- 出口提前横切：**根因已确认（Case B）并已修复（`c013ca1`），离线验证通过**；
  live 复验已于 Run S3 通过（见 §15）。
- 静态双机隧道 baseline 冻结：Run S3 通过后正式冻结。

## 15. Run S3：出口修复 + 地板修复 live 验证（fresh 通过）

### 15.1 环境问题：飞机卡地板 / lidar 缺失（已修复，`9025aab`）

- 现象：多轮 fresh 在 readiness 前失败（lidar 无点云 → FAST-LIO 无输入）；
  用户现场确认 UAV1 卡在地板里。原因是 course 部署的 `arena_floor` 碰撞薄板
  位于 z=0（顶面 +0.025），与 CopterSim 在 z=0 的生成体相交。
- 修复：`arena_floor` 中心下移至 z=-0.10（顶面 -0.075），生成点位于地板上方；
  `tests/stage8_course_geometry_check.py` 同步更新。
- 修复后 fresh 启动：FAST-LIO readiness PASS（lidar 正常）。

### 15.2 Run S3（fresh，`stage7-20260821T084406Z-2769`，
stack `a2f503da`，commit `c013ca1` + `9025aab`）

```text
mission: success=true 82.0s  collision=0 offboard_loss=0 timeout=0
uav1:    22/22 navigation confirmed（含 terminal）
uav2:    17 flythrough + 1 exit gate + 1 terminal = 19/19 confirmed，0 pending
goals:   uav1 logical=22 observed=22；uav2 logical=19（staging+17+terminal）observed=19
traverse time: uav1 42.53s / uav2 42.17s
min wall clearance: uav1 0.133m / uav2 0.135m（均 > 0.10 ✓）
max cross-track:    uav1 0.373m / uav2 0.357m（Run S2 为 0.636m）
tandem:  min physical distance 2.0m；min gap_s 2.116；median gap_s 2.73；
         overlap 33.47s
stops:   uav1 1（s≈5.63，1.0s，arc1 出口）；uav2 1（s≈14.66，0.6s，出口前）
```

### 15.3 出口段专项（uav2，s>13.5）

```text
min valid in-corridor wall clearance: 0.316m
max cross-track while inside corridor: 0.209m
negative clearance samples inside corridor: 0
terminal platform2 goal world: (32.0, 5.9)
exit gate 确认位置：s≈14.73（机体前缘已越过墙体终点 x=29.3）
odom 中心越过 x=29.3 比 terminal 发布晚约 2.8s（0.6s 出口短暂减速）
```

**结论：Case B 修复有效。** UAV2 不再在墙体纵向范围内向 platform2 横切；
出口段 clearance 全部为正且 >0.10m。

### 15.4 收尾

- 已按 canonical lifecycle 停机，`clean=true`；`sim.ps1 status` = `no active stack`。
- 记录保留在 `logs/stage7_live/stage7-20260821T084406Z-2769`。
