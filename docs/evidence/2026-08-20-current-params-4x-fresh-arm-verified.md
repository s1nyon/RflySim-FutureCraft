# Current-Parameter 4x Fresh Arm Verification（2026-08-20）

> 状态：**VERIFIED（4/4 fresh-instance full arm flight PASS）**
> HEAD：`269ba99`（工作区另有未提交的 8/20 参数/飞行计划改动）
> 目标：验证当前工作区未提交参数在干净的 fresh-instance、背靠背飞行链下是否稳定。

## 1. 结论

在以下严格操作纪律下，当前未提交参数连续 **4 次**完成双机 simulation-only arm
飞行，全部 `success=true`：

1. 上一栈 `stop -Execute` 收尾为 `clean=true`；
2. `start -Execute` 创建全新 stack；
3. FAST-LIO 产生 run-scoped readiness 后，若超过 120s 就重新采样同一 run；
4. 立即启动 EGO-Swarm；
5. 立即执行
   `scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`。

结论：今天的间歇性飞行失败更符合旧栈复用/未背靠背/定位偶发抖动，而不是当前参数
本身导致确定性失败。当前参数没有观察到 PBL-1 级回归。

## 2. 四次结果

| 次 | stack | run | simulation_instance | duration | success | collision | offboard_loss | timeout | min_distance |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `stack-20260820T144126Z-3b5cccf2` | `stage7-20260820T144224Z-15480` | `px4-1fa1e3bfbf9ff351` | 50.5s | true | 0 | 0 | 0 | 0.85m |
| 2 | `stack-20260820T150326Z-0605d620` | `stage7-20260820T150425Z-28031` | `px4-63e31111dd6e5e28` | 50.5s | true | 0 | 0 | 0 | 0.85m |
| 3 | `stack-20260820T151342Z-576d7a7d` | `stage7-20260820T151440Z-7108` | `px4-8fa735d7f3761128` | 50.5s | true | 0 | 0 | 0 | 0.85m |
| 4 | `stack-20260820T152416Z-b8d9f1e3` | `stage7-20260820T152514Z-19649` | `px4-7ab2bada0b4e8bfa` | 50.5s | true | 0 | 0 | 0 | 0.85m |

每轮 `flight_report.json` 的 `offboard/arming/takeoff/navigation/landing` 五项均为
`true`，`executor.exit_code=0`，`phase=complete`。

## 3. Watchdog 汇总

| 次 | uav1 max_speed | uav2 max_speed | 首次 land 位置 |
|---|---|---|---|
| 1 | 0.829 m/s | 0.814 m/s | 终点 AUTO.LAND 阶段 |
| 2 | 0.824 m/s | 1.044 m/s | 终点 AUTO.LAND 阶段 |
| 3 | 0.809 m/s | 1.004 m/s | 终点 AUTO.LAND 阶段 |
| 4 | 0.859 m/s | 1.222 m/s | 终点 AUTO.LAND 阶段 |

四轮均未复现 2026-08-20 21:07 run 的飞行中 `max_speed` 触发和 odom 发散。

## 4. 关键证据

- `logs/stage7_live/stage7-20260820T144224Z-15480/flight_report.json`
- `logs/stage7_live/stage7-20260820T150425Z-28031/flight_report.json`
- `logs/stage7_live/stage7-20260820T151440Z-7108/flight_report.json`
- `logs/stage7_live/stage7-20260820T152514Z-19649/flight_report.json`

对应 `score_summary.json`、`mission_events.jsonl`、`*_watchdog_events.jsonl`
均保留在同目录。

## 5. Remaining Risk

- 四次通过不能排除长尾偶发定位发散；如需更高置信度可继续增加 fresh 样本。
- 本次验证未提交任何代码；当前 8/20 工作区改动仍未 commit，需要 review diff 后决定。
- 观测到 `scripts/run_stage7_topic_probe.bat` 的 `--report '$STAGE7_RUN_DIR/...'`
  在 WSL 单引号内不会展开，会生成字面量 `$STAGE7_RUN_DIR` 目录；这是独立的小 bug，
  不在本次飞行验证范围内。

## 6. Next Recommended Step

若接受当前参数，先 review 工作区 diff，再创建本地 commit；若需要更高置信度，按同
流程继续第 5 次 fresh-instance arm 验证。
