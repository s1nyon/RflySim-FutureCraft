# Competition Course V2 — UAV1 Section A 3× Fresh Repeatability（CLEARANCE NOT STABLE）

Date: 2026-09-02 (Asia/Shanghai)
Status: **SECTION A FLIGHT PASS / CLEARANCE NOT STABLE**

## 1. Result

- 3/3 consecutive fresh-instance `full_section_a` **flight chain PASS**：
  OFFBOARD/arm/takeoff/EGO goal/terminal settle/AUTO.LAND/disarm 全确认；
  endpoint 4.51–4.58m；collision 0；watchdog/geofence 0；UAV2 0 违规；
  perception（sparse static + dynamic temporal）全 PASS；planner velocity 0 over-limit。
- **0/3 stable baseline PASS**：每轮 `minimum_wall_clearance_m` = 0.072 / 0.085 / 0.073，
  均 < `navigation_clearance_threshold_m = 0.25`（来源
  `map_spec.clearance_policy.lateral_margin_each_side_m`）。
- 结论：**SECTION A FLIGHT PASS / CLEARANCE NOT STABLE**（任务书分类 2）。

## 2. Acceptance Contract（Gate 0 已实施并提交 `f47a048`）

- static perception：sparse temporal evidence（frame contract valid 且 ≥3 帧
  `point_count≥1` 且 centroid error ≤0.5m）→ `static_registered_cloud_observed`；
  planner avoidance 独立字段（`planner_avoidance_consistent` / min signed distance /
  region coverage），不覆盖 perception 判定。
- wall contract：`collision_free = min_wall_clearance >= 0`；
  `navigation_clearance_pass = min_wall_clearance >= 0.25`；
  `navigation_clearance` 为独立 failure reason。

## 3. Frozen Configuration

- map spec `6CE845DDB7269898`；navigation config `B51C8F6F4302D8D9`；
  stage7 live config `F2E116EA70CD39A9`；ego launch `0AC5091A…/1FCE523E…`；
  fastlio launch `E70C1CF9…`；bridge `D284A450…`；commit `f47a048`。
- 3 轮之间无任何参数修改；仅 Run #2 因 readiness 120s 窗口在 EGO 启动链路下过紧，
  以 `STAGE7_READINESS_MAX_AGE_SEC=300` 运行（同一 instance 的实时证据，未改代码）。

## 4. Run Details

| | Run #1 | Run #2 | Run #3 |
|---|---|---|---|
| stack | `stack-20260901T185525Z-19bc4644` | `stack-20260902T034825Z-363300e9` | `stack-20260902T040228Z-33a4e2e7` |
| sim instance | `px4-d85f016a6cda2715` | `px4-52b0b10efc975e0d` | `px4-410ff97740b4a932` |
| nav run | `v2-nav-…185855Z-full_section_a` | `v2-nav-…035653Z-full_section_a` | `v2-nav-…040634Z-full_section_a` |
| flight chain | PASS | PASS | PASS |
| endpoint s | 4.506 m | 4.578 m | 4.571 m |
| min wall clearance | 0.072 m | 0.085 m | 0.073 m |
| static clearance | 0.473 m | 0.476 m | 0.478 m |
| collision / watchdog | 0 / 0 | 0 / 0 | 0 / 0 |
| static ROI frames / max pts | 33 / 3 | 32 / 3 | 34 / 3 |
| planner vel max / p95 | 0.403 / 0.350 | 0.415 / 0.354 | 0.403 / 0.319 |
| planner accel over-limit | 0 | 0 | 6（max 0.576） |
| PositionTarget type_mask | 3064（926） | 3064（908） | 3064（927） |
| UAV2 violations | 0 | 0 | 0 |
| lifecycle | manifest stop + PID 补清 clean | 同左 | 同左 |

## 5. Clearance RCA（系统性）

- 每轮所有 `min_wall_clearance < 0.25m` 样本均集中在 **起飞/进入段**
  `s ∈ [-0.42, 1.9]`、`section_a_right` 墙；corridor 后段（s>1.9）无贴墙。
- 根因：EGO 从 spawn local (0,0) 直飞 goal (7.0,0.7) 的初始轨迹在 Section A 入口
  处 local y≈0.25（右墙 surface local y≈−0.05），车辆表面距墙仅 0.07–0.09m。
- 属于 **EGO 起飞段轨迹行为**；本轮按任务书不调 EGO/Faster-LIO/bridge/PX4/地图。
- 首次严重冲出事件（wall −0.297m、1.5m/s、geofence）在 3 轮中**未复现**。

## 6. 残留风险 / Next

- 起飞段 wall clearance 系统性低于 0.25m 稳定阈值；3× stable baseline 未关闭。
- 下一最小动作（需 Yellow Zone 评审，本轮不执行）：针对 EGO 起飞段初始轨迹
  （spawn→Section A 入口贴右墙）的最小 planner experiment plan，或重新评估
  起飞路径/进入段设计；不接受通过修改 acceptance threshold 来"通过"。
