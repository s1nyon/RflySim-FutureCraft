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
    'scripts/validate_stage5.ps1',
    'tests/fixtures/stage5b/expected_live_mission_plan.json'
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
    $outputDir = Join-Path $env:TEMP ("future_aircraft_stage5b_{0}" -f $PID)
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $planOutputPath = Join-Path $outputDir 'live_mission_plan.json'
    if (Test-Path -LiteralPath $planOutputPath) { Remove-Item -LiteralPath $planOutputPath -Force }

    $generatorScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py'
    $behaviorConfigPath = Join-Path $ProjectRoot 'config/stage5_behavior_tree.json'
    $liveConfigPath = Join-Path $ProjectRoot 'config/stage5_live_mission.json'
    $expectedPath = Join-Path $ProjectRoot 'tests/fixtures/stage5b/expected_live_mission_plan.json'

    $generatorOutput = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $generatorScript -Arguments @('--behavior-config', $behaviorConfigPath, '--live-config', $liveConfigPath, '--output', $planOutputPath)
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "live_mission_contract.py failed with exit code ${LASTEXITCODE}: $($generatorOutput -join ' ')"
    }
    elseif (-not (Test-Path -LiteralPath $planOutputPath)) {
        $contractErrors += "live_mission_contract.py did not create output: $planOutputPath"
    }
    else {
        $actual = Get-Content -Raw -LiteralPath $planOutputPath | ConvertFrom-Json
        $expected = Get-Content -Raw -LiteralPath $expectedPath | ConvertFrom-Json
        if ((ConvertTo-StableJson $actual) -ne (ConvertTo-StableJson $expected)) {
            $contractErrors += 'live_mission_plan.json does not match Stage 5B fixture'
        }
    }

    if ($contractErrors.Count -eq 0) {
        $stage5Script = Join-Path $ProjectRoot 'scripts/validate_stage5.ps1'
        $stage5Output = & powershell -ExecutionPolicy Bypass -File $stage5Script -Quiet 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "Stage 5 validation regression failed with exit code ${LASTEXITCODE}: $($stage5Output -join ' ')"
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 5B live mission boundary validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 5B live mission boundary validation passed.' -ForegroundColor Green
}
exit 0

