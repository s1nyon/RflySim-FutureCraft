param(
    [string]$HealthDirWsl = '',
    [string]$StackId = '',
    [string]$ManifestWsl = '',
    [string]$Stage2Script = ''
)

# Reliably launch the WSL Stage 2 (roscore + dual MAVROS) as a detached process.
# Uses Start-Process (not cmd `start`) so it works in scheduled-task and
# non-interactive contexts. Stage 2 registers its own processes at creation.
$ErrorActionPreference = 'Stop'

function Write-Stage2Trace {
    param([Parameter(Mandatory = $true)][string]$Message)
    if (-not $StackId) { return }
    $project = Split-Path -Parent $PSScriptRoot
    $project = Split-Path -Parent $project
    $trace = Join-Path $project "logs\live_stack\$StackId\mavros_launch.log"
    try {
        Add-Content -LiteralPath $trace -Value ("{0} mavros_wrapper: {1}" -f (Get-Date -Format 'HH:mm:ss.fff'), $Message) -Encoding ASCII
    } catch {
        # Trace is best-effort; never block the launcher on a trace write failure.
    }
}

Write-Stage2Trace -Message 'launch_stage2: step D1 start (resolving stage2 script)'
if (-not $Stage2Script) {
    $Stage2Script = 'D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\future_aircraft_sim\scripts\wsl\stage2_two_mavros.sh'
}
if ($Stage2Script -match '^([A-Za-z]):\\(.*)$') {
    $wslScript = '/mnt/' + $matches[1].ToLower() + '/' + $matches[2].Replace('\', '/')
} else {
    $wslScript = $Stage2Script.Replace('\', '/')
}
Write-Stage2Trace -Message "launch_stage2: step D1 success wslScript=$wslScript"

Write-Stage2Trace -Message 'launch_stage2: step D2 start (build bash command)'
if ($HealthDirWsl) {
    $bashCmd = "STACK_HEALTH_DIR='$HealthDirWsl' STACK_ID='$StackId' STACK_MANIFEST='$ManifestWsl' bash '$wslScript'"
} else {
    $bashCmd = "bash '$wslScript'"
}
Write-Stage2Trace -Message 'launch_stage2: step D2 success'

Write-Stage2Trace -Message 'launch_stage2: step D3 start (Start-Process wsl.exe)'
$out = Join-Path $env:TEMP 'stage2_wsl.log'
$err = Join-Path $env:TEMP 'stage2_wsl.err.log'
$quotedCmd = '"' + $bashCmd.Replace('"', '\"') + '"'
try {
    $proc = Start-Process -FilePath 'wsl.exe' `
        -ArgumentList @('-d', 'RflySim-20.04', '-e', 'bash', '-lic', $quotedCmd) `
        -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
} catch {
    Write-Stage2Trace -Message "launch_stage2: step D3 FAILED ($($_.Exception.Message))"
    Write-Error "launch_stage2: failed to start wsl.exe: $($_.Exception.Message)"
    exit 1
}
Write-Stage2Trace -Message "launch_stage2: step D3 success wsl_pid=$($proc.Id)"
Write-Output "stage2 wsl pid=$($proc.Id)"
exit 0
