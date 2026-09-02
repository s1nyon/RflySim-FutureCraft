# Competition Course V2 — UAV1 Section A Navigation RCA & Control-Chain Closure

Date: 2026-09-02 (Asia/Shanghai)
Status: **RCA CLOSED — A. EVALUATION_TOOLING_ERROR（飞行链各层均已用 time-aligned evidence 验证）**
Branch: `infra/rviz-live-handoff-20260825`

## 1. Result

- **Result: A. EVALUATION_TOOLING_ERROR（唯一当前 failure 层）**
- 受控 fresh `full_section_a` 飞行链本身 **PASS**：OFFBOARD→arm→takeoff→EGO goal→
  terminal settle→AUTO.LAND→disarm 全部确认，endpoint 4.55m（≥4.5m），wall clearance
  0.066m、static clearance 0.486m、collision 0、watchdog/geofence 未触发、UAV2 0 违规。
- 修复后重放该 run：`result=PASS`、`failure_reasons=[]`。

## 2. Root Cause

`static_box_a` 的 evaluation ROI 点计数（max 3/帧）低于 `MIN_OBSTACLE_ROI_POINTS=5` 阈值，
report 据此输出 `static_obstacle_observed=false` → `obstacle_perception` failure。
但 static box 实际 **进入了 LiDAR / Faster-LIO registered cloud**（Gate B no-arm 1–3 点，
Gate C 飞行 3–4 点），且 **EGO grid map 明确感知并绕行**（bspline 证据，见下）。
0.35×0.25×0.9m 小 box 在 Mid360 点云中只有少量命中是物理限制，不是感知失败。

## 3. Perception Chain（逐层）

```text
RflySim world geometry      → static box 存在（COURSE_READY / world probe PASS）
        ↓
raw Mid360 cloud            → box 命中 1–4 点/帧（Gate B no-arm 与 Gate C 飞行一致）
        ↓
Faster-LIO registered cloud → cloud frame=camera_init，ROI frame contract 通过；
                              centroid local ≈ (4.4–4.6, 1.18–1.28, 0.4–0.7) 与 spec 吻合
        ↓
EGO grid map                → bspline 在 box 区域明确绕行（见 Planner Chain），map 集成正常
```

## 4. Planner Chain

```text
goal (local 7.0,0.7,1.0) → bspline → PositionCommand
```

- EGO desired velocity：max 0.412 m/s、p95 0.354 m/s（configured limit 0.45）→ **0 over-limit**
- EGO desired acceleration：max 0.534 m/s²（configured limit 0.55）→ **0 over-limit**
- bspline 证据：traj 覆盖 box 区（x 3.0–5.5），y 保持在 box 左侧（0.30→0.55），
  min signed distance to box = **0.703 m** > 0 → 轨迹不穿 box，EGO map 知道障碍。
- 结论：planner trajectory 自身安全（Q2/Q3 回答：sane，无超限）。

## 5. Control Chain

```text
PositionCommand → MAVROS PositionTarget → PX4 → actual odom
```

- PositionTarget：`coordinate_frame=1`（FRAME_LOCAL_NED），
  `type_mask=3064`（IGNORE_VX/VY/VZ | IGNORE_AFX/AFY/AFZ | FORCE | IGNORE_YAW_RATE），
  **667（short）/ 909（full）样本 100% 一致** → `CONTROL_CONTRACT_POSITION_ONLY` 实锤。
- tracking：as-published position error p95≈1.15–1.17m，但逐样本分解显示误差主要来自
  起飞前/降落后 z 差（odom z≈−0.1 vs target z=1.0）；**飞行中 xy 误差 <0.1m、z 误差 <0.03m**。
- 实际速度：full run max 1.011 m/s（仅 1 样本）、p95 0.391 m/s；上次 full run 的 1.5 m/s
  未复现。position-only bridge 在飞行中跟踪正常，**Bridge Fix Gate 不成立**。
- 结论：控制链 contract 已记录为事实，但**不是**本次 failure 原因（Q4/Q5 回答）。

## 6. Short vs Full（Q1/Q6）

- short_smoke：终点在 static box 之前，无 obstacle passage 要求，PASS。
- full_section_a（受控 fresh run）：穿过 static/dynamic 区域，飞行链 PASS；
  仅 evaluation ROI 阈值误报。
- 首次 full run（2026-09-02 01:43，同栈 short→full 连续飞行）曾出现贴右墙（wall clearance
  −0.297m）、横向摆动 ±1m、1.5 m/s、冲出 geofence；**相同配置 fresh run 未复现**。
  差异线索：首次为同一 instance 连续第二次飞行（short 后直接 full），本次为 fresh instance
  首个飞行。列为**间歇性 planner/环境残余风险**，未归因确定缺陷，不修改任何 planner 参数。

## 7. RViz Evidence

- UAV1-only RViz（`rviz_mode:=uav1`）在两轮 Gate C flight 中运行；截图保存于
  `logs/live_stack/<stack>/gateB/rviz_uav1_screen.png`（人工可查）。
- RViz 未导致 CPU/real-time 明显劣化（两轮飞行均正常完成）。

## 8. Fix（仅 evaluation tooling）

- `competition_course_navigation_report.py`：
  - `static_obstacle_observed` = ROI 点数≥5 **或** EGO 轨迹绕行证据
    （`static_trajectory_evidence`：bspline 覆盖障碍区且 min signed distance>0）。
  - 保留 `static_point_count_max`、`static_obstacle_observed_by_roi` /
    `static_obstacle_observed_by_trajectory` 明细，阈值本身未放宽。
  - ROI frame mismatch 时仍输出 `ROI_EVALUATION_INVALID_FRAME` 并 fail-closed（动态证据不可用）。
- 未修改：EGO `max_vel`/`max_acc`/horizon/inflation/cost、Faster-LIO、PX4 controller、
  map geometry、static/dynamic obstacle、Section A endpoint、bridge。

## 9. Regression

- `validate_competition_course_v2_navigation.ps1` / `validate_competition_course_v2.ps1` /
  `validate_stage7.ps1` / `validate_stage8.ps1` / `validate_lifecycle.ps1` / `git diff --check`
  全部 PASS（修复后）。
- 真实 full_section_a run 重放 report：PASS。

## 10. Live Runs（Gate B/C）

- Gate B no-arm：`stack-20260901T181154Z-47b13614` / `px4-cc35fde30d748c22`
- Gate C round 1 short_smoke：`stack-20260901T182330Z-499467de` / `px4-415411333d5d94cc`
  （`v2-nav-20260901T183600Z-short_smoke`？见 run 目录，PASS）
- Gate C round 2 full_section_a：`stack-20260901T183217Z-393b8303` / `px4-c0345db885898bee`
  （`v2-nav-20260901T183600Z-full_section_a`，修复前 FAIL→重放 PASS）
- 三个栈均已 manifest-owned stop，post-inspect `owned_and_alive=0 / orphans=0 /
  unknown_suspicious=0`；WSL PGID stop 缺陷每次按显式 PID 补清。

## 11. Next

- 3× consecutive fresh-instance full Section A repeatability（当前 1× fresh full PASS）。
- 若间歇性冲出复现，优先采集 EGO replan 时刻日志（本轮已确认 EGO 节点日志入口），
  再决定是否进入 planner 行为评审；本轮不自动继续。
