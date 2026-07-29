param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$requiredPaths = @(
    'config/stage2_1_mavlink_link.json',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mavlink_return_path_check.py',
    'tests/stage2_1_mavlink_return_path_check.py',
    'tests/fixtures/stage2_1/px4_status_ready.log',
    'tests/fixtures/stage2_1/px4_status_return_blocked.log',
    'tests/fixtures/stage2_1/expected_dry_run_report.json',
    'tests/fixtures/stage2_1/expected_runner_dry_run.txt',
    'scripts/wsl/stage2_1_single_mavlink_check.sh',
    'scripts/run_stage2_1_mavlink_check.bat',
    'README.md',
    '.agents/AGENT2READ.md'
)
$missing = @($requiredPaths | Where-Object { -not (Test-Path -LiteralPath (Join-Path $ProjectRoot $_)) })
$errors = @()

if ($missing.Count -eq 0) {
    try {
        $config = Get-Content -Raw -LiteralPath (Join-Path $ProjectRoot 'config/stage2_1_mavlink_link.json') | ConvertFrom-Json
        if ($config.namespace -ne '/uav1') { $errors += 'config namespace must be /uav1' }
        if ($config.px4_instance -ne 1) { $errors += 'config px4_instance must be 1' }
        if ($config.fcu_url -ne 'udp://:16540@127.0.0.1:17540') { $errors += 'config fcu_url is incorrect' }
    } catch { $errors += "config is invalid JSON: $($_.Exception.Message)" }

    $wslPath = Join-Path $ProjectRoot 'scripts/wsl/stage2_1_single_mavlink_check.sh'
    $bytes = [System.IO.File]::ReadAllBytes($wslPath)
    for ($i = 0; $i -lt $bytes.Length - 1; $i++) {
        if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) { $errors += 'WSL helper must be LF-only'; break }
    }
    $wslText = Get-Content -Raw -LiteralPath $wslPath
    foreach ($forbidden in @('cmd/arming', 'set_mode', 'setpoint', 'rospy.Publisher', 'start_two_uav.bat')) {
        if ($wslText -match [regex]::Escape($forbidden)) { $errors += "WSL helper contains forbidden action marker: $forbidden" }
    }

    $python = 'D:\PX4PSP\Python38\python.exe'
    $test = Join-Path $ProjectRoot 'tests/stage2_1_mavlink_return_path_check.py'
    $script = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/mavlink_return_path_check.py'
    $testOutput = & $python $test --script $script 2>&1
    if ($LASTEXITCODE -ne 0) { $errors += "Python regression failed: $($testOutput -join ' ')" }

    $runner = Join-Path $ProjectRoot 'scripts/run_stage2_1_mavlink_check.bat'
    $fixture = Join-Path $ProjectRoot 'tests/fixtures/stage2_1/expected_runner_dry_run.txt'
    $output = & cmd /c $runner --dry-run 2>&1
    if ($LASTEXITCODE -ne 0) { $errors += 'Stage 2.1 dry-run failed' }
    elseif (($output -join "`r`n").Trim() -ne (Get-Content -Raw -LiteralPath $fixture).Trim()) { $errors += 'Stage 2.1 dry-run output does not match fixture' }

    $stage2 = Join-Path $ProjectRoot 'scripts/validate_stage2.ps1'
    $stage2Output = & powershell -ExecutionPolicy Bypass -File $stage2 -Quiet 2>&1
    if ($LASTEXITCODE -ne 0) { $errors += "Stage 2 regression failed: $($stage2Output -join ' ')" }
}

if ($missing.Count -gt 0 -or $errors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 2.1 MAVLink return-path validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $errors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}
if (-not $Quiet) { Write-Host '[PASS] Stage 2.1 MAVLink return-path validation passed.' -ForegroundColor Green }
exit 0
