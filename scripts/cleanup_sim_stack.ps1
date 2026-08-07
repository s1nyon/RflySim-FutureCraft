param(
    [switch]$DryRun
)

# Cleanup script for the RflySim/PX4/ROS simulation stack started by
# scripts\start_predicted_course_two_uav.bat (or the Session-1 scheduled task).
#
# Terminates, in order:
#   1. Windows GUI processes (RflySim3D, CopterSim, QGroundControl)
#   2. cmd windows that orchestrate SITL / MAVROS / course startup
#   3. WSL-side ROS/PX4/planner/sensor processes and then WSL itself
#   4. the "FutureAircraftSim_LiveStack_Session1" scheduled task if present
#
# It is idempotent and reports what was terminated. It never deletes files and
# never touches cc-connect / codex processes.

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$simGuiPatterns = @('RflySim3D', 'CopterSim', 'QGroundControl')
$stageCmdPatterns = @(
    'future_aircraft_stage2',
    'start_rflysim_sitl_two',
    'start_wsl_mavros_two',
    'start_predicted_course',
    'start_two_uav'
)

function Invoke-CleanupStep {
    param(
        [string]$Name,
        [scriptblock]$Body
    )
    Write-Host "[cleanup] $Name"
    if (-not $DryRun) {
        & $Body
    }
}

Invoke-CleanupStep -Name 'kill GUI simulation processes' -Body {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $simGuiPatterns -contains $_.ProcessName } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

Invoke-CleanupStep -Name 'kill stage orchestration cmd windows' -Body {
    $cmdProcesses = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object {
            $commandLine = [string]$_.CommandLine
            $stageCmdPatterns | Where-Object { $commandLine -match $_ } | Select-Object -First 1
        }
    foreach ($process in $cmdProcesses) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Invoke-CleanupStep -Name 'kill WSL-side stage/ROS/PX4 processes' -Body {
    wsl -d RflySim-20.04 -e bash -lic @"
pkill -9 -f stage7_live_fastlio 2>/dev/null
pkill -9 -f stage7_live_ego 2>/dev/null
pkill -9 -f stage8_chain_recorder 2>/dev/null
pkill -9 -f stage8_control_chain_recorder 2>/dev/null
pkill -9 -f rflysim_sensor_bridge.py 2>/dev/null
pkill -9 -f rflysim_fastlio_dual 2>/dev/null
pkill -9 -f ego_planner_node 2>/dev/null
pkill -9 -f traj_server 2>/dev/null
pkill -9 -f waypoint_generator 2>/dev/null
pkill -9 -f mission_executor 2>/dev/null
pkill -9 -f stage2_two_mavros 2>/dev/null
pkill -9 -f px4-mavlink 2>/dev/null
pkill -9 -f rflysim_mavros_px4.launch 2>/dev/null
pkill -9 -f roscore 2>/dev/null
pkill -9 -x px4 2>/dev/null
exit 0
"@ 2>$null
}

Invoke-CleanupStep -Name 'shutdown WSL' -Body {
    wsl --shutdown 2>$null
    Start-Sleep -Seconds 4
}

Invoke-CleanupStep -Name 'delete Session-1 live-stack scheduled task' -Body {
    schtasks /delete /tn "\FutureAircraftSim_LiveStack_Session1" /f 2>$null
}

Start-Sleep -Seconds 2

$remainingCmd = @(
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object {
            $commandLine = [string]$_.CommandLine
            $stageCmdPatterns | Where-Object { $commandLine -match $_ } | Select-Object -First 1
        }
).Count
$remainingGui = @(
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $simGuiPatterns -contains $_.ProcessName }
).Count
$remainingWsl = 0
if (-not $DryRun) {
    $remainingWsl = (
        wsl -d RflySim-20.04 -e bash -lic "ps -eo pid,args | grep -E '[p]x4|[r]oscore|[m]avros|[s]ensor_bridge|[s]tage' | grep -v grep | wc -l" 2>$null |
            Out-String
    ).Trim()
}

Write-Host "[cleanup] remaining cmd=$remainingCmd gui=$remainingGui wsl=$remainingWsl"
if (($remainingCmd -eq 0) -and ($remainingGui -eq 0) -and ($remainingWsl -eq 0 -or $DryRun)) {
    Write-Host '[cleanup] stack is clean.'
    exit 0
}
Write-Host '[cleanup] WARNING: some processes remain; inspect manually.'
exit 1
