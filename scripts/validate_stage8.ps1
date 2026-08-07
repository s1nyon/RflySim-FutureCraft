$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
$geometry = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py'
$artifacts = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_artifacts.py'
$loader = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_ue_loader.py'
$lidarProbe = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\stage8_dynamic_lidar_probe.py'
$cloud = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_cloud_server.py'
$launch = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\launch\predicted_narrow_course.launch'
$spec = Join-Path $projectRoot 'config\maps\predicted_narrow_course_v1.json'
$recorder = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\stage8_control_chain_recorder.py'
$recorderCheck = Join-Path $projectRoot 'tests\stage8_control_chain_recorder_check.py'
$recorderBat = Join-Path $projectRoot 'scripts\run_stage8_control_chain_recorder.bat'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

Push-Location $projectRoot
try {
    Invoke-Checked $python @(
        'tests\stage8_course_geometry_check.py', '--module', $geometry, '--spec', $spec
    )
    Invoke-Checked $python @(
        'tests\stage8_course_artifacts_check.py',
        '--geometry-module', $geometry,
        '--artifact-module', $artifacts,
        '--cloud-module', $cloud,
        '--launch', $launch,
        '--spec', $spec
    )
    Invoke-Checked $python @(
        'tests\stage8_course_ue_loader_check.py',
        '--geometry-module', $geometry,
        '--loader-module', $loader,
        '--spec', $spec
    )
    Invoke-Checked $python @(
        'tests\stage8_dynamic_lidar_probe_check.py', '--module', $lidarProbe
    )
    Invoke-Checked $python @(
        'tests\stage8_probe_slamscene_check.py', '--module', $lidarProbe
    )
    Invoke-Checked $python @(
        'tests\stage8_geofence_check.py',
        '--module', (Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\course_geofence.py'),
        '--watchdog', (Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\course_geofence_watchdog.py')
    )
    Invoke-Checked $python @(
        'tests\stage8_watchdog_events_check.py',
        '--module', (Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\course_geofence.py'),
        '--watchdog', (Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\course_geofence_watchdog.py')
    )
    Invoke-Checked $python @(
        'tests\stage8_course_flight_plan_check.py',
        '--plan-module', (Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\stage7_flight_plan.py'),
        '--config', (Join-Path $projectRoot 'config\stage7_live_slam_ego_swarm.json'),
        '--course-spec', $spec,
        '--dual-launch', (Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\launch\rflysim_ego_swarm_dual.launch')
    )
    Invoke-Checked $python @('tests\stage8_course_launch_check.py', '--project-root', $projectRoot)

    if (-not (Test-Path -LiteralPath $recorder) -or
        -not (Test-Path -LiteralPath $recorderCheck) -or
        -not (Test-Path -LiteralPath $recorderBat)) {
        throw 'Stage 8 control-chain recorder script, test, or launcher is missing'
    }
    $recorderText = Get-Content -Raw -LiteralPath $recorder
    foreach ($banned in @('rospy\.Publisher', 'ServiceProxy', '\.publish\(', 'set_mode', 'arming', 'OFFBOARD', 'allow-arm')) {
        if ($recorderText -match $banned) {
            throw "Stage 8 recorder must be read-only (no $banned): $recorder"
        }
    }
    Invoke-Checked $python @(
        'tests\stage8_control_chain_recorder_check.py',
        '--recorder-module', $recorder,
        '--config', (Join-Path $projectRoot 'config\stage7_live_slam_ego_swarm.json')
    )
    $recorderBatText = Get-Content -Raw -LiteralPath $recorderBat
    if ($recorderBatText -notmatch 'REF_28COM_UAV_WSL_DIR%/devel/setup\.bash') {
        throw 'run_stage8_control_chain_recorder.bat must source the 28com_uav workspace for quadrotor_msgs'
    }
    $recorderEgoIndex = $recorderBatText.IndexOf('%EGO_SWARM_WSL_DIR%/devel/setup.bash')
    $recorder28Index = $recorderBatText.IndexOf('REF_28COM_UAV_WSL_DIR%/devel/setup.bash')
    $recorderProjectIndex = $recorderBatText.IndexOf('%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash')
    if ($recorderEgoIndex -lt 0 -or $recorderEgoIndex -lt $recorder28Index -or $recorderProjectIndex -lt $recorderEgoIndex) {
        throw 'run_stage8_control_chain_recorder.bat must source ego-planner-swarm after 28com_uav and before the project overlay so quadrotor_msgs matches the planner publisher'
    }
    Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\run_stage8_control_chain_recorder.bat', '--dry-run')

    Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\generate_predicted_narrow_course.bat', '--dry-run')
    Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\start_predicted_course_two_uav.bat', '--dry-run')

    $tempBase = [System.IO.Path]::GetTempPath()
    $tempA = Join-Path $tempBase ("future_aircraft_stage8_a_" + [Guid]::NewGuid().ToString('N'))
    $tempB = Join-Path $tempBase ("future_aircraft_stage8_b_" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempA, $tempB | Out-Null
    try {
        Invoke-Checked $python @($artifacts, '--spec', $spec, '--output', $tempA)
        Invoke-Checked $python @($artifacts, '--spec', $spec, '--output', $tempB)
        $filesA = @(Get-ChildItem -File -LiteralPath $tempA | Sort-Object Name)
        $filesB = @(Get-ChildItem -File -LiteralPath $tempB | Sort-Object Name)
        if ($filesA.Count -ne 5 -or $filesB.Count -ne 5) {
            throw "Expected five generated artifacts in each deterministic output set"
        }
        for ($index = 0; $index -lt $filesA.Count; $index++) {
            if ($filesA[$index].Name -ne $filesB[$index].Name) {
                throw "Generated artifact names differ"
            }
            $hashA = (Get-FileHash -Algorithm SHA256 -LiteralPath $filesA[$index].FullName).Hash
            $hashB = (Get-FileHash -Algorithm SHA256 -LiteralPath $filesB[$index].FullName).Hash
            if ($hashA -ne $hashB) {
                throw "Generated artifact differs: $($filesA[$index].Name)"
            }
        }
    }
    finally {
        $resolvedTemp = [System.IO.Path]::GetFullPath($tempBase)
        foreach ($candidate in @($tempA, $tempB)) {
            $resolvedCandidate = [System.IO.Path]::GetFullPath($candidate)
            if (-not $resolvedCandidate.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove non-temporary path: $resolvedCandidate"
            }
            if (Test-Path -LiteralPath $resolvedCandidate) {
                Remove-Item -Recurse -Force -LiteralPath $resolvedCandidate
            }
        }
    }

    Invoke-Checked 'git.exe' @('diff', '--check')
    Invoke-Checked 'powershell.exe' @('-ExecutionPolicy', 'Bypass', '-File', 'scripts\validate_stage7.ps1')
    Write-Output '[PASS] Stage 8 predicted narrow course offline validation PASS'
}
finally {
    Pop-Location
}
