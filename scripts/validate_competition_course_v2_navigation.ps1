param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = 'D:\PX4PSP\Python38\python.exe'
$Scripts = Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts'
$Failures = @()

function Invoke-Check {
    param([string]$Name, [string[]]$Arguments)
    Write-Host "[CHECK] $Name"
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        $script:Failures += "$Name exited $LASTEXITCODE"
    }
}

Push-Location $ProjectRoot
try {
    Invoke-Check 'V2 plan and transform contract' @('tests/competition_course_v2_navigation_plan_check.py', '--project-root', '.')
    Invoke-Check 'executor terminal settle contract' @('tests/mission_executor_terminal_contract_check.py', '--executor-module', 'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py')
    Invoke-Check 'landing disarm contract' @('tests/stage8_landing_disarm_check.py', '--executor-module', 'future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py')
    Invoke-Check 'V2 recorder contract' @('tests/competition_course_v2_navigation_recorder_check.py')
    Invoke-Check 'V2 report contract' @('tests/competition_course_v2_navigation_report_check.py', '--project-root', '.')
    Invoke-Check 'V2 runner contract' @('tests/competition_course_v2_navigation_entrypoint_check.py', '--project-root', '.')
    Invoke-Check 'V2 loader runtime parity' @('tests/competition_course_v2_loader_check.py', '--project-root', '.')
    Invoke-Check 'flight recorder crash-status contract' @('tests/stage7_flight_event_recorder_check.py', '--module', 'future_aircraft_ws/src/multi_uav_mission/scripts/flight_event_recorder.py')

    $Generated = Join-Path $ProjectRoot 'generated\competition_course_v2_navigation'
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    foreach ($Profile in @('short_smoke', 'full_section_a')) {
        $Plan = Join-Path $Generated "${Profile}_plan.json"
        Invoke-Check "generate $Profile plan" @(
            (Join-Path $Scripts 'competition_course_navigation_plan.py'),
            '--config', 'config/stage7_live_slam_ego_swarm.json',
            '--map-spec', 'config/maps/competition_course_v2.json',
            '--navigation-config', 'config/competition_course_v2_navigation.json',
            '--profile', $Profile,
            '--output', $Plan
        )
        Invoke-Check "dry-run $Profile executor" @(
            (Join-Path $Scripts 'mission_executor.py'),
            '--plan', $Plan,
            '--live-config', 'config/stage5_live_mission.json',
            '--backend', 'dry-run',
            '--events', (Join-Path $Generated "${Profile}_dry_events.jsonl"),
            '--trace', (Join-Path $Generated "${Profile}_dry_trace.json"),
            '--score', (Join-Path $Generated "${Profile}_dry_score.json")
        )
    }
} finally {
    Pop-Location
}

if ($Failures.Count -gt 0) {
    $Failures | ForEach-Object { Write-Host "[FAIL] $_" -ForegroundColor Red }
    exit 1
}
Write-Host '[PASS] Competition Course V2 Navigation offline validation' -ForegroundColor Green
exit 0
