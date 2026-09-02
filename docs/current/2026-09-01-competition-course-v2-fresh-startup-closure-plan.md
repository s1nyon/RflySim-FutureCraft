# Competition Course V2 Fresh-Startup Closure 修复计划

> 日期：2026-09-01
> 分支：`infra/rviz-live-handoff-20260825`
> 当前状态：`MAP NOT READY`
> 优先级：P0
> 目标：尽快恢复并关闭 Competition Course V2 地图阶段；暂停 Navigation / EGO live flight，直到地图在 fresh RflySim 中可重复正确加载。

---

# 1. 背景与事故结论

最新 fresh live 验证推翻了此前的 `MAP READY` 结论。

实际观察到：

- 隧道/静态 corridor 没有正确保留在 RflySim world；
- 动态摆锤尺寸异常；
- `COURSE_READY` 曾被置为 true，但实际场景状态明显错误；
- 之前的 evidence 更多证明了：
  - spec / geometry / manifest 在离线层一致；
  - loader 命令被发送；
  - 某些旧 running instance 上可通过 exact-ID reload 得到正确结果；
- 但没有真正证明：
  - **fresh RflySim startup 后，完整 V2 world state 可以稳定保留。**

因此当前结论必须改为：

> **Competition Course V2 geometry 设计暂不推倒重来；当前 blocker 优先判定为 live deployment / runtime ownership / async same-ID destroy-create race，而不是 corridor geometry 本身。**

本轮只修复地图的 live deployment contract。

---

# 2. 本轮最终目标

最终需要建立如下可信链路：

```text
competition_course_v2.json
        |
        v
deterministic geometry
        |
        +--> validator
        +--> preview
        +--> entity manifest
        |
        v
fresh RflySim startup
        |
        v
inactive-course cleanup only
        |
        v
selected V2 idempotent upsert
        |
        v
dynamic obstacle motion
        |
        v
post-load world-state retention verification
        |
        v
COURSE_READY
```

只有当 **两次独立 fresh startup** 都满足 live world-state 和视觉验收后，才能重新声明：

`Competition Course V2 — MAP READY`

地图阶段关闭后，才能恢复 Navigation。

---

# 3. 当前核心根因

## 3.1 P0 — Cross-instance `load_receipt.json` 污染

当前 live receipt 与 deterministic generated artifacts 混在固定目录，例如：

```text
generated/competition_course_v2/load_receipt.json
```

该文件可能来自上一个 RflySim / stack instance。

如果 loader 在新的 fresh RflySim 中读取上一轮 receipt，并执行：

```text
old receipt
    ↓
sendUE4Destroy(previous V2 IDs)
    ↓
immediately recreate same V2 IDs
```

则出现严重语义错误：

> 上一个 simulation instance 的 ownership state 控制了新的 RflySim process。

这会产生异步 Destroy / Create race。

尤其底层 UE/RflySim command 不提供可靠同步 ACK 时，可能出现：

```text
Destroy(old ID)
Create(same ID)
delayed Destroy arrives
→ newly created entity disappears
```

### 修复原则

`generated/competition_course_v2/` 只能保存 deterministic artifacts：

- entity manifest；
- preview；
- offline geometry report；
- terrain/marker assets；
- deterministic validation output。

Live ownership / load receipt 必须是 **run-scoped / stack-scoped / simulation-instance-scoped**。

建议：

```text
logs/live_stack/<stack_id>/competition_course_v2/
    load_receipt.json
    transition_receipt.json
    motion.json
    acceptance.json
```

receipt 至少绑定：

```text
stack_id
simulation_instance_id
spec_sha256
created_at
```

只有满足：

```text
receipt.stack_id == current_stack_id
AND
receipt.simulation_instance_id == current_simulation_instance_id
```

时，receipt 才允许参与当前 instance 内的 reload/cleanup。

跨 instance receipt：

```text
MUST NOT trigger sendUE4Destroy()
```

---

# 4. P0 — Course transition 不应销毁 selected V2 自己

当前 transition 逻辑如果对所有 tracked course ID 都执行 Destroy，则在 selected course 为 V2 时仍会：

```text
destroy predicted IDs
+
destroy V2 IDs
+
load V2
```

即使中间增加固定 sleep，也只是降低 race 概率，不是正确语义。

## 正确 contract

### selected = Competition Course V2

只允许：

```text
destroy inactive predicted_narrow_course IDs
DO NOT destroy selected V2 IDs
upsert V2 entities
```

### selected = predicted course

只允许：

```text
destroy inactive V2 IDs
DO NOT destroy selected predicted IDs
upsert predicted entities
```

核心原则：

> **Transition cleanup 只处理 inactive course。Selected course 的 entity state 通过 idempotent upsert 保证。**

不要通过“先销毁 selected course 再重新创建”来实现正常加载。

---

# 5. Selected course 使用 idempotent upsert

`sendUE4PosScale` 应被视为：

```text
create OR update entity state
```

因此正常加载 selected V2 时：

```text
sendUE4PosScale(
    ID,
    model,
    pose,
    scale
)
```

即可同时覆盖：

- entity 不存在 → create；
- entity 已存在 → update。

不要在正常 startup 前对 selected IDs 先 Destroy。

这样可以避免：

```text
Destroy + same-ID Create
```

导致的异步顺序问题。

---

# 6. Static map delivery reliability

V2 静态 corridor 不应只依赖一轮 UDP burst。

保持实现轻量，不建立复杂 retry framework。

推荐：

```text
static pass 1
↓
short settle 0.2–0.5 s
↓
static pass 2
```

第二轮发送完全相同：

```text
ID
pose
yaw
scale
asset
```

由于是 create/update，这属于幂等 reinforcement。

目的：

- 降低 UDP 单包丢失造成某面墙永久缺失的概率；
- 不引入新的长期后台 retry loop；
- 不扩大 lifecycle 复杂度。

---

# 7. 动态障碍修复

## 7.1 保留 Scale

动态障碍运动时必须继续使用：

```text
sendUE4PosScale
```

不能退回只更新 pose、导致 asset 恢复 native size 的 API。

动态运动每一帧都必须携带：

```text
spec-derived scale
```

focused tests 必须覆盖：

```text
motion update always uses expected Scale
motion update never falls back to native size
```

---

## 7.2 修复 pendulum 初始位置

摆锤需要区分：

```text
pivot
```

与：

```text
moving object center
```

如果 entity 初始创建位置直接使用 `pivot`：

```text
spawn at suspension pivot
↓
motion controller starts
↓
jump to bob position
```

视觉上会出现巨大跳变/异常。

应从：

```text
pendulum_pose(dynamic_spec, t=0)
```

得到真实初始 moving-object center。

因此：

```text
pivot = suspension reference
center = actual object center at current phase
```

不要把 pivot 当 entity center。

本轮不修改：

- amplitude；
- period；
- pendulum length；

除非 fresh live evidence 明确证明 spec 参数自身错误。

---

# 8. 暂时冻结 V2 geometry

当前不要修改：

- Section A/B/C centerline；
- corridor width；
- turn radius；
- wall thickness；
- wall height；
- spawn；
- landing area；
- static obstacle positions。

原因：

已有 offline validator / preview / deterministic transform 基本自洽。

当前 fresh-live 事故首先指向：

```text
runtime deployment
ownership
async destroy/create
dynamic entity update
readiness evidence
```

而不是地图数学几何。

只有新的 world-state probe 明确证明：

```text
requested geometry itself wrong
```

才重新打开 geometry design。

---

# 9. 修正 `COURSE_READY` 语义

当前最大的问题之一是：

```text
loader returned 0
+
motion process alive
=
COURSE_READY
```

这是错误的。

它只能证明：

> 命令发送流程没有立即报错。

不能证明：

> 地图现在真的存在。

## 正确 readiness contract

`COURSE_READY` 必须依赖：

```text
commands sent
↓
world state observed
↓
world state retained
↓
visual acceptance
```

至少增加：

# Post-load retention gate

---

# 10. Post-load retention gate

优先复用现有 SDK probe / entity state query，不重复造大型框架。

第一次 probe 前：

```text
wait ~3 s
```

然后：

```text
Probe A
```

再：

```text
wait ~2 s
```

执行：

```text
Probe B
```

A 和 B 都必须 PASS。

## Static entities

至少验证：

- 全部 generated wall IDs；
- static_box_a；
- static_pillar_b；
- landing/static representative entities。

检查：

```text
entity exists
position matches expected
yaw matches expected
dimension / scale matches expected
```

允许合理数值 tolerance，但必须 deterministic。

---

## Dynamic entity

验证：

```text
pendulum ID exists
scale remains correct
position changes over time
```

不能只检查：

```text
motion process alive
```

---

# 11. 为什么必须双 probe

之前的故障可能来自：

```text
Create
↓
immediate probe sees entity
↓
delayed Destroy arrives
↓
entity disappears
```

所以单次 probe 不够。

双 probe 的目标就是验证：

> entity 不仅“出现过”，而且“稳定保留”。

如果 A PASS、B FAIL：

```text
MAP NOT READY
```

直接回到 runtime deployment layer 排查。

---

# 12. Live visual evidence

自动 SDK/world-state evidence 仍不能完全取代真实画面。

每次 fresh map acceptance 至少保留：

## Overview screenshot

能看到：

- 完整 corridor；
- Section A；
- Turn A；
- Section B；
- Turn B；
- Section C；
- exit / landing area。

## Obstacle screenshot

能看到：

- static obstacle；
- pendulum；
- pendulum 尺寸合理；
- pendulum 周围空间关系合理。

## UAV entrance view

至少能确认：

- UAV spawn；
- initial yaw；
- corridor entrance；
- 起点附近墙体没有异常遮挡。

注意：

```text
offline preview != live visual evidence
```

preview 证明 specification。

live screenshot 证明 deployment。

---

# 13. Gate A — Offline Runtime Fix

一次完成：

1. selected course 不再被 transition destroy；
2. live receipt 变成 stack/instance scoped；
3. cross-instance receipt 不参与 cleanup；
4. selected V2 改为 idempotent upsert；
5. static entities 2-pass delivery；
6. dynamic initial center 修正；
7. dynamic updates 保留 Scale；
8. post-load retention probe；
9. `COURSE_READY` 只在 retention PASS 后写入；
10. focused tests。

然后运行：

```text
scripts\validate_competition_course_v2.ps1
scripts\validate_competition_course_v2_navigation.ps1
scripts\validate_stage7.ps1
scripts\validate_stage8.ps1
```

Navigation 实现保持冻结。

---

# 14. Gate B — Fresh Map-Only Live Run 1

必须使用：

# FRESH RflySim INSTANCE

不得使用旧 running instance 上的 hot reload 替代 fresh acceptance。

本轮：

```text
NO EGO
NO mission
NO OFFBOARD
NO arming
```

如果当前 lifecycle 只能完整启动基础 stack，可以接受 no-arm full stack。

不要为了 map-only 验收再重构 lifecycle。

---

## Gate B 必须同时 PASS

### Runtime

```text
retention probe A = PASS
retention probe B = PASS
```

### Tunnel

```text
all expected wall IDs retained
wall dimensions correct
corridor visually complete
```

### Static obstacles

```text
correct ID
correct position
correct dimensions
visible in expected region
```

### Pendulum

```text
correct ID
correct Scale
correct initial center
motion visible
no native-size regression
```

### Readiness

```text
COURSE_READY=true
```

只能发生在上述条件满足以后。

否则：

```text
MAP NOT READY
```

---

# 15. Gate C — Fresh Map-Only Live Run 2

Run 1 完全通过后：

```text
stop current stack
↓
clean lifecycle state
↓
start independent fresh stack
↓
load V2
↓
retention A
↓
retention B
↓
visual inspection
```

不得依赖：

- 人工 hot reload；
- 手工 resend；
- 临时脚本修墙；
- 上一轮 RflySim 状态。

如果第二次 fresh startup 仍完全正确：

```text
Competition Course V2 — MAP READY
```

地图阶段关闭。

不需要再做 3× / 5× fresh map regression。

---

# 16. 本轮严格禁止

暂停：

- EGO flight；
- Section A Navigation；
- OFFBOARD；
- arm；
- EGO tuning；
- Faster-LIO tuning；
- OpenVINS；
- dual-UAV coordination；
- mission C++；
- full corridor navigation；
- geometry redesign；
- 为了 live 通过而手工移动墙体；
- 仅修改 evidence 文档却不修 runtime。

---

# 17. Failure Classification

如果 fresh run 失败，按最便宜层定位。

## A. Offline manifest 错

修：

```text
spec / geometry / transform
```

但必须有明确 evidence 才能重新打开 geometry。

## B. Manifest 对，RflySim entity 不存在

修：

```text
loader / transition / UDP delivery / receipt ownership
```

## C. Entity 存在后消失

优先检查：

```text
late Destroy
cross-instance receipt
same-ID race
transition cleanup
```

## D. Entity 存在但尺寸错

检查：

```text
native asset size
sdk scale
motion update API
```

## E. Static 正常、dynamic 异常

只进入：

```text
motion controller / initial pose / scale persistence
```

不要动 corridor。

---

# 18. Git 策略

保持少量逻辑 commit。

建议：

```text
fix(map): isolate v2 runtime ownership by simulation instance

fix(map): make course transition upsert selected entities

fix(map): harden v2 static and dynamic entity delivery

test(map): require fresh-start retention before course ready

docs(evidence): re-close competition course v2 map gate
```

实际可以合并成 3–5 个。

不要制造大量碎 commit。

不要 push main。

---

# 19. Evidence 原则

旧 `MAP READY` evidence 不删除。

明确标记：

```text
SUPERSEDED BY FRESH-START FAILURE
```

新的 MAP READY evidence 必须至少包括：

```text
branch / commit
stack_id
simulation_instance_id
spec_sha256

fresh run 1
  probe A
  probe B
  screenshots

fresh run 2
  probe A
  probe B
  screenshots

dynamic obstacle scale + motion evidence
```

不要仅引用：

```text
load receipt
command count
process alive
```

作为地图存在的证据。

---

# 20. 最终完成标准

只有以下全部满足：

```text
offline validation PASS

fresh startup #1:
  complete tunnel visible
  static geometry correct
  dynamic dimensions correct
  dynamic motion correct
  retention A PASS
  retention B PASS

fresh startup #2:
  same conditions PASS

no manual hot reload needed
no cross-instance receipt cleanup
no selected-course Destroy/Create race
COURSE_READY depends on world-state evidence
```

才能声明：

# Competition Course V2 — MAP READY

到这里立刻停止地图开发。

下一阶段恢复：

```text
Competition Course V2 Navigation Baseline
```

从：

```text
current-instance no-arm
→ short smoke
→ Section A
```

继续。

---

# 21. 最终原则

本轮优先级：

```text
正确 live deployment
>
更多功能
>
更复杂架构
```

不要重写地图。

不要继续优化 Navigation。

不要用 sleep 掩盖错误 ownership。

核心目标只有一个：

> **让同一份已经验证过的 V2 specification，在两个独立 fresh RflySim instance 中都稳定生成同一张正确地图。**
