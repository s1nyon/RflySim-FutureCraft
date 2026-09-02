param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'config/stage5_behavior_tree.json',
    'config/stage5_live_mission.json',
    'future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py',
    'scripts/validate_stage5b.ps1',
    'tests/fixtures/stage5c/expected_executor_trace.json',
    'tests/fixtures/stage5c/expected_mission_events.jsonl',
    'tests/fixtures/stage5c/expected_score_summary.json'
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
    $outputDir = Join-Path $env:TEMP ("future_aircraft_stage5c_{0}" -f $PID)
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $planOutputPath = Join-Path $outputDir 'live_mission_plan.json'
    $eventsOutputPath = Join-Path $outputDir 'mission_events.jsonl'
    $traceOutputPath = Join-Path $outputDir 'executor_trace.json'
    $scoreOutputPath = Join-Path $outputDir 'score_summary.json'

    foreach ($path in @($planOutputPath, $eventsOutputPath, $traceOutputPath, $scoreOutputPath)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }

    $generatorScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py'
    $executorScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py'
    $behaviorConfigPath = Join-Path $ProjectRoot 'config/stage5_behavior_tree.json'
    $liveConfigPath = Join-Path $ProjectRoot 'config/stage5_live_mission.json'
    $traceFixturePath = Join-Path $ProjectRoot 'tests/fixtures/stage5c/expected_executor_trace.json'
    $eventsFixturePath = Join-Path $ProjectRoot 'tests/fixtures/stage5c/expected_mission_events.jsonl'
    $scoreFixturePath = Join-Path $ProjectRoot 'tests/fixtures/stage5c/expected_score_summary.json'

    $generatorOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $generatorScript -Arguments @('--behavior-config', $behaviorConfigPath, '--live-config', $liveConfigPath, '--output', $planOutputPath)
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "live_mission_contract.py failed with exit code ${LASTEXITCODE}: $($generatorOutput -join ' ')"
    }
    elseif (-not (Test-Path -LiteralPath $planOutputPath)) {
        $contractErrors += "live_mission_contract.py did not create output: $planOutputPath"
    }
    else {
        $executorOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $executorScript -Arguments @('--plan', $planOutputPath, '--backend', 'dry-run', '--events', $eventsOutputPath, '--trace', $traceOutputPath, '--score', $scoreOutputPath)
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "mission_executor.py failed with exit code ${LASTEXITCODE}: $($executorOutput -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $eventsOutputPath)) {
            $contractErrors += "mission_executor.py did not create mission events: $eventsOutputPath"
        }
        elseif (-not (Test-Path -LiteralPath $traceOutputPath)) {
            $contractErrors += "mission_executor.py did not create executor trace: $traceOutputPath"
        }
        elseif (-not (Test-Path -LiteralPath $scoreOutputPath)) {
            $contractErrors += "mission_executor.py did not create score summary: $scoreOutputPath"
        }
        else {
            $actualTrace = Get-Content -Raw -LiteralPath $traceOutputPath | ConvertFrom-Json
            $expectedTrace = Get-Content -Raw -LiteralPath $traceFixturePath | ConvertFrom-Json
            if (($actualTrace | ConvertTo-Json -Depth 16 -Compress) -ne ($expectedTrace | ConvertTo-Json -Depth 16 -Compress)) {
                $contractErrors += 'executor_trace.json does not match Stage 5C fixture'
            }

            $actualEvents = (Get-Content -Raw -LiteralPath $eventsOutputPath) -replace "`r`n", "`n"
            $expectedEvents = (Get-Content -Raw -LiteralPath $eventsFixturePath) -replace "`r`n", "`n"
            if ($actualEvents -ne $expectedEvents) {
                $contractErrors += 'mission_events.jsonl does not match Stage 5C fixture'
            }

            $actualScore = Get-Content -Raw -LiteralPath $scoreOutputPath | ConvertFrom-Json
            $expectedScore = Get-Content -Raw -LiteralPath $scoreFixturePath | ConvertFrom-Json
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
        $stage5bScript = Join-Path $ProjectRoot 'scripts/validate_stage5b.ps1'
        $stage5bOutput = & powershell -ExecutionPolicy Bypass -File $stage5bScript -Quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "Stage 5B validation regression failed with exit code ${LASTEXITCODE}: $($stage5bOutput -join ' ')"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 5C ROS mission executor validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 5C ROS mission executor validation passed.' -ForegroundColor Green
}
exit 0


