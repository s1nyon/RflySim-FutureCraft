# Stage 8 自有地图 Mid360 无点云问题记录（2026-08-02）

## 当前结论

Stage 8 的 Python 动态赛道可以在 RflySim3D 中显示，但 `VisionRingBlank` 上的 TypeID 23/Mid360 无法产生点云。FAST-LIO 窗口不是自行崩溃：`stage7_sensor_readiness.py` 等待 `/uav1/rflysim/lidar` 超时后返回失败，Stage 7 runner 随即主动结束整组 FAST-LIO 节点。

当前证据表明，`sendUE4PosScale` 创建的动态砖块地面和墙体没有进入 `VisionRingBlank` 的 Mid360 有效射线场景。继续增加动态物体或延长 readiness 超时不能解决问题。下一步需要制作包含静态地面、静态墙体和碰撞的自有 UE `.umap`，Cook 后部署到 RflySim3D。

## 已验证的现象

### 可用基线

- 基础地图：`ChallengeMap`
- run：`stage7-20260801T182428Z-2528`
- 结果：`ready=true`，五项 gate 全部通过。
- 两机每帧均接收 17,408 个点，雷达约 10 Hz。
- 两机均为 `armed=false`。

### VisionRingBlank 零动态物体对照

- run：`stage7-20260801T184340Z-2523`
- 只启动 `VisionRingBlank`、相同双机出生点，不调用赛道加载器。
- 结果：`timeout exceeded while waiting for message on topic /uav1/rflysim/lidar`。
- 这排除了赛道加载器和动态物体数量是唯一根因的可能性。

### VisionRingBlank 宽敞矩形动态赛场

- commit：`a5c9118 fix: ground and enclose predicted course`
- 场地包含约 30.8 m × 19.4 m 的连续动态地面、四面2.5 m高外墙、贴地狭窄通道、起降表面和平台，共31个对象。
- run：`stage7-20260801T185439Z-2525`
- instance：`px4-bc7622b2419e9775`
- 结果：`ready=false`，两机 `accepted_scans=0`、雷达时间戳为0。
- 两个 sensor bridge 均成功加载配置并启动，问题发生在 UE 点云回传边界。

### 重复切图问题

- commit：`de5d7a8 fix: preserve lidar while loading predicted course`
- 加载器默认不再发送 `RflyChangeMapbyName`，仅显式 `--change-map` 时切图。
- 该修复避免运行中重载关卡切断已有传感器，但不能使 `VisionRingBlank` 自身产生 Mid360 点云。

## 本机官方参考

以下 TypeID 23/Mid360 示例均使用 `ChallengeMap`：

- `D:\PX4PSP\RflySimAPIs\8.RflySimVision\0.ApiExps\10.Mid360Demo\SITLPosStr.bat`
- `D:\PX4PSP\RflySimAPIs\8.RflySimVision\0.ApiExps\4.Point-CloudVisualize\client_ue4_SITL.bat`

没有找到使用 `VisionRingBlank` 的官方 Mid360 示例；该地图主要出现在 RGB、分割和标定示例中。

## 当前代码状态

- 分支：`main`
- 相关提交：
  - `de5d7a8`：默认加载赛道时不重复切图。
  - `df26177`：记录雷达安全加载约束。
  - `a5c9118`：增加宽敞矩形动态场地、连续地面、外墙并将通道贴地。
- Stage 8 离线验证通过，但 live Mid360 验收失败。
- 不得将离线 PASS 描述为地图已经可用于雷达飞行。

## 明天的建议入口

1. 检查本机是否安装与 `D:\PX4PSP\RflySim3D` 匹配的 UE4 Editor，以及是否有可复用 `.uproject`。
2. 如果 Editor 可用，优先使用 UE Python API 根据 `config/maps/predicted_narrow_course_v1.json` 创建：
   - 静态连续地面；
   - 四面宽敞边界墙；
   - 贴地狭窄通道墙；
   - 起飞区、降落区和两个平台；
   - 所有静态网格启用简单碰撞。
3. 保存为独立地图名，例如 `PredictedNarrowCourseV1`，Cook 并保持 `/Game` 目录结构部署到 RflySim3D。
4. 在 `CopterSim\external\map` 创建同名16位 PNG 和 TXT 校准文件。
5. 将项目配置中的 `base_map` 和启动器改成新地图名，不在运行中切图。
6. 先运行单机/双机 no-arm Mid360 检查；只有新 run 的 readiness 五项 gate 全部通过才启动 EGO-Swarm。
7. topic probe 通过后，才允许执行 `--allow-arm --simulation-only`；失败时不得强制解锁。

## 不要重复的尝试

- 不要继续在 `VisionRingBlank` 中添加更多 `sendUE4PosScale` 动态墙体来期待 Mid360 恢复。
- 不要通过增大 readiness timeout 掩盖无点云。
- 不要在传感器运行时执行 `RflyChangeMapbyName`。
- 不要使用历史 readiness 报告通过新实例门禁。
- 用户明确要求使用自有地图，不要切换到 `ChallengeMap` 作为最终方案。
