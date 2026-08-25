$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = 'D:\PX4PSP\Python38\python.exe'

$tests = @(
    'competition_course_v2_substrate_check.py',
    'course_layer_transition_check.py',
    'competition_course_v2_geometry_check.py',
    'competition_course_v2_clearance_check.py',
    'competition_course_v2_preview_check.py',
    'competition_course_v2_evaluation_reference_check.py',
    'competition_course_v2_artifacts_check.py',
    'competition_course_v2_loader_check.py',
    'competition_course_v2_motion_check.py',
    'competition_course_v2_entrypoint_check.py',
    'competition_course_v2_live_probe_check.py'
)
foreach ($test in $tests) {
    & $Python (Join-Path $ProjectRoot "tests\$test") --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& (Join-Path $PSScriptRoot 'generate_competition_course_v2.bat') --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'generate_competition_course_v2.bat')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'deploy_competition_course_v2_terrain.bat') --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'load_competition_course_v2.bat') --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m py_compile `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_geometry.py') `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_spawn_args.py') `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\course_layer_transition.py') `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_artifacts.py') `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_ue_loader.py') `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_motion.py') `
    (Join-Path $ProjectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_live_probe.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host '[PASS] Competition Course V2 structural validation PASS'
exit 0
