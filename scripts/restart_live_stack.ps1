param(
    [switch]$DryRun
)

# One-shot stack restart for fresh-instance PBL-1 runs:
#   cleanup_sim_stack.ps1 -> create+run Session-1 scheduled task -> wait for
#   MAVROS connected -> reload predicted narrow course entities.

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$taskName = 'FutureAircraftSim_LiveStack_Session1'
$startup = Join-Path $projectRoot 'scripts\start_predicted_course_two_uav.bat'

& (Join-Path $PSScriptRoot 'cleanup_sim_stack.ps1')
if ($LASTEXITCODE -ne 0 -and -not $DryRun) {
    throw 'cleanup_sim_stack.ps1 did not finish cleanly'
}

if ($DryRun) {
    Write-Host '[dry-run] would create/run scheduled task and load course'
    exit 0
}

schtasks /create /tn "\$taskName" /tr "cmd /c call `"$startup`"" /sc once /st 23:59 /ru "PC-202307281902\Administrator" /rl HIGHEST /f | Out-Null
schtasks /run /tn "\$taskName" | Out-Null
Write-Host '[restart] stack task launched; waiting for MAVROS...'

$deadline = (Get-Date).AddSeconds(180)
$connected = $false
while ((Get-Date) -lt $deadline) {
    $topics = (wsl -d RflySim-20.04 -e bash -lic "timeout 5s rostopic list 2>/dev/null | grep -c 'mavros/state'" 2>$null | Out-String).Trim()
    if ($topics -match '^2$') {
        $state = (wsl -d RflySim-20.04 -e bash -lic "timeout 5s rostopic echo -n 1 /uav1/mavros/state 2>/dev/null | grep connected" 2>$null | Out-String).Trim()
        if ($state -match 'connected: True') {
            $connected = $true
            break
        }
    }
    Start-Sleep -Seconds 5
}
if (-not $connected) {
    throw 'MAVROS did not become connected within 180s; run cleanup and inspect'
}
Write-Host '[restart] MAVROS connected.'

# RflySim3D needs a moment to finish loading the map before entities spawn.
Start-Sleep -Seconds 20
Set-Location $projectRoot
cmd /c call "scripts\load_predicted_narrow_course.bat" 2>&1 | Select-String 'object_count'
Write-Host '[restart] course entities loaded; stack ready.'
