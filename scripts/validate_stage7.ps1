param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'config/stage7_live_slam_ego_swarm.json',
    'config/rflysim_sensor_uav1.json',
    'config/rflysim_sensor_uav2.json',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_mavros_px4.launch',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch',
    'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_setpoint_bridge.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mavros_setpoint_keepalive.py',
'future_aircraft_ws/src/multi_uav_mission/scripts/odom_frame_relay.py',
'future_aircraft_ws/src/multi_uav_mission/scripts/odom_tf_contract_check.py',
'future_aircraft_ws/src/multi_uav_mission/scripts/flight_event_recorder.py',
'future_aircraft_ws/src/multi_uav_mission/scripts/check_swarm_obstacle.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_run_artifacts.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py',
    'tests/stage7_cloud_contract_check.py',
    'tests/stage7_dual_sensor_config_check.py',
    'tests/stage7_flight_artifact_check.py',
'tests/stage7_goal_delivery_check.py',
'tests/stage7_executor_failure_artifact_check.py',
    'tests/stage7_probe_flow_check.py',
    'tests/stage7_quadrotor_msgs_overlay_check.py',
    'tests/stage7_persistent_navigation_subscriber_check.py',
    'tests/stage7_provenance_check.py',
'tests/stage7_planner_control_bridge_check.py',
'tests/stage7_sensor_readiness_check.py',
'tests/stage8_odom_tf_contract_check.py',
'tests/stage7_flight_event_recorder_check.py',
'tests/stage7_swarm_obstacle_check.py',
    'scripts/run_live_fastlio_dual.bat',
    'scripts/run_live_ego_swarm_dual.bat',
    'scripts/run_stage7_topic_probe.bat',
    'scripts/run_live_slam_ego_swarm_flight.bat',
    'scripts/wsl/stage7_live_fastlio_dual.sh',
    'scripts/wsl/stage7_live_ego_swarm_dual.sh',
    'scripts/wsl/stage7_run_context.sh',
    'scripts/wsl/stage7_live_slam_ego_swarm_flight.sh'
)

$missing = @()
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) {
        $missing += $relativePath
    }
}

$contractErrors = @()
$configPath = Join-Path $ProjectRoot 'config/stage7_live_slam_ego_swarm.json'

function Assert-NamespacedValue {
    param(
        [string]$Context,
        [string]$Namespace,
        [string]$Field,
        [string]$Value
    )
    if (-not $Value.StartsWith("$Namespace/")) {
        $script:contractErrors += "${Context}.${Field} must be under namespace ${Namespace}: ${Value}"
    }
}

function Assert-NoBannedText {
    param(
        [string]$RelativePath,
        [string[]]$BannedPatterns
    )
    $fullPath = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        return
    }
    $text = Get-Content -Raw -LiteralPath $fullPath
    foreach ($pattern in $BannedPatterns) {
        if ($text -match $pattern) {
            $script:contractErrors += "$RelativePath must not reference banned Stage 7 flow pattern: $pattern"
        }
    }
}

function Assert-LfOnly {
    param([string]$RelativePath)
    $fullPath = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        return
    }
    $bytes = [System.IO.File]::ReadAllBytes($fullPath)
    for ($i = 0; $i -lt ($bytes.Length - 1); $i++) {
        if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) {
            $script:contractErrors += "$RelativePath must use LF line endings for WSL execution"
            break
        }
    }
}

if (Test-Path -LiteralPath $configPath) {
    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    if ($config.mission_mode -ne 'live_slam_ego_swarm_flight') {
        $contractErrors += "mission_mode must be live_slam_ego_swarm_flight"
    }
    if ($config.simulation_arm_policy.mode -ne 'simulation_only') {
        $contractErrors += "simulation_arm_policy.mode must be simulation_only"
    }
    foreach ($flag in @('--allow-arm', '--simulation-only')) {
        if ($config.simulation_arm_policy.required_flags -notcontains $flag) {
            $contractErrors += "simulation_arm_policy.required_flags must include $flag"
        }
    }

    if ($config.uavs.Count -ne 2) {
        $contractErrors += "uavs must contain exactly two entries"
    }

    $expectedNamespaces = @{
        uav1 = '/uav1'
        uav2 = '/uav2'
    }
    $expectedOdomOut = @{
        uav1 = '/uav1/mavros/odometry/out'
        uav2 = '/uav2/mavros/odometry/out'
    }
    $expectedPlannerCmd = @{
        uav1 = '/uav1/planning/pos_cmd'
        uav2 = '/uav2/planning/pos_cmd'
    }
    $expectedSetpoint = @{
        uav1 = '/uav1/mavros/setpoint_raw/local'
        uav2 = '/uav2/mavros/setpoint_raw/local'
    }

    foreach ($uav in $config.uavs) {
        $uavId = [string]$uav.uav_id
        if (-not $expectedNamespaces.ContainsKey($uavId)) {
            $contractErrors += "unexpected uav_id: $uavId"
            continue
        }
        $namespace = $expectedNamespaces[$uavId]
        if ($uav.namespace -ne $namespace) {
            $contractErrors += "${uavId}.namespace must be $namespace"
        }
        if ($uav.slam_odom_to_fcu_topic -ne $expectedOdomOut[$uavId]) {
            $contractErrors += "${uavId}.slam_odom_to_fcu_topic must be $($expectedOdomOut[$uavId])"
        }
        if ($uav.planner_cmd_topic -ne $expectedPlannerCmd[$uavId]) {
            $contractErrors += "${uavId}.planner_cmd_topic must be $($expectedPlannerCmd[$uavId])"
        }
        if ($uav.mavros_setpoint_topic -ne $expectedSetpoint[$uavId]) {
            $contractErrors += "${uavId}.mavros_setpoint_topic must be $($expectedSetpoint[$uavId])"
        }
        $expectedDroneId = @{ uav1 = 0; uav2 = 1 }[$uavId]
        if ($uav.planner_bspline_topic -ne "/drone_${expectedDroneId}_planning/bspline") {
            $contractErrors += "${uavId}.planner_bspline_topic must be /drone_${expectedDroneId}_planning/bspline"
        }
        foreach ($field in @(
            'slam_namespace',
            'slam_odom_topic',
            'slam_cloud_topic',
            'planner_odom_topic',
            'planner_cloud_topic',
            'planner_cmd_topic',
            'planner_goal_topic',
            'planner_trigger_topic',
            'mavros_state_topic',
            'mavros_setpoint_topic',
            'mavros_set_mode_service',
            'mavros_arming_service'
        )) {
            Assert-NamespacedValue -Context $uavId -Namespace $namespace -Field $field -Value ([string]$uav.$field)
        }
        if ($config.fast_lio.sensor_topic_scope -ne 'shared_rflysim_bridge') {
            foreach ($field in @('sensor_lidar_topic', 'sensor_imu_topic')) {
                Assert-NamespacedValue -Context $uavId -Namespace $namespace -Field $field -Value ([string]$uav.$field)
            }
        }
    }
}

$bannedPatterns = @(
    'object_det',
    'target_provider',
    'behavior_tree',
    'basic_test\.launch',
    'bt_ros',
    'detection\.launch'
)
$runtimeScanPaths = @(
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_mavros_px4.launch',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch',
    'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_setpoint_bridge.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mavros_setpoint_keepalive.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/odom_frame_relay.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_run_artifacts.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py',
    'scripts/run_live_fastlio_dual.bat',
    'scripts/run_live_ego_swarm_dual.bat',
    'scripts/run_stage7_topic_probe.bat',
    'scripts/run_live_slam_ego_swarm_flight.bat',
    'scripts/wsl/stage7_live_fastlio_dual.sh',
    'scripts/wsl/stage7_live_ego_swarm_dual.sh',
    'scripts/wsl/stage7_live_slam_ego_swarm_flight.sh'
)
foreach ($relativePath in $runtimeScanPaths) {
    Assert-NoBannedText -RelativePath $relativePath -BannedPatterns $bannedPatterns
}
Assert-NoBannedText -RelativePath 'scripts/wsl/stage7_live_fastlio_dual.sh' -BannedPatterns @('sensor_pkg/main\.py')
foreach ($relativePath in @(
    'config/stage7_live_slam_ego_swarm.json',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch',
    'scripts/wsl/stage7_live_fastlio_dual.sh',
    'scripts/wsl/stage7_live_ego_swarm_dual.sh',
    'scripts/wsl/stage7_live_slam_ego_swarm_flight.sh'
)) {
    Assert-NoBannedText -RelativePath $relativePath -BannedPatterns @('shared_rflysim_bridge')
}

$fastLioLaunchPath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch'
if (Test-Path -LiteralPath $fastLioLaunchPath) {
    $fastLioLaunch = Get-Content -Raw -LiteralPath $fastLioLaunchPath
    foreach ($topic in @('/uav1/rflysim/lidar', '/uav1/rflysim/imu', '/uav2/rflysim/lidar', '/uav2/rflysim/imu')) {
        if ($fastLioLaunch -notmatch [regex]::Escape($topic)) {
            $contractErrors += "missing isolated FAST-LIO input: $topic"
        }
    }
    foreach ($nodeName in @('rflysim_pointcloud_adapter', 'rflysim_imu_relay')) {
        if ($fastLioLaunch -notmatch $nodeName) {
            $contractErrors += "rflysim_fastlio_dual.launch must start per-UAV $nodeName nodes"
        }
    }
    foreach ($uavId in @('uav1', 'uav2')) {
        if ($fastLioLaunch -notmatch "/${uavId}/slam/odometry_raw") {
            $contractErrors += "rflysim_fastlio_dual.launch must publish raw FAST-LIO odometry under /${uavId}/slam/odometry_raw before MAVROS frame relay"
        }
        if ($fastLioLaunch -notmatch "odom_frame_relay\.py") {
            $contractErrors += 'rflysim_fastlio_dual.launch must run odom_frame_relay.py for namespaced MAVROS odometry frames'
            break
        }
        if ($fastLioLaunch -notmatch "${uavId}_camera_init" -or $fastLioLaunch -notmatch "${uavId}_body") {
            $contractErrors += "rflysim_fastlio_dual.launch must relay ${uavId} odometry with namespaced camera/body frames"
        }
        foreach ($frameName in @("${uavId}_map_ned", "${uavId}_odom_ned", "${uavId}_base_link_frd")) {
            if ($fastLioLaunch -notmatch $frameName) {
                $contractErrors += "rflysim_fastlio_dual.launch must publish MAVROS-compatible namespaced TF frame $frameName"
            }
        }
    }
    if ($fastLioLaunch -match '<remap\s+from="/Odometry"\s+to="\$\(arg uav[12]_odom_topic\)"') {
        $contractErrors += 'rflysim_fastlio_dual.launch must not remap raw FAST-LIO /Odometry directly to MAVROS odometry/out'
    }
}

$mavrosLaunchPath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_mavros_px4.launch'
if (Test-Path -LiteralPath $mavrosLaunchPath) {
    $mavrosLaunch = Get-Content -Raw -LiteralPath $mavrosLaunchPath
    foreach ($requiredPattern in @(
        'odometry/fcu/odom_parent_id_des',
        'odometry/fcu/odom_child_id_des',
        'odometry/fcu/map_id_des'
    )) {
        if ($mavrosLaunch -notmatch [regex]::Escape($requiredPattern)) {
            $contractErrors += "rflysim_mavros_px4.launch must override MAVROS $requiredPattern for namespaced external odometry"
        }
    }
}

$stage2MavrosPath = Join-Path $ProjectRoot 'scripts/wsl/stage2_two_mavros.sh'
if (Test-Path -LiteralPath $stage2MavrosPath) {
    $stage2Mavros = Get-Content -Raw -LiteralPath $stage2MavrosPath
    if ($stage2Mavros -notmatch 'rflysim_mavros_px4\.launch') {
        $contractErrors += 'stage2_two_mavros.sh must start the project MAVROS wrapper with namespaced odometry frames'
    }
    foreach ($frameName in @('uav1_odom', 'uav1_base_link', 'uav2_odom', 'uav2_base_link')) {
        if ($stage2Mavros -notmatch $frameName) {
            $contractErrors += "stage2_two_mavros.sh dry-run/runtime contract must mention MAVROS odometry frame $frameName"
        }
    }
}

$fastLioRunnerPath = Join-Path $ProjectRoot 'scripts/wsl/stage7_live_fastlio_dual.sh'
if (Test-Path -LiteralPath $fastLioRunnerPath) {
    $fastLioRunner = Get-Content -Raw -LiteralPath $fastLioRunnerPath
    if ($fastLioRunner -notmatch '--copter-id 1' -or $fastLioRunner -notmatch '--copter-id 2') {
        $contractErrors += 'stage7 FAST-LIO runner must start two identified sensor bridges'
    }
    foreach ($pattern in @(
        'rflysim_sensor_uav1\.json',
        'rflysim_sensor_uav2\.json',
        '--sensor-seq-id 0',
        '--sensor-seq-id 10',
        '--udp-port 9999',
        '--udp-port 10009',
        '--process-start-marker',
        'stage7_sensor_readiness\.py'
    )) {
        if ($fastLioRunner -notmatch $pattern) {
            $contractErrors += "stage7 FAST-LIO runner missing isolated readiness pattern: $pattern"
        }
    }
    foreach ($imuRemap in @(
        '/uav1/rflysim/imu:=/uav1/rflysim/imu_raw',
        '/uav2/rflysim/imu:=/uav2/rflysim/imu_raw'
    )) {
        if ($fastLioRunner -notmatch [regex]::Escape($imuRemap)) {
            $contractErrors += "stage7 FAST-LIO runner must remap the namespaced SDK IMU source: $imuRemap"
        }
    }
    if ($fastLioRunner -notmatch 'topic_has_publisher') {
        $contractErrors += 'stage7_live_fastlio_dual.sh must validate ROS sensor topic publishers, not only sensor bridge process existence'
    }
    if ($fastLioRunner -notmatch 'Publishers: None') {
        $contractErrors += 'stage7_live_fastlio_dual.sh must detect stale sensor bridge registrations with no ROS publishers'
    }
    if ($fastLioRunner -notmatch 'STAGE7_SENSOR_STARTUP_TIMEOUT_SEC:-120') {
        $contractErrors += 'stage7_live_fastlio_dual.sh must allow 120 seconds for bounded RflySim point-cloud initialization'
    }
    if ($fastLioRunner -notmatch 'STAGE7_READINESS_TOPIC_TIMEOUT_SEC:-10') {
        $contractErrors += 'stage7_live_fastlio_dual.sh must allow 10 seconds for each readiness topic during asymmetric dual-adapter startup'
    }
    if ($fastLioRunner -notmatch '--timeout-s "\$READINESS_TOPIC_TIMEOUT_SEC"') {
        $contractErrors += 'stage7_live_fastlio_dual.sh must pass the bounded readiness topic timeout to the live sampler'
    }
    if ($fastLioRunner -notmatch '--sensor-mode lidar_only') {
        $contractErrors += 'stage7 FAST-LIO runner must run sensor bridges in lidar-only mode for flight stability'
    }
    if ($fastLioRunner -notmatch 'SENSOR_STARTUP_DEADLINE') {
        $contractErrors += 'stage7_live_fastlio_dual.sh must enforce the sensor startup timeout with a deadline'
    }
    foreach ($cleanupPattern in @('cleanup_sensor_bridges', 'pkill -KILL', 'pgrep -f')) {
        if ($fastLioRunner -notmatch $cleanupPattern) {
            $contractErrors += "stage7_live_fastlio_dual.sh missing bounded stale bridge cleanup: $cleanupPattern"
        }
    }
    foreach ($lifecyclePattern in @('cleanup_stage7_run', 'FASTLIO_PID', 'kill -TERM "\$FASTLIO_PID"', 'handle_shutdown')) {
        if ($fastLioRunner -notmatch $lifecyclePattern) {
            $contractErrors += "stage7_live_fastlio_dual.sh missing owned FAST-LIO lifecycle cleanup: $lifecyclePattern"
        }
    }
}

$flightRunnerPath = Join-Path $ProjectRoot 'scripts/wsl/stage7_live_slam_ego_swarm_flight.sh'
if (Test-Path -LiteralPath $flightRunnerPath) {
    $flightRunner = Get-Content -Raw -LiteralPath $flightRunnerPath
    if ($flightRunner -notmatch 'stage7_sensor_readiness\.py[\s\\]+--validate') {
        $contractErrors += 'arm-capable runner must validate the current Stage 7 readiness report'
    }
    if ($flightRunner -notmatch 'stage7_load_run_context' -or $flightRunner -notmatch 'STAGE7_CURRENT_SIMULATION_INSTANCE_ID') {
        $contractErrors += 'arm-capable runner must recompute the current PX4 simulation instance before readiness validation'
    }
    if ($flightRunner -notmatch 'ego_swarm_setpoint_bridge\.py') {
        $contractErrors += 'stage7_live_slam_ego_swarm_flight.sh must continuously bridge ego-swarm commands to MAVROS setpoints'
    }
    if ($flightRunner -notmatch 'cleanup_keepalive') {
        $contractErrors += 'stage7_live_slam_ego_swarm_flight.sh must clean up setpoint keepalive processes'
    }
    if ($flightRunner -notmatch 'safe_land_disarm') {
        $contractErrors += 'stage7_live_slam_ego_swarm_flight.sh must land and disarm after an armed-path failure'
    }
    if ($flightRunner -notmatch 'MAV_CMD_COMPONENT_ARM_DISARM=400') {
        $contractErrors += 'stage7 live flight failure cleanup must include the PX4 SITL force-disarm command as a bounded fallback'
    }
    if ($flightRunner -notmatch 'EXECUTOR_EXIT_CODE[\s\S]+safe_land_disarm') {
        $contractErrors += 'stage7 live flight runner must invoke safe landing when the executor fails'
    }
    if ($flightRunner -notmatch 'stage7_flight_plan\.py') {
        $contractErrors += 'stage7_live_slam_ego_swarm_flight.sh must generate the flight plan from the Stage 7 config'
    }
    if ($flightRunner -notmatch 'stage7_flight_report\.py') {
        $contractErrors += 'stage7_live_slam_ego_swarm_flight.sh must write a flight report after executor success or failure'
    }
    if ($flightRunner -notmatch 'OUTPUT_DIR="\$STAGE7_RUN_DIR"') {
        $contractErrors += 'arm-capable runner must write flight artifacts under the current run directory'
    }
    if ($flightRunner -notmatch 'CURRENT_RUN_FILE="\$PROJECT_DIR/logs/stage7_live/current_run\.env"') {
        $contractErrors += 'arm-capable runner must keep run metadata at logs/stage7_live/current_run.env'
    }
    if ($flightRunner -match 'OUTPUT_DIR="\$PROJECT_DIR/logs/stage7_live"') {
        $contractErrors += 'arm-capable runner must not write flight artifacts to the flat logs/stage7_live directory'
    }
    if ($flightRunner -notmatch '--max-odom-age-s 2') {
        $contractErrors += 'arm-capable runner watchdog must tolerate short odometry gaps (--max-odom-age-s 2)'
    }
    $ref28OverlayIndex = $flightRunner.IndexOf('source "$REF_28COM_UAV_WSL_DIR/devel/setup.bash"')
    $flightEgoOverlayIndex = $flightRunner.IndexOf('source "$EGO_SWARM_WSL_DIR/devel/setup.bash"', [Math]::Max(0, $ref28OverlayIndex))
    $flightProjectOverlayAfterEgoIndex = $flightRunner.IndexOf('future_aircraft_ws/devel/setup.bash', [Math]::Max(0, $flightEgoOverlayIndex))
    if ($ref28OverlayIndex -lt 0 -or $flightEgoOverlayIndex -lt $ref28OverlayIndex -or $flightProjectOverlayAfterEgoIndex -lt $flightEgoOverlayIndex) {
        $contractErrors += 'arm-capable runner must source ego-planner-swarm after 28com_uav and before the project overlay so quadrotor_msgs matches the planner publisher'
    }
}

$egoRunnerPath = Join-Path $ProjectRoot 'scripts/wsl/stage7_live_ego_swarm_dual.sh'
if (Test-Path -LiteralPath $egoRunnerPath) {
    $egoRunner = Get-Content -Raw -LiteralPath $egoRunnerPath
    if ($egoRunner -notmatch 'stage7_sensor_readiness\.py[\s\\]+--validate') {
        $contractErrors += 'ego-swarm runner must validate the current Stage 7 readiness report'
    }
    if ($egoRunner -notmatch 'stage7_load_run_context' -or $egoRunner -notmatch 'STAGE7_CURRENT_SIMULATION_INSTANCE_ID') {
        $contractErrors += 'ego-swarm runner must recompute the current PX4 simulation instance before readiness validation'
    }
    $egoOverlayIndex = $egoRunner.IndexOf('source "$EGO_SWARM_WSL_DIR/devel/setup.bash"')
    $projectOverlayAfterEgoIndex = $egoRunner.IndexOf('future_aircraft_ws/devel/setup.bash', [Math]::Max(0, $egoOverlayIndex))
    if ($egoOverlayIndex -lt 0 -or $projectOverlayAfterEgoIndex -lt $egoOverlayIndex) {
        $contractErrors += 'ego-swarm runner must restore the project ROS overlay after sourcing ego-planner-swarm'
    }
}

$topicProbeRunnerPath = Join-Path $ProjectRoot 'scripts/run_stage7_topic_probe.bat'
if (Test-Path -LiteralPath $topicProbeRunnerPath) {
    $topicProbeRunner = Get-Content -Raw -LiteralPath $topicProbeRunnerPath
    if ($topicProbeRunner -notmatch 'stage7_load_run_context' -or $topicProbeRunner -notmatch 'STAGE7_CURRENT_SIMULATION_INSTANCE_ID') {
        $contractErrors += 'topic probe runner must recompute the current PX4 simulation instance before readiness validation'
    }
    if ($topicProbeRunner -notmatch '--readiness-max-age-s') {
        $contractErrors += 'topic probe runner must pass an explicit readiness age limit'
    }
    if ($topicProbeRunner -notmatch 'STAGE7_READINESS_MAX_AGE_SEC:-120') {
        $contractErrors += 'topic probe runner must use the same 120-second readiness window as the ego-swarm runner'
    }
    if ($topicProbeRunner -notmatch '\$STAGE7_RUN_DIR/topic_probe_report\.json') {
        $contractErrors += 'topic probe runner must write its report under the current run directory'
    }
}

foreach ($relativePath in @(
    'scripts/wsl/stage7_live_fastlio_dual.sh',
    'scripts/wsl/stage7_live_ego_swarm_dual.sh',
    'scripts/wsl/stage7_run_context.sh',
    'scripts/wsl/stage7_live_slam_ego_swarm_flight.sh'
)) {
    Assert-LfOnly -RelativePath $relativePath
}

if ($missing.Count -eq 0) {
    $pythonRunner = Get-ContractPythonRunner
    if (-not $pythonRunner) {
        $contractErrors += 'No usable Python interpreter found; checked D:\PX4PSP\Python38\python.exe, python, and WSL python3'
    }
    else {
        $reportPath = Join-Path $env:TEMP ("future_aircraft_stage7_smoke_report_{0}.json" -f $PID)
        if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath -Force }
        $smokeScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $smokeScript -Arguments @(
            '--config', $configPath,
            '--backend', 'dry-run',
            '--report', $reportPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "ego_swarm_flight_smoke_check.py dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $reportPath)) {
            $contractErrors += "ego_swarm_flight_smoke_check.py did not create report: $reportPath"
        }
        else {
            $report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
            if ($report.ready -ne $true) {
                $contractErrors += 'ego_swarm_flight_smoke_check.py dry-run report must be ready=true'
            }
            if ($report.uavs.Count -ne 2) {
                $contractErrors += 'ego_swarm_flight_smoke_check.py dry-run report must contain two UAV entries'
            }
        }
    }

    if ($pythonRunner) {
        $probeReportPath = Join-Path $env:TEMP ("future_aircraft_stage7_topic_probe_{0}.json" -f $PID)
        if (Test-Path -LiteralPath $probeReportPath) { Remove-Item -LiteralPath $probeReportPath -Force }
        $probeScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $probeScript -Arguments @(
            '--config', $configPath,
            '--backend', 'dry-run',
            '--report', $probeReportPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_topic_probe.py dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $probeReportPath)) {
            $contractErrors += "stage7_topic_probe.py did not create report: $probeReportPath"
        }
        else {
            $probeReport = Get-Content -Raw -LiteralPath $probeReportPath | ConvertFrom-Json
            foreach ($layer in @('sensor_bridge', 'fast_lio', 'mavros', 'ego_swarm', 'flight_gate')) {
                if (-not ($probeReport.layers.PSObject.Properties.Name -contains $layer)) {
                    $contractErrors += "stage7_topic_probe.py report missing layer: $layer"
                }
            }
            if ($probeReport.uavs.Count -ne 2) {
                $contractErrors += 'stage7_topic_probe.py dry-run report must contain two UAV entries'
            }
        }

        $relayCheckScript = Join-Path $ProjectRoot 'tests/stage7_odom_frame_relay_check.py'
        $relayModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/odom_frame_relay.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $relayCheckScript -Arguments @(
            '--module', $relayModulePath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_odom_frame_relay_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $sensorImportCheckScript = Join-Path $ProjectRoot 'tests/stage7_sensor_bridge_import_check.py'
        $sensorBridgeModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $sensorImportCheckScript -Arguments @(
            '--module', $sensorBridgeModulePath,
            '--psp-path', 'D:\PX4PSP'
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_sensor_bridge_import_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $cloudContractScript = Join-Path $ProjectRoot 'tests/stage7_cloud_contract_check.py'
        $cloudContractModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_cloud_contract.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $cloudContractScript -Arguments @(
            '--module', $cloudContractModule
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_cloud_contract_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $readinessCheckScript = Join-Path $ProjectRoot 'tests/stage7_sensor_readiness_check.py'
        $readinessModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_sensor_readiness.py'
        $topicProbeModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $readinessCheckScript -Arguments @(
            '--module', $readinessModule,
            '--probe-module', $topicProbeModule
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_sensor_readiness_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $flightArtifactCheckScript = Join-Path $ProjectRoot 'tests/stage7_flight_artifact_check.py'
        $flightPlanModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_plan.py'
        $flightReportModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py'
        $flightArtifactsModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_run_artifacts.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $flightArtifactCheckScript -Arguments @(
            '--plan-module', $flightPlanModulePath,
            '--report-module', $flightReportModulePath,
            '--artifacts-module', $flightArtifactsModulePath,
            '--config', $configPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_flight_artifact_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $goalDeliveryCheckScript = Join-Path $ProjectRoot 'tests/stage7_goal_delivery_check.py'
        $singlePlannerLaunch = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_single.launch'
        $dualPlannerLaunch = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch'
        $missionExecutorModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $goalDeliveryCheckScript -Arguments @(
            '--single-launch', $singlePlannerLaunch,
            '--dual-launch', $dualPlannerLaunch,
            '--executor-module', $missionExecutorModule
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_goal_delivery_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $plannerBridgeCheckScript = Join-Path $ProjectRoot 'tests/stage7_planner_control_bridge_check.py'
        $plannerBridgeModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_setpoint_bridge.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $plannerBridgeCheckScript -Arguments @(
            '--bridge-module', $plannerBridgeModule,
            '--plan-module', $flightPlanModulePath,
            '--executor-module', $missionExecutorModule,
            '--config', $configPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_planner_control_bridge_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $executorFailureCheckScript = Join-Path $ProjectRoot 'tests/stage7_executor_failure_artifact_check.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $executorFailureCheckScript -Arguments @(
            '--executor-module', $missionExecutorModule,
            '--live-config', (Join-Path $ProjectRoot 'config/stage5_live_mission.json')
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_executor_failure_artifact_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $probeFlowCheckScript = Join-Path $ProjectRoot 'tests/stage7_probe_flow_check.py'
        $probeModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $probeFlowCheckScript -Arguments @(
            '--probe-module', $probeModule,
            '--config', $configPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_probe_flow_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $quadrotorMsgsOverlayCheckScript = Join-Path $ProjectRoot 'tests/stage7_quadrotor_msgs_overlay_check.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $quadrotorMsgsOverlayCheckScript -Arguments @(
            '--flight-runner', (Join-Path $ProjectRoot 'scripts/wsl/stage7_live_slam_ego_swarm_flight.sh'),
            '--recorder-bat', (Join-Path $ProjectRoot 'scripts/run_stage8_control_chain_recorder.bat')
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_quadrotor_msgs_overlay_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $persistentSubscriberCheckScript = Join-Path $ProjectRoot 'tests/stage7_persistent_navigation_subscriber_check.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $persistentSubscriberCheckScript -Arguments @(
            '--executor-module', $missionExecutorModule
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_persistent_navigation_subscriber_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $provenanceCheckScript = Join-Path $ProjectRoot 'tests/stage7_provenance_check.py'
        $flightReportModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_flight_report.py'
        $runArtifactsModulePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/stage7_run_artifacts.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $provenanceCheckScript -Arguments @(
            '--artifacts-module', $runArtifactsModulePath,
            '--report-module', $flightReportModulePath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_provenance_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $odomTfContractCheckScript = Join-Path $ProjectRoot 'tests/stage8_odom_tf_contract_check.py'
        $odomTfContractModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/odom_tf_contract_check.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $odomTfContractCheckScript -Arguments @(
            '--module', $odomTfContractModule,
            '--config', $configPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage8_odom_tf_contract_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $odomTfReportPath = Join-Path $env:TEMP ("future_aircraft_odom_tf_contract_{0}.json" -f $PID)
        if (Test-Path -LiteralPath $odomTfReportPath) { Remove-Item -LiteralPath $odomTfReportPath -Force }
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $odomTfContractModule -Arguments @(
            '--config', $configPath,
            '--backend', 'dry-run',
            '--report', $odomTfReportPath
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "odom_tf_contract_check.py dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $odomTfReportPath)) {
            $contractErrors += 'odom_tf_contract_check.py did not create report'
        }

        $flightEventRecorderCheckScript = Join-Path $ProjectRoot 'tests/stage7_flight_event_recorder_check.py'
        $flightEventRecorderModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/flight_event_recorder.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $flightEventRecorderCheckScript -Arguments @(
            '--module', $flightEventRecorderModule
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_flight_event_recorder_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }

        $swarmObstacleCheckScript = Join-Path $ProjectRoot 'tests/stage7_swarm_obstacle_check.py'
        $swarmObstacleModule = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/check_swarm_obstacle.py'
        $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $swarmObstacleCheckScript -Arguments @(
            '--module', $swarmObstacleModule
        )
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "stage7_swarm_obstacle_check.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
    }

    foreach ($script in @(
        'scripts/run_live_fastlio_dual.bat',
        'scripts/run_live_ego_swarm_dual.bat',
        'scripts/run_stage7_topic_probe.bat',
        'scripts/run_live_slam_ego_swarm_flight.bat'
    )) {
        $fullPath = Join-Path $ProjectRoot $script
        $output = & cmd /c $fullPath --dry-run 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "$script --dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
        elseif ($script -eq 'scripts/run_stage7_topic_probe.bat' -and
                ($output -join ' ') -notmatch 'readiness max age: 120 seconds') {
            $contractErrors += 'topic probe dry-run must expose its 120-second readiness age limit'
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 7 live SLAM ego-swarm validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 7 live SLAM ego-swarm validation passed.' -ForegroundColor Green
}
exit 0
