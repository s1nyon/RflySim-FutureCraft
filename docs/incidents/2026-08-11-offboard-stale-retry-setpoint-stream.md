# OFFBOARD 无法确认：旧栈重试 + setpoint 流中断（2026-08-11）

> 状态：**RESOLVED**（fresh-instance 后 armed live 飞行 PASS，见
> `../evidence/2026-08-11-live-import-and-pwsh-compat-armed-verified.md`）

## 1. 症状

run `stage7-20260810T173607Z-2745`（旧栈 `stack-20260810T173509Z-b096fe72`）：

```
[ERROR] OFFBOARD mode not confirmed for uav1 within 10.0s;
        last_state=connected=True armed=False mode=MANUAL
```

`mission_events.jsonl`：`set_mode OFFBOARD` 服务返回 `ros_success`
（MAVROS `mode_sent=true`），但 PX4 10s 内保持 MANUAL；两机全程未 arm。

## 2. 诊断

- readiness 五门全 PASS，topic/service 全部 available —— 不是 readiness 或 ROS 图问题。
- `ego_swarm_setpoint_bridge.py`（keepalive）在 `flight_runner` 的 EXIT trap 中会被
  `cleanup_keepalive` 杀掉；首轮 flight runner 失败退出后，其 keepalive 已死。
- 旧栈上第二轮 flight 是「同一个旧栈 + 20+ 分钟窗口 + ego 重启」后的重试，
  与 PBL-1 的「fresh 栈 → fastlio → ego → flight 背靠背」流程不符。
- executor 的 warmup setpoints 在 seq4（uav2 warmup）期间结束，uav1 的
  setpoint 流如果只有 executor 在发，则在 `set_mode OFFBOARD` 时刻已停；
  PX4 需要持续 setpoint 流才能进入/保持 OFFBOARD，缺失时回退 MANUAL。

## 3. 根因

不是代码回归（PBL-1 后 mission 脚本仅 ego-planner-swarm 路径重命名）。
是运行环境/时序问题：旧栈重试窗口内 keepalive setpoint 流中断，
OFFBOARD 转换时 PX4 收不到连续 setpoint。

## 4. 修复与验证

- 完整清理旧栈（manifest stop + 显式 PID 补清 + 删除 scheduled task）。
- fresh 栈按背靠背顺序：fastlio（readiness ros 后端 PASS）→ ego → armed flight。
- 结果：双机 OFFBOARD 各 ~0.5s 确认、arm、起飞、14/14 导航、降落，`success=true`。

## 5. 可复用经验

- 不要在同一旧栈上反复重试；失败后走「完整清理 → fresh-instance」。
- 出现 OFFBOARD 不确认时，先查 `/uavX/mavros/setpoint_raw/local` 是否仍有
  keepalive 在发（`rostopic hz`），再查 PX4 状态，不要动 planner/EGO 调参。
