# PBL-1 Full-Stack Regression Closure（2026-08-08）

> 状态：**CLOSED（3/3 fresh-instance 完整飞行 PASS）**
> HEAD：`2072fc3`（lifecycle P0 修复后，本轮未改飞行代码）
> 目标：证明 lifecycle 大修没有破坏 FAST-LIO → EGO → OFFBOARD → 双机穿隧道能力

## 1. 结论

- **LIFECYCLE FROZEN**：3 轮回归全部由当前 lifecycle（双 CopterSim 实例化、拓扑
  health gate、spawn_attested PX4、安全 stop）承载，未发现 lifecycle 层缺陷，冻结。
- **PBL-1 REGRESSION CLOSED**：3 次连续 fresh-instance 完整飞行全部 success。
- 本轮未修改任何飞行/planner/EGO/视觉代码；仅使用临时编排脚本（未入库）与
  `STAGE7_READINESS_TOPIC_TIMEOUT_SEC=45` 运行旋钮（handbook 记载的冷启动口径）。

## 2. 每轮结果（全部 fresh-instance，clean → start → READY → 飞行 → stop → clean）

| Cycle | stack | CopterSim u1/u2 | PX4 u1/u2 | flight run | 导航确认 | 结果 | stop |
|---|---|---|---|---|---|---|---|
| 1 | ddc342bf | 34616/29012 | 215/417 | 134030Z-2746 | 14/14 (7+7) | success 41.5s | clean |
| 2 | 7605f5f6 | 42412/40128 | 215/417 | 135056Z-2746 | 14/14 (7+7) | success 41.5s | clean |
| 3 | 8650ecb8 | 41340/32368 | 215/417 | 142654Z-2746 | 14/14 (7+7) | success 41.5s | clean |

每轮 score：`success=true, offboard_loss_count=0, collision_count=0, timeout_count=0,
min_uav_distance_m=0.85`；OFFBOARD/arming/takeoff/landing 双机确认；UAV2
`planner_commands` 正常（末段 673/407 等，未出现 EGO REPLAN/EXEC 但 pos_cmd 为 0
的偶发）。

## 3. 回归过程中观察到的 T3 传感器层故障（非 lifecycle）

在旧栈 0266cde0 上反复原地重试后，以及其后的 8b78e4aa、ab2fb4ab 栈，连续出现
UAV2 传感器消息超时（topic 依次为 odom / imu / lidar），fastlio readiness 失败：

- run `stage7-20260808T131938Z-11759`：uav2 odom relay 60s 无 publisher。
- run `stage7-20260808T140108Z-2745` / `140636Z-5165` / `141613Z-2745`：uav2
  odom/imu/lidar 消息在采样窗口内无输出（bridge 曾收到 IMU，relay 曾 advertising）。

证据：fastlio_dual.log、各 run 的 uav1/uav2_sensor_bridge.log、sensor_readiness.json
均已保留在 `logs/stage7_live/`。

**分类与根因假设**：属 localization/传感器层（T3），与 lifecycle 无关（同代码在
Cycles 1/2 首试即过）。最可能：在同一个运行中的 CopterSim 上反复启停
VisionCaptureApi 传感器桥（无法干净释放捕获）导致 UAV2 流退化；**彻底清理（含
stop 当前栈、清 WSL 残留、按顺序重启 fresh 栈）后恢复正常**——用户"清干净再按
顺序启动"的判断正确，最终 Cycle 3 fresh 栈首试即过（readiness 30s）。

**not yet tested / remaining suspicion**：是否还有更底层的 UAV2 传感器长期退化因素
（渲染负载等）未 100% 排除；但当前流程（失败→完整清理→fresh 栈）可稳定恢复。

## 4. 操作要点（供后续复用）

- 一次完整飞行 = fresh stack → `fastlio`（readiness）→ 立即 `ego` → 立即 `flight`，
  三者需在 readiness 120s 新鲜窗口内背靠背（本轮回合用手写临时编排脚本
  `.tmp_pbl1_cycle.sh`，未入库；如后续常态化可考虑入库为正式脚本）。
- 冷启动 readiness 偶发消息超时可用 `STAGE7_READINESS_TOPIC_TIMEOUT_SEC=45` 旋钮
  （handbook 已记载），但**根因恢复靠完整清理 + fresh 实例**，不是靠放宽超时。
- 飞行链清理：`.tmp_pbl1_cleanup.sh` 按显式 pgrep+pid 清理
  sensor_bridge/fastlio/ego/traj_server/waypoint/slam 等进程（无 pkill/名称扫杀）。

## 5. 决策

- **LIFECYCLE FROZEN**（无 lifecycle 层回归证据，冻结候选转为冻结）。
- **PBL-1 REGRESSION CLOSED**。
- 下一阶段：**M2-A**（waypoint baseline 运动指标），本轮不实现。
