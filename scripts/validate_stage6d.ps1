param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$requiredPaths = @(
    'config/env_template.bat',
    'config/stage5_behavior_tree.json',
    'config/stage5_live_mission.json',
    'future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py',
    'scripts/run_live_no_arm_smoke.bat',
    'scripts/run_live_sim_arm.bat',
    'scripts/wsl/stage6d_live_no_arm_smoke.sh',
    'scripts/wsl/stage6e_live_sim_arm.sh',
    'scripts/validate_stage6c.ps1',
    'tests/fixtures/stage6d/expected_no_arm_dry_run.txt',
    'tests/fixtures/stage6d/expected_sim_arm_dry_run.txt'
)

$missing = @()
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) {
        $missing += $relativePath
    }
}

$contractErrors = @()
function Normalize-TextForComparison {
    param([string]$Value)
    return ($Value -replace "`r`n", "`n").Trim()
}

if ($missing.Count -eq 0) {
    $noArmScript = Join-Path $ProjectRoot 'scripts/run_live_no_arm_smoke.bat'
    $simArmScript = Join-Path $ProjectRoot 'scripts/run_live_sim_arm.bat'
    $noArmFixture = Join-Path $ProjectRoot 'tests/fixtures/stage6d/expected_no_arm_dry_run.txt'
    $simArmFixture = Join-Path $ProjectRoot 'tests/fixtures/stage6d/expected_sim_arm_dry_run.txt'
    $liveConfigPath = Join-Path $ProjectRoot 'config/stage5_live_mission.json'
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

    foreach ($relativePath in @('scripts/wsl/stage6d_live_no_arm_smoke.sh', 'scripts/wsl/stage6e_live_sim_arm.sh')) {
        $fullPath = Join-Path $ProjectRoot $relativePath
        $bytes = [System.IO.File]::ReadAllBytes($fullPath)
        for ($i = 0; $i -lt ($bytes.Length - 1); $i++) {
            if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) {
                $contractErrors += "$relativePath must use LF line endings for WSL execution"
                break
            }
        }
    }

    $noArmOutput = & cmd /c $noArmScript --dry-run 2>&1
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "run_live_no_arm_smoke.bat --dry-run failed with exit code ${LASTEXITCODE}: $($noArmOutput -join ' ')"
    } elseif ((Normalize-TextForComparison ($noArmOutput -join "`n")) -ne (Normalize-TextForComparison (Get-Content -Raw -LiteralPath $noArmFixture))) {
        $contractErrors += 'run_live_no_arm_smoke.bat --dry-run output does not match fixture'
    }

    $simArmOutput = & cmd /c $simArmScript --dry-run 2>&1
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "run_live_sim_arm.bat --dry-run failed with exit code ${LASTEXITCODE}: $($simArmOutput -join ' ')"
    } elseif ((Normalize-TextForComparison ($simArmOutput -join "`n")) -ne (Normalize-TextForComparison (Get-Content -Raw -LiteralPath $simArmFixture))) {
        $contractErrors += 'run_live_sim_arm.bat --dry-run output does not match fixture'
    }

    if ($contractErrors.Count -eq 0) {
        $stage6cScript = Join-Path $ProjectRoot 'scripts/validate_stage6c.ps1'
        $stage6cOutput = & powershell -ExecutionPolicy Bypass -File $stage6cScript -Quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "Stage 6C validation regression failed with exit code ${LASTEXITCODE}: $($stage6cOutput -join ' ')"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 6D/6E live runner validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 6D/6E live runner validation passed.' -ForegroundColor Green
}
exit 0
