# Competition Course V2 — UAV1 full Section A 首次 live diagnostic（FAIL）

Date: 2026-09-02 (Asia/Shanghai)
Status: **BLOCKED_BY_CURRENT_PLANNER_BEHAVIOR（待 RCA）**
Branch: `infra/rviz-live-handoff-20260825`（工作区含两个已 live 验证的小修复，未提交）

## 1. Run 信息

- Stack: `stack-20260901T173302Z-1471abcd`
- Simulation instance: `px4-add5ccff2a57b013`
- Stage 7 readiness: `stage7-20260901T174149Z-13038`（PASS）
- Navigation run: `v2-nav-20260901T174335Z-full_section_a`
- Profile: `full_section_a`（Section A endpoint local `(7.0, 0.7, 1.0)`）
- Result: **FAIL**（`executor_error`、`mission_contract`、`watchdog_or_geofence`、`wall_clearance`、`obstacle_perception`）

## 2. 事件序列（基于 watchdog/recorder/flight events 时间对齐）

1. preflight/takeoff 正常：OFFBOARD → arm → takeoff altitude `0.936m`（t≈7s）。
2. EGO goal 发布并被接受，planner PositionCommand 共 9035 条。
3. **早期贴墙**：起飞后沿 Section A 前进，在 `s≈0.825`（local `(3.33, -0.12)`，world `(19.33, -0.82)`）
   贴近 `section_a_right` 墙，`minimum_wall_clearance_m = -0.297`。
4. 全程横向大幅摆动：local y 范围约 `[-1.18, +0.99]`，远超 corridor 安全包络。
5. 在 `local x≈6.0`（static box 区域后）悬停约 2s（t≈674-676s），随后 **突然加速**
   至 `1.5+ m/s`（EGO launch `max_vel=0.45`，实测最高 `1.542 m/s`，`speed>0.45` 样本 437/1300）。
6. 冲出 geofence：`local x > 7.5`（t≈677.7s 首次 `outside_x`），odom 冻结于
   `local (7.656, 0.547, 0.207)`，`odom_age_s` 持续增长至 57s。
7. watchdog 在 `1788284674.89` 记录 `course geofence violated; requesting AUTO.LAND`，
   PX4 进入 AUTO.LAND 后 `mode_loss`（OFFBOARD→AUTO.LAND），约 19s 后 disarm。
8. terminal settle 未确认：90s 超时（`last_distance=1.041m speed=0.750m/s settled_for=0s`），
   landing/disarm confirmation 缺失。

## 3. 责任层初步判断

- **不是** V2 plan/goal/frame 问题：short_smoke 同一栈同一链路成功（`v2-nav-20260901T173953Z-short_smoke` PASS），
  终点坐标、geofence、settle 契约均正确。
- **不是** map runtime/loader 问题：`COURSE_READY`、world-state retention 正常，实体 parity 通过。
- **不是** OFFBOARD/arm/takeoff/landing executor 基线的回归：事件链在 takeoff 前全部正常，
  离线 Stage 7/8/V2 navigation 门全 PASS。
- **最可疑责任层**：EGO planner 轨迹生成/跟踪行为（trajectory 无减速、超速、横摆、穿墙规划），
  以及 LiDAR 感知证据缺失（`static_obstacle_observed=false`、`static_point_count_max=0`）。

按 AGENTS.md 默认策略：**不得直接调 EGO 参数**；先确认感知→地图→规划责任边界。

## 4. 遗留 open questions

1. EGO 是否在 `local x≈6` 处发生 replan 失败/轨迹中断（悬停 2s 后突然加速）？
2. Section A 墙在 FAST-LIO registered cloud / EGO grid map 中的实际观测质量如何？
3. `static_box_a` 为何完全未被 ROI 观测（0 points）？
4. EGO `max_vel=0.45` 与实际 `1.5+ m/s` 的差距来自 planner 轨迹还是 PX4 跟随？
5. RflySim crash listener 报 0，但 wall clearance 为负——碰撞检测语义需单独确认。

## 5. 本日已 live 验证的小修复（均通过离线回归）

- `competition_course_ue_loader.py`：entity payload parity 改为字段级浮点容差比较
  （Windows Py3.8 生成 vs WSL Py3.10 重算的 ULP 差异），metadata 仍严格相等；
  篡改拒绝测试全 PASS。
- `scripts/wsl/competition_course_v2_navigation.sh`：receipt `created_ids` 改为无序集合校验
  （创建顺序 vs manifest 排序顺序不同但 ID 集合一致）。

## 6. 环境收尾

- Stop 两轮完成：Windows GUI 进程关闭；WSL fastlio/sensor/ego 组按 manifest 显式 PID TERM
  补清（已知 PGID stop 缺陷），`record_stop(clean=true)` 已落盘。
- Post-stop inspect: `owned_and_alive=0`、`orphans=0`、`unknown_suspicious=0`、
  `ports_occupied_by_unknown=0`。

## 7. 下一步最小动作

1. 拉取该 run 的 EGO `bspline`/`traj` topic 或 node 日志（当前未落盘），确认 replan 行为；
2. 用只读 recorder 复跑 no-arm，检查 registered cloud 在 Section A 墙/static box 区域的
   point coverage（确认感知责任层）；
3. 若证据指向 EGO 行为，按 Yellow Zone 向用户说明影响面与设计后再动 planner 配置。
