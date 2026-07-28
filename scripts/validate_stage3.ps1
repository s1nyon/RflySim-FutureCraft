param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'future_aircraft_ws/src/multi_uav_mission/package.xml',
    'future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt',
    'future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py',
    'scripts/create_log_run.bat',
    'tests/fixtures/stage3/mission_events.jsonl',
    'tests/fixtures/stage3/expected_score_summary.json'
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

if ($missing.Count -eq 0 -and $pythonRunner) {
    $outputPath = Join-Path $env:TEMP ("future_aircraft_stage3_score_summary_{0}.json" -f $PID)
    if (Test-Path -LiteralPath $outputPath) { Remove-Item -LiteralPath $outputPath -Force }
    $scoreScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py'
    $fixturePath = Join-Path $ProjectRoot 'tests/fixtures/stage3/mission_events.jsonl'
    $expectedPath = Join-Path $ProjectRoot 'tests/fixtures/stage3/expected_score_summary.json'
    $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $scoreScript -Arguments @('--events', $fixturePath, '--output', $outputPath)
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "score_summary.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
    }
    elseif (-not (Test-Path -LiteralPath $outputPath)) {
        $contractErrors += "score_summary.py did not create output: $outputPath"
    }
    else {
        $actual = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
        $expected = Get-Content -Raw -LiteralPath $expectedPath | ConvertFrom-Json
        foreach ($field in @('success', 'duration_s', 'min_uav_distance_m', 'offboard_loss_count', 'collision_count', 'timeout_count', 'targets_detected_count')) {
            if ($actual.$field -ne $expected.$field) {
                $contractErrors += "score summary mismatch for ${field}: actual=$($actual.$field), expected=$($expected.$field)"
            }
        }
    }
}

$logScript = Join-Path $ProjectRoot 'scripts/create_log_run.bat'
if (Test-Path -LiteralPath $logScript) {
    $output = & cmd /c "`"$logScript`" --dry-run" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "scripts/create_log_run.bat --dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 3 logging/scoring validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 3 logging/scoring validation passed.' -ForegroundColor Green
}
exit 0

