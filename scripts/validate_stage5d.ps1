param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'config/stage5_live_mission.json',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py',
    'scripts/validate_stage5c.ps1',
    'tests/fixtures/stage5d/expected_mavros_smoke_report.json',
    'tests/stage5d_ros_master_unavailable_check.py'
)

$missing = @()
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) {
        $missing += $relativePath
    }
}

$contractErrors = @()
$pythonRunner = Get-ContractPythonRunner
if (-not $pythonRunner) {
    $contractErrors += 'No usable Python interpreter found; checked D:\PX4PSP\Python38\python.exe, python, and WSL python3'
}

function ConvertTo-StableJson($Value) {
    return ($Value | ConvertTo-Json -Depth 16 -Compress)
}

if ($missing.Count -eq 0 -and $pythonRunner) {
    $outputDir = Join-Path $env:TEMP ("future_aircraft_stage5d_{0}" -f $PID)
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $reportOutputPath = Join-Path $outputDir 'mavros_smoke_report.json'
    if (Test-Path -LiteralPath $reportOutputPath) { Remove-Item -LiteralPath $reportOutputPath -Force }

    $smokeScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py'
    $liveConfigPath = Join-Path $ProjectRoot 'config/stage5_live_mission.json'
    $expectedPath = Join-Path $ProjectRoot 'tests/fixtures/stage5d/expected_mavros_smoke_report.json'
    $liveConfig = Get-Content -Raw -LiteralPath $liveConfigPath | ConvertFrom-Json
    $expectedOdomTopics = @{
        uav1 = '/uav1/mavros/odometry/in'
        uav2 = '/uav2/mavros/odometry/in'
    }
    foreach ($uav in $liveConfig.uavs) {
        if ($uav.odom_topic -ne $expectedOdomTopics[$uav.uav_id]) {
            $contractErrors += "unexpected odom_topic for $($uav.uav_id): $($uav.odom_topic)"
        }
    }

    if ($contractErrors.Count -gt 0) {
        # Preserve the contract failure without generating a report from an invalid interface.
    }
    else {
        $smokeOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $smokeScript -Arguments @('--live-config', $liveConfigPath, '--backend', 'dry-run', '--report', $reportOutputPath)
        if ($LASTEXITCODE -ne 0) {
        $contractErrors += "mavros_smoke_check.py failed with exit code ${LASTEXITCODE}: $($smokeOutput -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $reportOutputPath)) {
        $contractErrors += "mavros_smoke_check.py did not create output: $reportOutputPath"
        }
        else {
        $actual = Get-Content -Raw -LiteralPath $reportOutputPath | ConvertFrom-Json
        $expected = Get-Content -Raw -LiteralPath $expectedPath | ConvertFrom-Json
        if ((ConvertTo-StableJson $actual) -ne (ConvertTo-StableJson $expected)) {
            $contractErrors += 'mavros_smoke_report.json does not match Stage 5D fixture'
        }
        }
    }

    if ($contractErrors.Count -eq 0) {
        $masterCheckScript = Join-Path $ProjectRoot 'tests/stage5d_ros_master_unavailable_check.py'
        $masterCheckOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $masterCheckScript -Arguments @('--script', $smokeScript)
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "ROS master unavailable regression check failed with exit code ${LASTEXITCODE}: $($masterCheckOutput -join ' ')"
        }
    }

    if ($contractErrors.Count -eq 0) {
        $stage5cScript = Join-Path $ProjectRoot 'scripts/validate_stage5c.ps1'
        $stage5cOutput = & powershell -ExecutionPolicy Bypass -File $stage5cScript -Quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "Stage 5C validation regression failed with exit code ${LASTEXITCODE}: $($stage5cOutput -join ' ')"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 5D MAVROS live smoke validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 5D MAVROS live smoke validation passed.' -ForegroundColor Green
}
exit 0

