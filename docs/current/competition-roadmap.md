# Competition Capability Roadmap（比赛能力开发主索引）

> 状态基准：2026-08-11（lifecycle P0 已冻结、PBL-1 full-stack regression 已 CLOSED、
> 迁移后 `dev` live 链 armed 验证已恢复，证据
> `docs/evidence/2026-08-11-live-import-and-pwsh-compat-armed-verified.md`；
> 已知 OPEN：WSL 进程组 stop 失效，见
> `docs/incidents/2026-08-11-wsl-pgid-stop-ineffective.md`）
> 依据：正式赛题文件
> `docs/reference/competition-guide-2026.pdf`，赛题 2.1
> 「室内狭窄通道环境下多飞行器智能协同导航与作业挑战赛」。
> 本文档是比赛能力开发的**主设计索引**；历史调试细节保留在各 development log，
> 不重复复制到本文档。

---

## 1. Competition North Star

> 构建一个由 **不少于两架飞行器** 组成的全自主室内协同系统，使其在正式赛题规定的
> **狭窄、带转弯、含静态与动态障碍** 的通道环境中，于 **12 分钟任务时限** 内依次完成：
> 集群自主起飞（20 s 内）→ 双机进入通道（20 s 内）→ 在线定位与自主避障 →
> 未知目标搜索与协同作业（彩色标签 / 二维码 / 温度异常点）→ 穿越通道 →
> 通道出口外 ArUco 平台精准降落；除赛题明确允许的启动 / 急停外，**不依赖人工遥控**。

目标不是“让飞机飞得更丝滑”，也不是“把 EGO-Swarm 调到论文级”，而是：

> 赢得/完成正式比赛任务所需的全自主能力，且可重复、可证明。

## 2. Official Competition Requirements（赛题 2.1，以正式 PDF 为准）

### 2.1 任务（四步）

| # | 任务 | 硬约束 |
|---|---|---|
| 一 | 多飞行器自主集群起飞 | ≥2 架；同时或依次 **20 s 内**自主起飞；不得相互碰撞 |
| 二 | 协同导航与避障 | 并行或依次 **20 s 内**进入狭窄通道；避开静态（锥桶、支架）与动态（摆动的悬挂物）障碍；避免相互碰撞及与环境碰撞 |
| 三 | 协同目标作业 | 通道内 **3 个作业目标点**（带颜色的标签、二维码、温度异常点）；位置**赛前未知**；每点至少一架成功识别并记录；实时返回目标类型 + 相对通道坐标系位置 |
| 四 | 穿越通道并定点降落 | 有序穿越通道出口进入降落区；依次或同时降落在带 ArUco 二维码的平台上；避免相互干扰/碰撞 |

### 2.2 场地与时间

- 起飞区：平坦无障碍，起飞点数量 ≥ 飞行器数。
- 通道：长 ≥3 m、宽 ≤1.5 m、转弯半径 ≤1 m；评分按 **3 个通道段** 计（Sb）。
- 降落区：通道出口外多块平台，每块中央贴 **ArUco 4×4_250（ID 随机）**，数量 ≥ 飞行器数，
  平台间距 ≥1.5 m。精准降落定义：二维码范围内 + 姿态正。
- 准备阶段限时 10 min（含 1 名队员 5 min 检录答辩）；任务阶段 ≤12 min；
  每组一次完整任务，设备故障可申请一次重试（重试后原成绩作废）。
- 禁止人工遥控干预，**启动与急停除外**。

> ⚠️ PDF 内部不一致：通道场景说明写降落二维码 50cm×50cm，降落区域说明写 60cm×60cm。
> 以正式细则最终口径为准（Roadmap 暂记为 60cm×60cm，来源：§「降落区域二维码说明」）。

### 2.3 评分结构（满分 100，同分比时间）

| 项 | 分值 | 说明 |
|---|---:|---|
| Sa 集群起飞 | 10 | 全部起飞且无碰撞 |
| Sb 协同导航与避障 | 30 | 每成功穿越一个通道段且无碰撞 +10（共 3 段）；每碰撞一次 **-5**（含障碍物/墙体/机间） |
| Sc 协同目标作业 | 30 | 每成功识别并完成一个目标点 +10（共 3 点） |
| Sd 穿越并降落 | 20 | 全部穿越并降落 +14；每架精准降落（二维码内+姿态正）+2 |
| Se 技术汇报 | 10 | 协同策略、系统设计、创新性 |

成绩为 0 的情形：飞行器数量 <2；比赛中出现人工遥控干预（紧急停飞除外）；飞出比赛区域。
任务超 12 min 终止并按 12 min 内成绩计。

## 3. Current Capability Assessment（truthful，2026-08-08）

等级：`DONE`（有 live 证据并闭环）/ `BASELINE`（能跑但未按比赛要求验收）/
`PARTIAL` / `SCAFFOLD`（接口占位）/ `NOT IMPLEMENTED` / `BLOCKED`。

| 能力 | 状态 | 证据 / 说明 |
|---|---:|---|
| Lifecycle（启动/停止/fresh-instance/ownership/topology/安全 stop） | **DONE\*** | 5 次连续 closure + 3 次 full regression；`docs/evidence/2026-08-08-lifecycle-p0-fix-live-validated.md`；\*2026-08-11 复验发现 `stack_stop.py` WSL PGID kill 失效（stop 报 NOT clean，需显式 PID 补清），待 Yellow Zone 修复，见 `docs/incidents/2026-08-11-wsl-pgid-stop-ineffective.md` |
| 双机 PX4/MAVROS/FAST-LIO/EGO 软件栈 | **BASELINE** | 3× fresh-instance 完整飞行 success（`docs/evidence/2026-08-08-pbl1-fullstack-regression-closure.md`） |
| OFFBOARD / arming / takeoff / landing(AUTO.LAND) | **BASELINE** | 每轮 41.5 s 全程 14 段确认；但按比赛 20 s 起飞窗验收未做 |
| 窄通道导航（当前已知路线） | **BASELINE** | PBL 已知隧道 14/14 段；比赛几何（宽≤1.5m、3 段、转弯）未按赛题验收 |
| 静态障碍避障（锥桶/支架） | **NOT IMPLEMENTED** | 当前场景只有墙体/赛道静态物；锥桶/支架类目标障碍未建 |
| 动态障碍避障（摆动悬挂物） | **NOT IMPLEMENTED** | 无动态障碍验收 |
| 双机同时/20s 内进入通道 | **NOT IMPLEMENTED** | 当前是 UAV1 全程→UAV2 全程（错时）；与比赛协同语义不一致 |
| 机间防撞 | **PARTIAL** | 感知式 EMERGENCY_STOP 曾 live 触发一次；无系统性双机同时进通道验证 |
| 视觉目标感知（彩色标签/二维码/温度） | **SCAFFOLD** | `sim_vision_target_provider` 为 mock/JSON 接口占位，**不是完整视觉能力**；D435i RGB/depth transport 部分可用（`lidar_only` 默认） |
| 目标定位（相对通道坐标系） | **NOT IMPLEMENTED** | — |
| 协同目标作业（识别→记录→去重→分工） | **NOT IMPLEMENTED** | — |
| ArUco 精准降落 | **NOT IMPLEMENTED** | 当前仅 AUTO.LAND；无 ArUco 检测/对齐 |
| 完整比赛任务（起飞→进通道→作业→穿出→降落→报告） | **NOT IMPLEMENTED** | — |

## 4. Requirement → Capability → Evidence 映射

| 比赛要求 | 项目能力 | 状态 | 证据 | 下一缺口 |
|---|---|---|---|---|
| ≥2 架飞行器 | dual PX4/MAVROS/CopterSim | DONE | topology + 3× closure | — |
| 20 s 内自主起飞且无碰撞 | mission executor takeoff | PARTIAL | takeoff 确认（未按 20 s 窗验收） | P2 起飞窗/防碰撞验收 |
| 20 s 内进入通道 | 双机 entry scheduler | NOT IMPLEMENTED | — | P3-A |
| 3 段窄通道穿越 | FAST-LIO + EGO + waypoint | BASELINE | 14/14 段（已知隧道） | P2 按比赛几何验收 |
| 静态障碍避障 | — | NOT IMPLEMENTED | — | P2 静态障碍回归 |
| 动态障碍避障 | — | NOT IMPLEMENTED | — | P2 动态障碍回归 |
| 机间防撞 | 感知式 EMERGENCY_STOP | PARTIAL | 一次 live 触发 | P3-B/C |
| 未知目标感知 | vision pipeline (mock) | SCAFFOLD | `sim_vision_target_provider` | P4 真实 detector |
| 目标定位 | — | NOT IMPLEMENTED | — | P4-E |
| 协同目标作业 | mission layer | NOT IMPLEMENTED | — | P5 target ownership |
| ArUco 精准降落 | AUTO.LAND only | NOT IMPLEMENTED | — | P6 |
| 全自主任务闭环 | — | NOT IMPLEMENTED | — | P7 |
| 12 min 时限 / 同分比时间 | — | NOT IMPLEMENTED | — | P8 |

## 5. Development Phases（Competition Capability Roadmap）

### Phase 0 — Engineering Foundation（CLOSED / FROZEN）

- goal：可靠、可重复、安全地启动/停止完整双机系统（lifecycle/ownership/topology/fresh-instance/safe stop/diagnostics）。
- status：**CLOSED**（5× closure + 3× full regression）。
- exit：已完成；仅真实 regression evidence 才重新打开（AGENTS.md Red-Zone 不变）。

### Phase 1 — PBL Full-Stack Baseline（CLOSED）

- goal：证明双机定位/规划/控制链稳定运行（FAST-LIO×2 + EGO×2 + OFFBOARD×2 + 当前 waypoint baseline + landing/disarm）。
- status：**CLOSED**（3× fresh-instance full flight success）。
- 定位：这是 **regression baseline**，不是比赛 mission strategy（当前 UAV1 全程→UAV2 全程在 P3 前必须替换）。

### Phase 2 — Competition-Grade Narrow-Corridor Navigation（ACTIVE）

- goal：两架无人机在比赛规定的窄通道中连续、安全、高效导航，对未知静态/动态障碍在线响应，满足进入时限与碰撞约束。
- current map gate：**CLOSED / MAP READY (2026-09-01)**。single-source geometry、
  preview、validator、RflySim entity metadata 与 no-arm RGB/LiDAR/IMU/Faster-LIO
  验收均通过；没有通过 EGO、mission 或控制参数掩盖地图问题。见
  [`2026-09-01-competition-course-v2-map-acceptance.md`](../evidence/2026-09-01-competition-course-v2-map-acceptance.md)。
- current navigation gate：**BLOCKED AT LIVE LIFECYCLE GATE (2026-09-01)，offline ready**。
  UAV1 Section A 的 spec-derived world↔local transform、`short_smoke` / `full_section_a`
  单目标 plan、opt-in terminal settle、AUTO.LAND disarm confirmation、UAV2 连续隔离监控、
  collision heartbeat 与 provenance-labelled clearance report 已实现；V2 navigation、V2 map、
  Stage 7 和 Stage 8 离线回归均 PASS。没有修改 EGO/Faster-LIO 参数、PBL route 或 dual-UAV
  mission semantics。入口与验证：

  ```powershell
  scripts\validate_competition_course_v2_navigation.ps1
  scripts\run_competition_course_v2_navigation.bat --dry-run --profile short_smoke --stack-id <id> --manifest <path>
  ```

  live 仍未执行，因此不得描述为 navigation PASS。重启后的只读 inspect 对旧 stack
  `stack-20260831T173615Z-6d6e09b6` 报告 `stale_pid_reuse=1`：manifest 中原
  RflySim3D PID `20072` 现属于系统 `svchost.exe`。端口为空且没有 owned-alive 进程，
  但 lifecycle 规则要求 fail closed；不得 kill 该系统进程、不得自动清理或绕过。
  证据见
  [`2026-09-01-v2-section-a-live-lifecycle-blocker.md`](../evidence/2026-09-01-v2-section-a-live-lifecycle-blocker.md)。
  lifecycle 状态经人工安全处置后，下一内部阶梯是 current-instance no-arm →
  1× short smoke → 1× full Section A diagnostic → 3× consecutive fresh-instance full Section A。
  设计与执行边界见
  [`2026-09-01-competition-course-v2-navigation-baseline-design.md`](../architecture/2026-09-01-competition-course-v2-navigation-baseline-design.md)。
- work：motion baseline metrics；corridor/gate guidance；look-ahead goal transition；online local replanning；
  静态障碍回归；动态障碍回归；velocity/acceleration tuning；clearance monitoring。
- KPI：collision=0；min wall clearance；navigation success rate；time to enter corridor；
  time to traverse corridor；replanning success；dynamic obstacle avoidance success；OFFBOARD loss=0。
- entry：Phase 1 保持可用；exit：双机均能进入通道、静态/动态障碍测试通过、连续 N 次无碰撞、
  无 unexpected OFFBOARD loss（N 与时间阈值按正式细则确定，未定则标 TBD after rules）。
- 注意：Gate / Look-ahead 只是当前优先研究的实现策略，**不是强制比赛要求**；若有更简单可靠方案可替换。

### Phase 3 — Multi-UAV Corridor Coordination

- goal：两架无人机真正同时参与任务（非 UAV1 完成全程后才 UAV2 开始）。
- 逐步：P3-A staggered dual entry（20 s 窗）→ P3-B minimum-separation control →
  P3-C corridor segment reservation → P3-D priority/yield/wait → P3-E failure/blocked-path recovery。
- 允许“高层 corridor coordination + 独立 EGO local planner”作为合法且优先的工程方案；
  是否需要统一 global frame / swarm trajectory exchange 由后续实验与比赛需求决定。

### Phase 4 — Competition Perception（提高优先级）

- goal：真实感知 3 类目标（带颜色标签、二维码、温度异常点）并按比赛输出
  类型 + 相对通道坐标系位置。
- 拆分：P4-A RGB transport（D435i，`--sensor-mode full`）→ P4-B color detection →
  P4-C QR detection/decoding → P4-D thermal（若赛题与硬件链支持）→ P4-E target localization →
  P4-F confidence/duplicate filtering → P4-G target-provider contract integration。
- 明确：`sim_vision_target_provider` 只是 mission-perception **接口 scaffold**，不是视觉能力。

### Phase 5 — Cooperative Target Operation

- goal：发现→确认→记录→避免重复→协同覆盖（target state / ownership / claim / completion /
  inter-UAV result sharing / duplicate suppression / reallocation）。
- 建议状态机：`UNSEEN → DETECTED → CLAIMED → SERVICING → COMPLETED`。
- 实现框架（BT / state machine / mission manager）由后续决定，本轮不选型。

### Phase 6 — Precision Exit and Landing

- goal：ArUco 平台精准降落（detect marker → relative pose → approach → fine alignment →
  descent → touchdown → disarm）。
- KPI：landing success rate；horizontal landing error；landing time；wrong-platform rate。

### Phase 7 — Full Competition Mission Integration

- goal：READY → 自主起飞 → 规则窗口内双机进通道 → 窄通道导航 → 静/动态避障 →
  目标搜索 → 协同任务分配 → 目标作业 → 双机穿出 → 精准降落 → mission report。
- 只有通过该阶段真实 evidence 才可用 `COMPETITION READY`。

### Phase 8 — Score / Reliability Optimization

- goal：时间优化、速度调优、可靠性、失败恢复、传感器退化测试、重复 fresh-instance、
  比赛日工作流。**在任务功能完整以前不追求极限速度。**

## 6. Dependency Graph

```text
Engineering Foundation (P0, DONE)
        ↓
PBL Baseline (P1, DONE)
        ↓
Narrow-Corridor Navigation (P2, NEXT)
      ↙            ↘
Coordination (P3)    Perception (P4)
      ↘            ↙
Cooperative Target Operation (P5)
        ↓
Precision Landing (P6)
        ↓
Full Mission Integration (P7)
        ↓
Reliability / Score Optimization (P8)
```

可并行：真实 RGB detector（P4）可在 P2/P3 部分导航工作期间并行开发；
但完整协同目标任务（P5/P7）依赖导航与感知均达到一定成熟度。

## 7. Score Priorities（Score-before-polish）

按正式评分（Sa 10 + Sb 30 + Sc 30 + Sd 20 + Se 10）：

1. Safety（collision=0，不牺牲安全）；
2. Task completeness（把 Sb 3 段、Sc 3 目标、Sd 穿越降落全部做出来——约占 80 分）；
3. Reliability（连续可重复）；
4. Score coverage（补齐能拿分的能力，优先于轨迹审美）；
5. Time performance（同分比时间，最后优化）；
6. Aesthetic smoothness（次要性能指标）。

原则：**先实现真正产生比赛能力/分数的功能，再优化已经可以拿分的能力**；
禁止花数周微调轨迹 jerk 而真实目标检测仍是 mock。

## 8. Hard Invariants

- **Safety**：验收轮 collision 必须为 0；除规则允许动作外无人工控制；禁止全局进程扫杀；
  OFFBOARD 意外丢失按失败处理。
- **Multi-UAV**：不得把“两个 planner 都启动”描述为完成多机协同；不得把
  “UAV1 全程→UAV2 全程”描述为最终 competition coordination。
- **Perception**：不得把 mock detections 描述为 real vision capability。
- **Planning**：项目使用 EGO-Swarm 不意味着所有功能必须围绕它设计；更简单可靠的高层
  coordination 若满足比赛需求，允许采用。
- **Evidence**：任何 `DONE / CLOSED / COMPETITION READY` 必须有实际 test evidence。

## 9. Smoothness 的真实定位

连续运动质量是比赛级导航的**次要性能指标**（减少不必要停顿、提高通道通过效率、
降低控制冲击、可能改善任务时间）；它不是独立比赛目标。

```text
safe autonomous completion = primary metric
smoothness = secondary performance metric
```

未来指标：flight time、path length、goal transition 速度跌落、acceleration、jerk、
wall clearance、collision count、planner failure count。

## 10. Gate / Look-ahead 的研究定位

- Gate：解决“任务层过度约束精确 waypoint”，把“必须到某一点”变成“安全穿过某 corridor section”。
- Look-ahead：解决 waypoint stop-and-go，实现连续 goal transition。
- 若实验发现现有 EGO waypoint / preset-target 模式有更简单可靠的方法满足比赛需求，
  **可以替换 Gate/Look-ahead**；它们不是不可改变的架构要求。

## 11. Explicit Non-Goals

- 不是最终目标：必须魔改 EGO-Swarm；必须实现论文级 swarm trajectory optimization；
  追求最小 jerk 本身；证明某种规划算法理论最先进；把所有传感器同时接进 EGO；
  为了架构漂亮重写已稳定的 lifecycle。
- 项目目标是：赢得/完成比赛任务所需的可靠自主能力；研究优化必须建立在比赛功能完整之上。

## 12. Competition Ready 定义

只有以下全部具备真实 evidence 才允许写 `COMPETITION READY`：

- 多机自主启动/起飞；进入时限满足；窄通道导航；环境避障；机间避障；
- 未知目标感知；协同目标作业；目标信息记录；全通道穿越；精准降落；
- 全自主任务闭环；可重复性（fresh-instance）。

`PBL-1 PASS` ≠ `Competition Ready`。

## 13. Acceptance Gates（阶段级）

每个阶段定义 Entry / Work / Exit；Exit 中的具体 N 与时间阈值：

- 若正式细则已给出 → 使用细则值；
- 否则标 `TBD after rules`，禁止无依据编数字。

## 14. 旧路线处理

- 旧 `M2 = Smooth narrow-space motion`、`M3 = Better dual-UAV coordination` 的表述
  **已被本文档取代**（见 `.agents/AGENT2READ.md` §20 Historical 标记）。
- 历史 evidence（lifecycle 根因、PBL regression、stage7/8 失败报告）**保留**，
  本文档只引用不替换。

## 15. 来源与链接

- 正式赛题 PDF：`docs/reference/competition-guide-2026.pdf`
- lifecycle closure：`docs/evidence/2026-08-08-lifecycle-p0-fix-live-validated.md`
- PBL regression closure：`docs/evidence/2026-08-08-pbl1-fullstack-regression-closure.md`
- 迁移后 armed live 恢复：`docs/evidence/2026-08-11-live-import-and-pwsh-compat-armed-verified.md`
- lifecycle 设计：`docs/architecture/2026-08-08-live-stack-lifecycle-design.md`
- Agent 入口：`.agents/AGENT2READ.md`
