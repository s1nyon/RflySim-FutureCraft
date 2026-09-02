param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'config/env_template.bat',
    'config/stage5_behavior_tree.json',
    'config/stage5_live_mission.json',
    'future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/live_smoke_runbook.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py',
    'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py',
    'scripts/start_two_uav.bat',
    'scripts/start_mission_executor_sim_arm.bat',
    'scripts/validate_stage6b.ps1',
    'tests/fixtures/stage6c/expected_live_smoke_runbook.json'
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
    $outputDir = Join-Path $env:TEMP ("future_aircraft_stage6c_{0}" -f $PID)
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $planOutputPath = Join-Path $outputDir 'live_mission_plan.json'
    $runbookOutputPath = Join-Path $outputDir 'live_smoke_runbook.json'
    foreach ($path in @($planOutputPath, $runbookOutputPath)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }

    $generatorScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py'
    $runbookScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/live_smoke_runbook.py'
    $behaviorConfigPath = Join-Path $ProjectRoot 'config/stage5_behavior_tree.json'
    $liveConfigPath = Join-Path $ProjectRoot 'config/stage5_live_mission.json'
    $envTemplatePath = Join-Path $ProjectRoot 'config/env_template.bat'
    $fixturePath = Join-Path $ProjectRoot 'tests/fixtures/stage6c/expected_live_smoke_runbook.json'

    $generatorOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $generatorScript -Arguments @('--behavior-config', $behaviorConfigPath, '--live-config', $liveConfigPath, '--output', $planOutputPath)
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "live_mission_contract.py failed with exit code ${LASTEXITCODE}: $($generatorOutput -join ' ')"
    }
    elseif (-not (Test-Path -LiteralPath $planOutputPath)) {
        $contractErrors += "live_mission_contract.py did not create output: $planOutputPath"
    }

    if ($contractErrors.Count -eq 0) {
        $runbookOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $runbookScript -Arguments @('--project-root', $ProjectRoot, '--env-template', $envTemplatePath, '--live-config', $liveConfigPath, '--plan', $planOutputPath, '--output', $runbookOutputPath)
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "live_smoke_runbook.py failed with exit code ${LASTEXITCODE}: $($runbookOutput -join ' ')"
        }
        elseif (-not (Test-Path -LiteralPath $runbookOutputPath)) {
            $contractErrors += "live_smoke_runbook.py did not create output: $runbookOutputPath"
        }
        else {
            $actual = Get-Content -Raw -LiteralPath $runbookOutputPath | ConvertFrom-Json
            $expected = Get-Content -Raw -LiteralPath $fixturePath | ConvertFrom-Json
            $expectedWorkspace = @($expected.environment.windows_paths | Where-Object { $_.key -eq 'FUTURE_AIRCRAFT_WS' })
            if ($expectedWorkspace.Count -ne 1) {
                $contractErrors += 'Stage 6C fixture must contain exactly one FUTURE_AIRCRAFT_WS entry'
            }
            else {
                $expectedWorkspace[0].value = Join-Path $ProjectRoot 'future_aircraft_ws'
            }
            if (($actual | ConvertTo-Json -Depth 16 -Compress) -ne ($expected | ConvertTo-Json -Depth 16 -Compress)) {
                $contractErrors += 'live_smoke_runbook.json does not match Stage 6C fixture'
            }
        }
    }

    if ($contractErrors.Count -eq 0) {
        $stage6bScript = Join-Path $ProjectRoot 'scripts/validate_stage6b.ps1'
        $stage6bOutput = & powershell -ExecutionPolicy Bypass -File $stage6bScript -Quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "Stage 6B validation regression failed with exit code ${LASTEXITCODE}: $($stage6bOutput -join ' ')"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 6C live dual-MAVROS smoke runbook validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 6C live dual-MAVROS smoke runbook validation passed.' -ForegroundColor Green
}
exit 0

