param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'python_contract_runner.ps1')

$requiredPaths = @(
    'config/stage4_ego_swarm.json',
    'third_party/ego-planner-swarm',
    'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py',
    'tests/fixtures/stage4/expected_ego_swarm_commands.json'
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
    $outputPath = Join-Path $env:TEMP ("future_aircraft_stage4_ego_swarm_commands_{0}.json" -f $PID)
    if (Test-Path -LiteralPath $outputPath) { Remove-Item -LiteralPath $outputPath -Force }
    $adapterScript = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py'
    $configPath = Join-Path $ProjectRoot 'config/stage4_ego_swarm.json'
    $expectedPath = Join-Path $ProjectRoot 'tests/fixtures/stage4/expected_ego_swarm_commands.json'
    $output = Invoke-ContractPythonScript -Runner $pythonRunner -ScriptPath $adapterScript -Arguments @('--config', $configPath, '--output', $outputPath)
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "ego_swarm_adapter.py failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
    }
    elseif (-not (Test-Path -LiteralPath $outputPath)) {
        $contractErrors += "ego_swarm_adapter.py did not create output: $outputPath"
    }
    else {
        $actual = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
        $expected = Get-Content -Raw -LiteralPath $expectedPath | ConvertFrom-Json
        foreach ($field in @('planner', 'source_dir', 'fallback_mode')) {
            if ($actual.$field -ne $expected.$field) {
                $contractErrors += "ego-swarm command summary mismatch for ${field}: actual=$($actual.$field), expected=$($expected.$field)"
            }
        }
        if ($actual.uavs.Count -ne $expected.uavs.Count) {
            $contractErrors += "ego-swarm command summary UAV count mismatch: actual=$($actual.uavs.Count), expected=$($expected.uavs.Count)"
        }
        else {
            for ($i = 0; $i -lt $expected.uavs.Count; $i++) {
                foreach ($field in @('uav_id', 'namespace', 'odom_topic', 'goal_topic', 'trajectory_topic', 'frame_id', 'launch_command')) {
                    if ($actual.uavs[$i].$field -ne $expected.uavs[$i].$field) {
                        $contractErrors += "ego-swarm command summary mismatch for uavs[$i].${field}: actual=$($actual.uavs[$i].$field), expected=$($expected.uavs[$i].$field)"
                    }
                }
            }
        }
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 4 ego-swarm validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 4 ego-swarm validation passed.' -ForegroundColor Green
}
exit 0

