# Stage 8 双机穿隧道 live 问题记录（2026-08-02）

## 当前结论

Stage 8 双机穿隧道任务尚未通过 live 验收。最终 run `stage7-20260802T102552Z-8563` 在新仿真实例 `px4-01e125f57b8b5a69` 上通过了双机 sensor readiness 和 topic probe，但飞行阶段失败，`flight_report.json` 为 `ready=false`。

本次不能描述为“双机穿过隧道并到达降落点”。最终检查确认两机均已解除解锁：UAV1 为 `armed=false / AUTO.LAND`，UAV2 为 `armed=false / MANUAL`。

## 已确认现象

- 新 run 的 readiness 五项 gate 全部通过：`identity`、`schema`、`freshness`、`isolation`、`stationary_stability` 均为 `pass`。
- topic probe 的 `sensor_bridge`、`fast_lio`、`mavros`、`ego_swarm` 和 `flight_gate` 均为 `ready=true`。
- 飞行启动后，UAV1 曾处于 `armed=true / OFFBOARD`，高度约 `1.006 m`。
- 同一时刻 UAV2 处于 `armed=true / ALTCTL`，`/uav2/mavros/odometry/in` 的 z 约为 `11.257 m`。UAV2 飞出地图/雷达有效范围后失去定位。
- 最终 `executor.log` 报错：`planned navigation not confirmed for uav1 within 45.0s; last_distance=2.596m planner_commands=0`。
- 最终报告中的起飞、OFFBOARD、导航和降落确认项均未形成成功证据，任务整体失败。

## 本次发现并修正的前置缺陷

首次飞行尝试没有起飞，原因是两个 geofence watchdog 使用相同 ROS 节点名，后启动的节点会关闭前一个节点；同时 watchdog 会在解锁后的 MAVROS 模式消息同步瞬间把暂时非 `OFFBOARD` 直接判为降落。

当前工作区已做最小修正：

- watchdog 节点名按 UAV namespace 隔离为 `course_geofence_watchdog_uav1` 和 `course_geofence_watchdog_uav2`；
- 解锁后增加 2 秒模式同步宽限；
- 越界、超速和里程计过期仍保持立即降落；
- 聚焦 geofence 测试和完整 `scripts\validate_stage8.ps1` 离线验证通过。

该修正只解决前置竞态，不代表隧道飞行问题已经解决。

## 运行过程中的其他失败

- 一个飞行 runner 因 readiness 超过 120 秒返回 `[ERROR] stale report`，在调用 OFFBOARD/arm 前安全退出。
- 在同一 ROS master 上直接重启 FAST-LIO 会与旧 Stage 7 节点重名，导致新旧节点互相关闭，并使 `/uav1/mavros/odometry/out` 无发布者。再次刷新 readiness 前必须先精确停止旧 FAST-LIO、sensor bridge 和 EGO 节点，或重启完整仿真实例。

## 尚未确认的根因

UAV2 异常升高的直接输入来源尚未确认。下一次不要先改航线或放宽 geofence，应先记录并对齐以下数据：

1. `/uav2/planning/pos_cmd` 的实际 z 指令及时间戳；
2. `/uav2/mavros/setpoint_raw/local` 的实际发送值、坐标系和 type mask；
3. `/uav2/mavros/odometry/in`、FAST-LIO odometry 和 PX4 local position 的坐标方向；
4. UAV2 从 `OFFBOARD` 切到 `ALTCTL` 前后的 PX4 failsafe 原因；
5. 两个 watchdog 的实时输入、决策和 `AUTO.LAND` 服务返回值；
6. EGO-Swarm 为什么在 UAV1 导航验证期间出现 `planner_commands=0`。

## 开发约束（2026-08-07 补充）

位置数据离谱时不做自动返航：当无人机 xyz 位置出现非有限值或远超赛道
geofence（超出 `Geofence.unreasonable_margin_m`，默认 5 m）时，
`course_geofence_watchdog.py` 判定为 `no_autoland` / `unreasonable_position`
并**跳过 AUTO.LAND 请求**，只记录事件等待操作员处理。正确做法是修好代码后
重启仿真，而不是依赖基于脏数据的返航兜底。UAV2 出现 z≈11.257 m 这类数据时
即属此情况。

## 2026-08-07 复测：起飞被 watchdog stale-odom 打断（已修）

实例 `px4-c50420f823fe4489`（run `stage7-20260807T080522Z-2599`）上双机
OFFBOARD + arming 全部确认，但起飞失败：uav1 高度始终 -0.108 m。
watchdog 证据显示第一次 `land` 触发于
`mode=OFFBOARD armed=true odom_age=0.52s`（`max-odom-age-s=0.5` 超限），
即起飞 setpoint 刚发出时一次 0.52 s 的里程计缺口被误判为失联、立刻
AUTO.LAND。修复：flight runner 的 watchdog 阈值改为
`--max-odom-age-s 2`（2 秒无里程计仍立即降落），validate_stage7 契约强制。
后续 AUTO.LAND 期间 watchdog 反复记 `land/mode_loss`（281 次）只是状态
噪声，不影响安全。

## 2026-08-07 复测（lidar_only）：起飞通过，导航 planner_commands=0

实例 `px4-7535c751ee1c7e3f`（run `stage7-20260807T084232Z-2599`），
传感器 bridge 切换为 `--sensor-mode lidar_only` 后：

- readiness 快速通过；双机 OFFBOARD + arming + **起飞高度确认全部通过**
  （`takeoff_altitude_confirmed: uav1/uav2 = true`），stale-odom 误判不再出现；
- 导航阶段失败：`planned navigation not confirmed for uav1 within 45.0s;
  last_distance=2.601m planner_commands=0`——与 08-02 隧道问题同源：
  ego-swarm 收到 goal 后没有产生 `/planning/pos_cmd`；
- 下一轮 live 优先排查 `planner_commands=0`：goal 是否被 planner 接受、
  odom/cloud 输入是否正常、`traj_start_trigger`/方式位是否满足。

## 下次继续顺序

1. 清理旧 Stage 7 ROS 节点并启动全新双机实例。
2. 生成全新 readiness run，确认五项 gate 通过且两机未解锁。
3. 增加只读 topic 记录，先验证两机 planner/setpoint 的 z 始终在 `0..2 m` geofence 内。
4. 先执行单机或分阶段起飞，确认 UAV1、UAV2 分别能稳定保持 1 m OFFBOARD，不直接进入长航线。
5. 修复并验证 `planner_commands=0` 后，再逐段增加隧道 waypoint。
6. 任一车辆高度异常、丢失 OFFBOARD、里程计过期或失去定位时立即停止任务并降落；不得强制继续穿隧道。

## 工具进展（2026-08-07）

只读控制链取证记录器已实现并通过离线验证：

- `future_aircraft_ws/src/multi_uav_mission/scripts/stage8_control_chain_recorder.py`
  订阅完整链路
  `planning/pos_cmd -> mavros/setpoint_raw/local` 与
  `slam/odometry_raw -> mavros/odometry/out -> mavros/odometry/in ->
  mavros/local_position/odom`，外加 `mavros/state` 模式切换；
- 输出 run-scoped 的 `$STAGE7_RUN_DIR/stage8_control_chain.jsonl` 与
  `$STAGE7_RUN_DIR/stage8_control_chain_summary.json`；摘要按层统计 z 的
  min/max/越界计数与 planner 指令条数（用于定位 `planner_commands=0`）；
- 每条 JSONL 同时记录 `receive_wall_time / receive_monotonic /
  header.stamp`；setpoint 的 z 越界统计只在 `IGNORE_PZ` 未置位时计为有效指令；
- 记录器只订阅、不发布，不调用 service，不 arm；watchdog 决策与 flight
  event 记录保留现有实现，摘要只引用其文件路径；
- 入口：`scripts\run_stage8_control_chain_recorder.bat`（`--dry-run` 可离线验收）。

下次 live 时在“D435i no-arm probe → topic probe”之后启动记录器，再进入
no-arm planner 检查与单机悬停，即可回答“坏值最先在哪一层出现”。
