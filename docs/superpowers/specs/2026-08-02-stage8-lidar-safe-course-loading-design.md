# Stage 8 雷达安全赛道加载设计

## 背景

预测赛道启动器已经通过 `RFLYSIM_UE4_MAP` 选择 `VisionRingBlank`，但动态赛道加载器随后再次发送 `RflyChangeMapbyName VisionRingBlank`。实机链路复现实验表明，执行该命令前双机点云约为 10 Hz，执行后两路点云立即停止；ROS 发布者仍存在，但不再收到 UE 数据。readiness 随后因等待 `/uav1/rflysim/lidar` 超时而主动关闭 FAST-LIO launch。

## 目标

- 预测赛道正常加载时不重载 UE 关卡。
- 保留加载器在传感器启动前显式切图的独立调试能力。
- 用自动化测试防止默认切图行为回归。
- 用真实双机 no-arm 门禁证明赛道和激光雷达能够同时工作。
- 仅在全部安全门禁通过后执行仿真解锁飞行。

## 设计

### 加载器接口

`load_scene` 增加 `change_map` 布尔参数，默认值为 `False`。默认路径只执行以下操作：

1. 按赛道拥有的 ID 范围清理旧动态物体。
2. 使用 `sendUE4PosScale` 放置赛道物体。
3. 返回加载回执，其中记录是否请求了关卡切换。

只有命令行显式传入 `--change-map` 时，加载器才会先发送 `RflyChangeMapbyName <base_map>` 并等待关卡加载。该模式仅用于传感器启动前的人工调试，不进入标准双机启动链路。

### 启动链路

`start_predicted_course_two_uav.bat` 保持现有职责：

1. 生成并验证赛道数据。
2. 通过 `RFLYSIM_UE4_MAP=VisionRingBlank` 启动完整双机栈。
3. 调用默认的对象加载模式，将26个动态赛道物体放入已经加载的关卡。

因此基础地图只在仿真进程启动时选择一次，动态加载阶段不再触发关卡生命周期重置。

## 测试

按照 TDD 顺序修改：

1. 先把加载器测试改为断言默认调用不发送地图命令，并观察测试因现有行为失败。
2. 增加显式 `change_map=True` 的测试，验证独立调试能力仍然可用。
3. 实现最小代码使两项测试通过。
4. 运行 `scripts/validate_stage8.ps1` 和 `scripts/validate_stage7.ps1`。
5. 精确关闭本项目残留终端和仿真进程，重新启动预测赛道。
6. 运行双机 FAST-LIO no-arm readiness，要求两机点云均有新鲜数据且全部门禁通过。
7. 运行 EGO-Swarm 和 Stage 7 topic probe；只有门禁通过才运行带 `--allow-arm --simulation-only` 的双机短航段。

## 安全与失败处理

- 默认模式不得发送任何关卡切换命令。
- no-arm readiness 或 topic probe 任一失败时立即停止，不尝试解锁。
- 飞行只允许连接 PX4 SITL 的仿真实例。
- 验收报告必须确认两机最终落地并解除解锁，且碰撞、OFFBOARD 丢失和超时计数均为零。

## 非目标

- 本修复不改变赛道几何、尺寸、材质或障碍物布局。
- 不修改 FAST-LIO、点云格式或 UDP 端口。
- 不为运行中的关卡热切换实现传感器自动重建。
