$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
$geometry = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py'
$artifacts = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_artifacts.py'
$loader = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_ue_loader.py'
$cloud = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_cloud_server.py'
$launch = Join-Path $projectRoot 'future_aircraft_ws\src\multi_uav_mission\launch\predicted_narrow_course.launch'
$spec = Join-Path $projectRoot 'config\maps\predicted_narrow_course_v1.json'

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
    Invoke-Checked $python @('tests\stage8_course_launch_check.py', '--project-root', $projectRoot)

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
