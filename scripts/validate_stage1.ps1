param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$requiredPaths = @(
    'config/env_template.bat',
    'config/stage1_single_uav.json',
    'scripts/start_single_uav.bat',
    'scripts/start_vcxsrv.bat',
    'scripts/start_rflysim_sitl_single.bat',
    'scripts/start_wsl_ros_single.bat',
    'scripts/wsl/stage1_single_uav.sh',
    'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_single.launch'
)

$missing = @()
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) {
        $missing += $relativePath
    }
}

$contractErrors = @()
$envPath = Join-Path $ProjectRoot 'config/env_template.bat'
if (Test-Path -LiteralPath $envPath) {
    $envText = Get-Content -Raw -LiteralPath $envPath
    if ($envText -match 'CustSimAPIs') {
        $contractErrors += 'config/env_template.bat contains invalid CustSimAPIs path segment'
    }
    if ($envText -notmatch '/mnt/d/PX4PSP/RflySimAPIs/8\.RflySimVision/3\.CustExps/e13\.RobotCom26Adv/future_aircraft_sim') {
        $contractErrors += 'config/env_template.bat missing correct FUTURE_AIRCRAFT_SIM_WSL_DIR path'
    }
    foreach ($name in @('PSP_PATH', 'PSP_PATH_LINUX', 'RFLYSIM_WSL_DISTRO', 'RFLYSIM_UAV_SITL_SCRIPT', 'REF_28COM_UAV_DIR', 'REF_28COM_UAV_WSL_DIR', 'FUTURE_AIRCRAFT_SIM_WSL_DIR')) {
        if ($envText -notmatch [regex]::Escape($name)) {
            $contractErrors += "config/env_template.bat missing $name"
        }
    }
}

$configPath = Join-Path $ProjectRoot 'config/stage1_single_uav.json'
if (Test-Path -LiteralPath $configPath) {
    try {
        $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
        if ($config.stage -ne 1) { $contractErrors += 'config/stage1_single_uav.json stage must be 1' }
        if (-not $config.launch.windows_sitl_script) { $contractErrors += 'stage1 config missing launch.windows_sitl_script' }
        if (-not $config.launch.wsl_ros_script) { $contractErrors += 'stage1 config missing launch.wsl_ros_script' }
        if ($config.uav.namespace -ne '/mavros') { $contractErrors += 'stage1 single-UAV namespace should remain /mavros for original 28com stack' }
    }
    catch {
        $contractErrors += "config/stage1_single_uav.json is not valid JSON: $($_.Exception.Message)"
    }
}

$dryRunScripts = @(
    'scripts/start_vcxsrv.bat',
    'scripts/start_rflysim_sitl_single.bat',
    'scripts/start_wsl_ros_single.bat',
    'scripts/start_single_uav.bat'
)
foreach ($relativePath in $dryRunScripts) {
    $fullPath = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $fullPath) {
        $content = Get-Content -Raw -LiteralPath $fullPath
        if ($content -notmatch '--dry-run') { $contractErrors += "$relativePath missing --dry-run support" }
        if ($content -match 'cmd /k "call ""') {
            $contractErrors += "$relativePath uses invalid cmd nested call quoting"
        }
        $output = & cmd /c "`"$fullPath`" --dry-run" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "$relativePath --dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
    }
}

$wslScript = Join-Path $ProjectRoot 'scripts/wsl/stage1_single_uav.sh'
if (Test-Path -LiteralPath $wslScript) {
    $wslText = Get-Content -Raw -LiteralPath $wslScript
    foreach ($needle in @(
        'sensor_pkg/main.py',
        'faster_lio mapping_mid360.launch',
        'rflysim_ego_swarm_single.launch',
        'object_det detection.launch',
        'mission_pkg basic_test.launch',
        'REF_28COM_UAV_WSL_DIR'
    )) {
        if ($wslText -notmatch [regex]::Escape($needle)) {
            $contractErrors += "scripts/wsl/stage1_single_uav.sh missing $needle"
        }
    }
    foreach ($forbidden in @(
        'ego_planner swarm.launch',
        'random_forest',
        'poscmd_2_odom',
        'simulator.xml'
    )) {
        if ($wslText -match [regex]::Escape($forbidden)) {
            $contractErrors += "scripts/wsl/stage1_single_uav.sh must not use ego-swarm demo component $forbidden"
        }
    }
}

$egoWrapper = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_single.launch'
if (Test-Path -LiteralPath $egoWrapper) {
    $egoWrapperText = Get-Content -Raw -LiteralPath $egoWrapper
    foreach ($needle in @(
        'pkg="ego_planner"',
        'type="ego_planner_node"',
        'type="traj_server"',
        'name="odom_topic" default="/mavros/local_position/odom"',
        'name="cloud_topic" default="/cloud_registered"',
        'name="pos_cmd_topic" default="/planning/pos_cmd"',
        'from="~odom_world" to="$(arg odom_topic)"',
        'from="~grid_map/cloud" to="$(arg cloud_topic)"',
        'from="/position_cmd" to="$(arg pos_cmd_topic)"'
    )) {
        if ($egoWrapperText -notmatch [regex]::Escape($needle)) {
            $contractErrors += "rflysim_ego_swarm_single.launch missing $needle"
        }
    }
    foreach ($forbidden in @(
        'swarm.launch',
        'run_in_sim.launch',
        'single_run_in_sim.launch',
        'simulator.xml',
        'random_forest',
        'poscmd_2_odom',
        'pcl_render_node'
    )) {
        if ($egoWrapperText -match [regex]::Escape($forbidden)) {
            $contractErrors += "rflysim_ego_swarm_single.launch must not use ego-swarm demo component $forbidden"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 1 single-UAV launch validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 1 single-UAV launch validation passed.' -ForegroundColor Green
}
exit 0

