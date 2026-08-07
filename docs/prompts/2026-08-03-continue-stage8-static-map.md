# 明天继续开发 Prompt

> **状态：已搁置（2026-08-07）。** 用户明确不安装 UE Editor；地图问题已用
> SLAMScene + 动态砖块方案临时解决（live 验证通过），本 prompt 中的
> UE 静态地图步骤不再执行。详见
> `docs/decisions/2026-08-07-no-ue-editor.md`。后续 live 直接走
> `scripts\start_predicted_course_two_uav.bat`，不要询问是否安装 UE。

请继续开发以下工程，直接在 `main` 分支工作：

`D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\future_aircraft_sim`

开始前完整阅读：

`docs/stage8_lidar_issue_2026-08-02.md`

目标是把当前 `VisionRingBlank + Python 动态砖块` 原型升级成真正可供 TypeID 23/Mid360 扫描的自有 UE 静态地图，并完成 live no-arm 验收；不要改用官方 `ChallengeMap` 作为最终地图。

已确认的事实：

- `ChallengeMap` 基线 run `stage7-20260801T182428Z-2528` 的双机 Mid360/FAST-LIO readiness 通过，两机每帧17,408点、约10 Hz。
- `VisionRingBlank` 零动态物体 run `stage7-20260801T184340Z-2523` 失败。
- 添加宽敞动态地面和四面外墙后，run `stage7-20260801T185439Z-2525` 仍然 `accepted_scans=0`。
- 因此不要再尝试靠 `sendUE4PosScale` 动态地面/墙体修复 Mid360，也不要只增加超时。
- FAST-LIO 窗口退出是 readiness 失败后的主动清理，不是 FAST-LIO 自身随机闪退。

当前相关提交：

- `de5d7a8 fix: preserve lidar while loading predicted course`
- `df26177 docs: explain lidar-safe course loading`
- `a5c9118 fix: ground and enclose predicted course`

当前几何要求继续保留：

- 完整矩形比赛场地，不能围得太小。
- 当前约30.8 m × 19.4 m，赛道包围盒四周约5 m安全空间。
- 四面外墙高2.5 m。
- 狭窄通道墙、地面、起降表面和平台必须贴地。
- 通道净宽1.4–1.5 m、长度大于3 m、转弯半径不大于1 m。
- 至少两架无人机，出生点不能重叠。

请按以下顺序执行：

1. 先检查本机 UE4 Editor/UE4Editor-Cmd、注册表安装位置以及可复用 `.uproject`。RflySim3D 是 UE4 运行时，Cook 版本必须匹配，不能拿 UE5 资源混用。
2. 如果 UE4 Editor 可用，创建或复用最小工程，并优先用 UE Python API 从 `config/maps/predicted_narrow_course_v1.json` 生成静态网格 Actor。所有地面和墙体必须具有简单碰撞，并保存为独立关卡 `PredictedNarrowCourseV1.umap`。
3. 使用项目提供的 UE4 配置检查/Cook 流程，确保 `Use Pak File=False`、`Share Material Shader Code=False`，检查外部资源和碰撞。
4. 将 Cooked Content 按 `/Game` 原目录结构部署到 `D:\PX4PSP\RflySim3D\RflySim3D\Content`。
5. 在 `D:\PX4PSP\CopterSim\external\map` 生成同名 `PredictedNarrowCourseV1.png` 与 `PredictedNarrowCourseV1.txt`；平地高度图使用16位常值32768并按实际场地范围校准。
6. 更新工程 spec/启动入口使用新地图名。地图只在仿真启动时选择，运行中不得调用 `RflyChangeMapbyName`。
7. 运行离线验证，然后精确关闭本项目旧 `cmd /k` 窗口、RflySim3D、CopterSim、PX4 和对应 WSL 实例，启动全新双机仿真。
8. 运行 `scripts\run_live_fastlio_dual.bat`，读取本次新 run 的 `sensor_readiness.json`。要求两机雷达时间戳非零、点云 schema 正确、五项 gate 全部 `pass`、两机 `armed=false`。
9. readiness 未通过就停止并分析日志，不得继续解锁。通过后再启动 EGO-Swarm 和 `scripts\run_stage7_topic_probe.bat`。
10. 只有 topic probe 的 flight gate 通过，才执行：

```bat
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only
```

最终报告必须确认 `collision_count=0`、`offboard_loss=0`、`timeout=0`，两机均已降落并解除解锁。

开发要求：

- 先检查证据再修改，不要重复今天已经排除的路线。
- 采用 TDD；生产代码修改前先写能复现缺陷的失败测试。
- 保留用户现有修改，只处理本任务相关文件。
- 每次 live 使用全新的 simulation instance ID 和 run ID，不复用历史报告。
- 在结论中明确区分“离线验证通过”和“真实 live Mid360/飞行验收通过”。
