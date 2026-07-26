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
    'scripts/wsl/stage1_single_uav.sh'
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
        $output = & cmd /c "`"$fullPath`" --dry-run" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "$relativePath --dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
    }
}

$wslScript = Join-Path $ProjectRoot 'scripts/wsl/stage1_single_uav.sh'
if (Test-Path -LiteralPath $wslScript) {
    $wslText = Get-Content -Raw -LiteralPath $wslScript
    foreach ($needle in @('sensor_pkg/main.py', 'mission_pkg basic_test.launch', 'REF_28COM_UAV_WSL_DIR')) {
        if ($wslText -notmatch [regex]::Escape($needle)) {
            $contractErrors += "scripts/wsl/stage1_single_uav.sh missing $needle"
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

