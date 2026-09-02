param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'config/stage5_behavior_tree.json',
    'future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py',
    'scripts/validate_stage3.ps1',
    'tests/fixtures/stage5/expected_mission_events.jsonl',
    'tests/fixtures/stage5/expected_score_summary.json'
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
    $outputDir = Join-Path $env:TEMP ("future_aircraft_stage5_{0}" -f $PID)
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $eventsOutputPath = Join-Path $outputDir 'mission_events.jsonl'
    $scoreOutputPath = Join-Path $outputDir 'score_summary.json'
    if (Test-Path -LiteralPath $eventsOutputPath) { Remove-Item -LiteralPath $eventsOutputPath -Force }
    if (Test-Path -LiteralPath $scoreOutputPath) { Remove-Item -LiteralPath $scoreOutputPath -Force }

    $runnerScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py'
    $scoreScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py'
    $configPath = Join-Path $ProjectRoot 'config/stage5_behavior_tree.json'
    $expectedEventsPath = Join-Path $ProjectRoot 'tests/fixtures/stage5/expected_mission_events.jsonl'
    $expectedScorePath = Join-Path $ProjectRoot 'tests/fixtures/stage5/expected_score_summary.json'

    $runnerOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $runnerScript -Arguments @('--config', $configPath, '--output', $eventsOutputPath)
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "behavior_tree_runner.py failed with exit code ${LASTEXITCODE}: $($runnerOutput -join ' ')"
    }
    elseif (-not (Test-Path -LiteralPath $eventsOutputPath)) {
        $contractErrors += "behavior_tree_runner.py did not create output: $eventsOutputPath"
    }
    else {
        $actualEvents = (Get-Content -Raw -LiteralPath $eventsOutputPath) -replace "`r`n", "`n"
        $expectedEvents = (Get-Content -Raw -LiteralPath $expectedEventsPath) -replace "`r`n", "`n"
        if ($actualEvents -ne $expectedEvents) {
            $contractErrors += 'mission_events.jsonl does not match Stage 5 fixture'
        }
    }

    if ($contractErrors.Count -eq 0) {
        $scoreOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $scoreScript -Arguments @('--events', $eventsOutputPath, '--output', $scoreOutputPath)
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "score_summary.py failed with exit code ${LASTEXITCODE}: $($scoreOutput -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $scoreOutputPath)) {
            $contractErrors += "score_summary.py did not create output: $scoreOutputPath"
        }
        else {
            $actualScore = Get-Content -Raw -LiteralPath $scoreOutputPath | ConvertFrom-Json
            $expectedScore = Get-Content -Raw -LiteralPath $expectedScorePath | ConvertFrom-Json
            foreach ($field in @('success', 'duration_s', 'min_uav_distance_m', 'offboard_loss_count', 'collision_count', 'timeout_count', 'targets_detected_count', 'mission_start_time', 'mission_end_time')) {
                if ($actualScore.$field -ne $expectedScore.$field) {
                    $contractErrors += "score summary mismatch for ${field}: actual=$($actualScore.$field), expected=$($expectedScore.$field)"
                }
            }
            if (($actualScore.failure_reasons | ConvertTo-Json -Compress) -ne ($expectedScore.failure_reasons | ConvertTo-Json -Compress)) {
                $contractErrors += 'score summary mismatch for failure_reasons'
            }
        }
    }

    if ($contractErrors.Count -eq 0) {
        $stage3Script = Join-Path $ProjectRoot 'scripts/validate_stage3.ps1'
        $stage3Output = & powershell -ExecutionPolicy Bypass -File $stage3Script -Quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "Stage 3 validation regression failed with exit code ${LASTEXITCODE}: $($stage3Output -join ' ')"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 5 behavior tree validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 5 behavior tree validation passed.' -ForegroundColor Green
}
exit 0

