# Stage 8 雷达安全赛道加载实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让预测赛道默认只加载动态物体，避免重复 UE 关卡切换中断双机激光雷达，并完成一次门禁保护下的仿真短航段。

**Architecture:** 基础地图继续由双机启动器通过 `RFLYSIM_UE4_MAP` 选择。`narrow_course_ue_loader.py` 将关卡切换变成显式可选行为，默认仅清理项目拥有的对象 ID 并放置赛道；现有 Stage 7 readiness、topic probe 和 flight runner 负责实时安全验收。

**Tech Stack:** Python 3.8、RflySim `UE4CtrlAPI`、PowerShell、Windows batch、ROS Noetic/WSL、PX4 SITL。

## Global Constraints

- 默认赛道加载不得发送 `RflyChangeMapbyName`。
- `--change-map` 只保留给传感器启动前的人工调试，不进入标准双机启动链路。
- 不修改赛道几何、FAST-LIO、点云格式或 UDP 端口。
- readiness 或 topic probe 任一失败时不得解锁。
- 飞行只允许使用 `--allow-arm --simulation-only`，并要求最终双机落地、解除解锁且碰撞、OFFBOARD 丢失和超时均为零。

---

### Task 1: 将关卡切换改为显式可选行为

**Files:**
- Modify: `tests/stage8_course_ue_loader_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_ue_loader.py:45-140`

**Interfaces:**
- Consumes: `CourseModel.base_map`、现有 `UE4CtrlAPI.sendUE4Cmd/sendUE4Destroy/sendUE4PosScale`。
- Produces: `load_scene(client, model, clear_first, window_id, change_map=False) -> Dict[str, object]`；命令行参数 `--change-map`；回执字段 `change_map: bool`。

- [ ] **Step 1: 写默认不切图的失败测试**

把默认加载断言改为：

```python
receipt = loader.load_scene(client, model, clear_first=True, window_id=0)
assert client.map_commands == []
assert receipt["change_map"] is False
```

- [ ] **Step 2: 运行测试并确认正确失败**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_ue_loader_check.py --geometry-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --loader-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_ue_loader.py --spec config\maps\predicted_narrow_course_v1.json
```

Expected: FAIL，因为当前实现仍发送 `RflyChangeMapbyName VisionRingBlank`。

- [ ] **Step 3: 写显式切图契约测试**

使用第二个 `FakeUEClient` 调用：

```python
explicit_client = FakeUEClient()
explicit_receipt = loader.load_scene(
    explicit_client,
    model,
    clear_first=False,
    window_id=2,
    change_map=True,
)
assert explicit_client.map_commands == [("RflyChangeMapbyName VisionRingBlank", 2)]
assert explicit_receipt["change_map"] is True
```

同时断言 dry-run 默认回执的 `change_map` 为 `False`，使用 `--change-map` 的第二次 dry-run 回执为 `True`。

- [ ] **Step 4: 写最小实现**

将加载函数改为：

```python
def load_scene(
    client,
    model: CourseModel,
    clear_first: bool,
    window_id: int,
    change_map: bool = False,
) -> Dict[str, object]:
    commands = build_ue_commands(model)
    if change_map:
        client.sendUE4Cmd("RflyChangeMapbyName {}".format(model.base_map), window_id)
        time.sleep(3.0)
```

向 argparse 添加：

```python
parser.add_argument("--change-map", action="store_true")
```

在 live 和 dry-run 回执中写入 `"change_map": args.change_map`，并将 `args.change_map` 传给 `load_scene`。

- [ ] **Step 5: 运行加载器测试并确认通过**

Run: 使用 Step 2 的同一命令。

Expected: `stage8 course UE loader: PASS`。

- [ ] **Step 6: 运行 Stage 8 验证并提交代码**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: `[PASS] Stage 8 predicted narrow course offline validation PASS`。

Commit:

```powershell
git add tests/stage8_course_ue_loader_check.py future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_ue_loader.py
git commit -m "fix: preserve lidar while loading predicted course"
```

---

### Task 2: 记录安全加载约束

**Files:**
- Modify: `README.md:98-118`

**Interfaces:**
- Consumes: Task 1 的默认对象加载行为和 `--change-map` 参数。
- Produces: 操作者可执行的启动顺序与热切图警告。

- [ ] **Step 1: 更新 Stage 8 运行说明**

在 Stage 8 说明中明确：标准入口由启动脚本选择基础地图，加载器默认不切图；运行中使用 `--change-map` 会销毁 RflySim 传感器捕获状态，必须在传感器启动前使用。

- [ ] **Step 2: 检查文档和提交**

Run:

```powershell
git diff --check
git diff -- README.md
```

Expected: 无空白错误，文字与设计一致。

Commit:

```powershell
git add README.md
git commit -m "docs: explain lidar-safe course loading"
```

---

### Task 3: 离线回归验证

**Files:**
- Verify: `scripts/validate_stage8.ps1`
- Verify: `scripts/validate_stage7.ps1`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的已提交工作树。
- Produces: Stage 8 与 Stage 7 完整离线验证证据。

- [ ] **Step 1: 运行完整 Stage 8 验证**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: Stage 8 PASS，且其内嵌 Stage 7 回归也 PASS。

- [ ] **Step 2: 检查 Git 状态**

Run:

```powershell
git status --short --branch
```

Expected: `main` 仅领先远端，无未提交源码修改。

---

### Task 4: 实时 no-arm 与仿真飞行验收

**Files:**
- Runtime output: `logs/stage7_live/<run-id>/sensor_readiness.json`
- Runtime output: `logs/stage7_live/topic_probe_report.json`
- Runtime output: `logs/stage7_live/<run-id>/flight_report.json`

**Interfaces:**
- Consumes: `scripts/start_predicted_course_two_uav.bat`、Stage 7 四个 live runner。
- Produces: 同一新仿真实例和 run ID 下的传感器、规划与飞行验收报告。

- [ ] **Step 1: 精确清理并重启预测赛道**

关闭本项目残留 `cmd /k` 窗口及 RflySim3D、CopterSim、PX4、QGroundControl，终止 `RflySim-20.04` 后执行：

```powershell
cmd /c scripts\start_predicted_course_two_uav.bat
```

确认两机均为 `connected=True`、`armed=False`、`MANUAL`。

- [ ] **Step 2: 运行新的 FAST-LIO no-arm readiness**

Run:

```powershell
cmd /c scripts\run_live_fastlio_dual.bat
```

读取新 run ID 对应报告，要求 `ready=true`，五项 gate 全部 `pass`，两机点云均有非零时间戳且 `armed=false`。

- [ ] **Step 3: 启动 EGO-Swarm 并执行只读 topic probe**

Run:

```powershell
cmd /c scripts\run_live_ego_swarm_dual.bat
cmd /c scripts\run_stage7_topic_probe.bat
```

要求报告中的 `sensor_bridge`、`fast_lio`、`mavros`、`ego_swarm` 和 `flight_gate` 全部就绪。

- [ ] **Step 4: 仅在门禁通过后执行仿真短航段**

Run:

```powershell
cmd /c scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

若任何前置门禁失败，跳过此步骤。成功报告必须满足 `ready=true`、`collision_count=0`、`offboard_loss=0`、`timeout=0`，并确认两机最终降落和解除解锁。

- [ ] **Step 5: 最终安全状态与工作树检查**

读取两机 `/mavros/state`，要求 `armed=False`；运行 `git status --short --branch`，报告实际结果，不以历史报告代替本次证据。
