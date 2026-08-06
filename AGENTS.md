# AGENTS.md

本仓库是 RflySim 双机协同仿真工程（FS-310 / PX4 SITL / MAVROS / Faster-LIO / EGO-Swarm）。动手前先了解项目背景、运行链路与安全门禁，不要凭 README 概况猜测着改。

## 开始任务前必读

- `.agents/AGENT2READ.md`：agent 执行规则、开发经验与关键坑（优先级最高）
- `README.md`：项目概览、启动流程、运行约束
- `docs/`：按任务范围查阅相关阶段记录

## 硬性规则

- 不修改 `28com_sim` 原工程；ROS 逻辑只放在 `future_aircraft_ws`。
- 多机命名空间固定为 `/uav1`、`/uav2`。
- 仿真解锁仅允许 `--allow-arm --simulation-only`；真实飞机保持人工 arm。
- 每次重启仿真视为新实例；no-arm readiness 五项门禁通过前不得启动规划或飞行。
- 传感器配置 JSON 必须是无注释纯 JSON（桥接脚本用 `json.loads` 校验）。
- 双机 FAST-LIO 坐标系相互独立：ego-swarm 轨迹广播不参与防撞决策，机间防撞依赖感知。
- 改动须同步更新 README / AGENT2READ / docs；提交到 `main` 分支并推送 GitHub。

## 验证

- 离线：`tests\` 回归 + `scripts\validate_stage*.ps1`。
- Live no-arm：`scripts\run_live_fastlio_dual.bat` → `scripts\run_live_ego_swarm_dual.bat` → `scripts\run_stage7_topic_probe.bat`。
- 仿真飞行：`scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`。
