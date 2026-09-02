# Script Inventory

每个保留的 tracked script 必须且只能出现在下列一个分类表中。Public entry 可由开发者直接调用；Protected internal 由受支持入口委托或属于冻结 live 链；Focused diagnostic 用于限定范围的检查；Hazard-disabled 是安全墓碑；Historical compatibility 仍被回归链消费但不是新工作的首选入口。

## Public entry

| Path | Purpose |
| --- | --- |
| `scripts/end_live_stack.ps1` | 受支持的 Stage 7 收尾与 manifest stop 入口。 |
| `scripts/live_stack_fresh_instance.ps1` | Manifest 化 fresh-instance 编排，默认 DryRun。 |
| `scripts/live_stack_inspect.ps1` | 当前 stack 的只读 ownership/health 检查。 |
| `scripts/live_stack_retire_stale.ps1` | 已证明死亡 stack 的显式 stale ownership metadata retirement；默认 DryRun、零进程信号。 |
| `scripts/live_stack_start.ps1` | Manifest 化 live stack 启动入口。 |
| `scripts/live_stack_stop.ps1` | Manifest-only graceful stop，默认 DryRun。 |
| `scripts/run_live_ego_swarm_dual.bat` | 当前双机 EGO-Swarm runner。 |
| `scripts/run_live_fastlio_dual.bat` | 当前双机 sensor/Faster-LIO readiness runner。 |
| `scripts/run_live_slam_ego_swarm_flight.bat` | 显式 simulation-only arming 的 PBL-1 flight runner。 |
| `scripts/run_competition_course_v2_navigation.bat` | Competition Course V2 的 UAV1 Section A opt-in runner；live 必须显式 stack/manifest 与 simulation arm flags。 |
| `scripts/run_rflysim_rviz.bat` | 可选的 per-UAV/dual RViz 调试入口，不参与 READY 或控制链。 |
| `scripts/validate_asset_calibration.ps1` | 官方模型标定场的纯离线契约与 DryRun 验证入口。 |
| `scripts/validate_competition_course_v2.ps1` | Competition Course V2 的基底、精确 ID 切换、净空、确定性产物、评价参考、loader 与 DryRun 总入口。 |
| `scripts/validate_competition_course_v2_navigation.ps1` | UAV1 Section A plan、executor opt-in、recorder/report、runner 与 map parity 的纯离线总入口。 |
| `scripts/validate_lifecycle.ps1` | Lifecycle 离线回归入口。 |
| `scripts/validate_repository.ps1` | Repository、文档和结构 contract 总入口。 |
| `scripts/validate_stage6c.ps1` | 当前 Stage 6C 核心离线门。 |
| `scripts/validate_stage6d.ps1` | 当前 Stage 6D no-arm 核心离线门。 |
| `scripts/validate_stage7.ps1` | 当前 Stage 7 核心离线门。 |
| `scripts/validate_stage8.ps1` | 当前 Stage 8 核心离线门。 |

## Protected internal

| Path | Purpose |
| --- | --- |
| `scripts/calibration/__init__.py` | 官方模型标定 Python package marker。 |
| `scripts/calibration/asset_catalog.py` | 官方模型候选目录、schema 与 checksum 纯校验。 |
| `scripts/calibration/calibration_artifacts.py` | 标定场确定性 JSON/SVG 产物生成器。 |
| `scripts/calibration/calibration_cli.py` | DryRun-first 标定命令分发器。 |
| `scripts/calibration/calibration_geometry.py` | 标定站位、净距与 ENU/NED 坐标纯几何。 |
| `scripts/calibration/object_metadata.py` | RflySim `BoxExtent` 元数据标准化与证据状态分析。 |
| `scripts/calibration/showcase_geometry.py` | 近场官方模型展台规格、缩放与出生点净距纯几何。 |
| `scripts/calibration/showcase_artifacts.py` | 近场展台确定性 JSON/SVG 预览与清单生成。 |
| `scripts/calibration/ue_asset_loader.py` | 仅作用于标定 owned ID 的官方模型加载/移除实现。 |
| `scripts/deploy_predicted_course_terrain.bat` | 当前赛道 terrain 部署 helper。 |
| `scripts/deploy_competition_course_v2_terrain.bat` | Competition Course V2 可逆 terrain 部署 helper。 |
| `scripts/generate_competition_course_v2.bat` | Competition Course V2 确定性生成 helper。 |
| `scripts/generate_predicted_narrow_course.bat` | 当前赛道确定性生成 helper。 |
| `scripts/load_competition_course_v2.bat` | Competition Course V2 stack-scoped idempotent upsert / unload helper（live 需要 `--stack-id` 与 `--simulation-instance-id`）。 |
| `scripts/load_predicted_narrow_course.bat` | 当前 RflySim 动态赛道加载 helper。 |
| `scripts/start_competition_course_v2_two_uav.bat` | 显式选择 Competition Course V2 的双机启动 helper。 |
| `scripts/start_predicted_course_two_uav.bat` | 当前双机赛道启动链 helper。 |
| `scripts/transition_project_course_layer.bat` | 从 tracked map specs 派生精确实体 ID 的新旧赛道互斥切换 helper；不做 ID range sweep。 |
| `scripts/start_rflysim_sitl_two.bat` | 当前双机 RflySim/PX4 启动 helper。 |
| `scripts/start_two_uav.bat` | 当前双机基础启动 helper。 |
| `scripts/start_wsl_mavros_two.bat` | 当前双 MAVROS/health-gate 启动 helper。 |
| `scripts/lifecycle/__init__.py` | Lifecycle Python package marker。 |
| `scripts/lifecycle/fresh_instance.py` | Fresh-instance 状态机。 |
| `scripts/lifecycle/generate_sitl_wrapper.ps1` | Stack-scoped SITL wrapper 生成器。 |
| `scripts/lifecycle/health_gate.py` | Live stack health gate。 |
| `scripts/lifecycle/health_probe.py` | Lifecycle health producer/probe。 |
| `scripts/lifecycle/launch_stage2.ps1` | Lifecycle 管理的 Stage 2 launcher。 |
| `scripts/lifecycle/process_table.py` | Windows/WSL 进程身份读取。 |
| `scripts/lifecycle/register_launcher.py` | 创建时登记 Windows launcher。 |
| `scripts/lifecycle/run_wsl_bounded.ps1` | 有界 WSL 调用 helper。 |
| `scripts/lifecycle/spawn_attest.py` | PX4 spawn-attested ownership 证明。 |
| `scripts/lifecycle/stack_inspect.py` | Manifest ownership 与冲突检查核心。 |
| `scripts/lifecycle/stack_manifest.py` | Stack manifest schema/identity 核心。 |
| `scripts/lifecycle/stack_ownership.py` | Ownership 判定核心。 |
| `scripts/lifecycle/stack_register.py` | 创建时 ownership 唯一登记入口。 |
| `scripts/lifecycle/stack_retire_stale.py` | Pre-existing PID reuse 的双快照、token-bound metadata retirement 核心；不包含 stop backend。 |
| `scripts/lifecycle/stack_stop.py` | Manifest-only graceful stop 核心。 |
| `scripts/lifecycle/stack_topology.py` | 双机 stack topology contract。 |
| `scripts/lifecycle/to_wsl_path.ps1` | Windows 到 WSL 路径转换 helper。 |
| `scripts/run_live_stack_start_bg.ps1` | 后台启动 `live_stack_start.ps1` 并捕获输出，供受控 Gate 轮询使用。 |
| `scripts/maintenance/clean_logs.ps1` | `sim.ps1 clean-logs` 的有界内部实现。 |
| `scripts/maintenance/curate_pbl1_evidence.py` | PBL-1 三次批准 run 的确定性证据整理与脱敏实现。 |
| `scripts/python_contract_runner.ps1` | PowerShell validator 的 Python contract helper。 |
| `scripts/sim_cli.psm1` | 根 `sim.ps1` 的委托实现。 |
| `scripts/wsl/build_future_aircraft_ws.sh` | `sim.ps1 build` 的 WSL Catkin helper。 |
| `scripts/wsl/cleanup_stage7_flight_chain.sh` | 当前 stack-scoped Stage 7 flight-chain 收尾。 |
| `scripts/wsl/competition_course_v2_navigation.sh` | UAV1 Section A 的 stack/instance fail-closed WSL runner；只创建 UAV1 控制进程与只读 evidence 进程。 |
| `scripts/wsl/lifecycle_common.sh` | WSL 创建时 PID/PGID 登记公共函数。 |
| `scripts/wsl/live_stack_wsl_ops.sh` | WSL stack inspect/stop 显式 PID 操作。 |
| `scripts/wsl/rviz_live.sh` | Lifecycle-owned RViz WSL session wrapper。 |
| `scripts/wsl/stage2_health_check.sh` | 当前双机 ROS/MAVROS health 检查。 |
| `scripts/wsl/stage2_two_mavros.sh` | 当前双 MAVROS WSL 启动链。 |
| `scripts/wsl/stage6d_live_no_arm_smoke.sh` | 当前 Stage 6D no-arm WSL 实现。 |
| `scripts/wsl/stage7_live_ego_swarm_dual.sh` | 当前双机 EGO-Swarm WSL 实现。 |
| `scripts/wsl/stage7_live_fastlio_dual.sh` | 当前双机 Faster-LIO/readiness WSL 实现。 |
| `scripts/wsl/stage7_live_slam_ego_swarm_flight.sh` | 当前 simulation-only flight WSL 实现。 |
| `scripts/wsl/stage7_run_context.sh` | Run/instance scoped artifact context。 |

## Focused diagnostic

| Path | Purpose |
| --- | --- |
| `scripts/run_stage2_1_mavlink_check.bat` | 单机 MAVLink 回程诊断。 |
| `scripts/run_stage7_topic_probe.bat` | Stage 7 只读 topic/readiness probe。 |
| `scripts/run_stage8_control_chain_recorder.bat` | Stage 8 只读控制链记录器。 |
| `scripts/capture_rflysim_window.ps1` | 只读 RflySim3D 主窗口截图 helper（map acceptance evidence）。 |
| `scripts/rflysim_view_cmd.py` | 只读 RflySim3D view/capture 命令 helper（map acceptance evidence）。 |
| `scripts/start_mavros_uav1.bat` | UAV1 MAVROS focused helper。 |
| `scripts/start_mavros_uav2.bat` | UAV2 MAVROS focused helper。 |
| `scripts/start_rflysim_sitl_single.bat` | 单机 SITL focused helper。 |
| `scripts/start_single_uav.bat` | Stage 1 单机 focused launcher。 |
| `scripts/start_vcxsrv.bat` | WSL/GUI focused startup helper。 |
| `scripts/start_wsl_ros_single.bat` | Stage 1 单机 ROS focused helper。 |
| `scripts/validate_stage1.ps1` | Stage 1 focused validator。 |
| `scripts/validate_stage2.ps1` | Stage 2 focused validator。 |
| `scripts/validate_stage2_1.ps1` | Stage 2.1 focused validator。 |
| `scripts/validate_stage4.ps1` | EGO integration focused validator。 |
| `scripts/wsl/stage1_single_uav.sh` | Stage 1 single-UAV WSL diagnostic helper。 |
| `scripts/wsl/stage2_1_single_mavlink_check.sh` | Stage 2.1 WSL MAVLink diagnostic。 |
| `scripts/wsl/stage8_chain_recorder_once.sh` | Stage 8 recorder one-shot WSL helper。 |

## Hazard-disabled

| Path | Purpose |
| --- | --- |
| `scripts/cleanup_sim_stack.ps1` | HAZARD-DISABLED fail-fast tombstone；不得恢复名称扫杀。 |
| `scripts/restart_live_stack.ps1` | HAZARD-DISABLED fail-fast tombstone；不得恢复硬重启循环。 |

## Historical compatibility

| Path | Purpose |
| --- | --- |
| `scripts/create_log_run.bat` | Stage 3→5→6 validator chain 仍消费的日志 helper。 |
| `scripts/run_live_no_arm_smoke.bat` | Stage 6D 兼容 runner。 |
| `scripts/run_live_sim_arm.bat` | Stage 6E simulation-arm 兼容 runner。 |
| `scripts/start_mission.bat` | 早期 mission wrapper，保留供回归链。 |
| `scripts/start_mission_executor_sim_arm.bat` | Stage 5E executor 兼容 wrapper。 |
| `scripts/validate_stage3.ps1` | Stage 3 logging/scoring 回归依赖。 |
| `scripts/validate_stage5.ps1` | Stage 5 behavior-tree 回归依赖。 |
| `scripts/validate_stage5b.ps1` | Stage 5B contract 回归依赖。 |
| `scripts/validate_stage5c.ps1` | Stage 5C executor 回归依赖。 |
| `scripts/validate_stage5d.ps1` | Stage 5D smoke 回归依赖。 |
| `scripts/validate_stage5e.ps1` | Stage 5E simulation-arm 回归依赖。 |
| `scripts/validate_stage6a.ps1` | Stage 6A target-provider 回归依赖。 |
| `scripts/validate_stage6b.ps1` | Stage 6B vision-provider 回归依赖。 |
| `scripts/wsl/stage5e_executor_sim_arm.sh` | Stage 5E WSL 兼容实现。 |
| `scripts/wsl/stage6e_live_sim_arm.sh` | Stage 6E WSL 兼容实现。 |
