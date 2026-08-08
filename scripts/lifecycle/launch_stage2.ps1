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
if (-not $Stage2Script) {
    $Stage2Script = 'D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\future_aircraft_sim\scripts\wsl\stage2_two_mavros.sh'
}
$wslScript = $Stage2Script.Replace('\', '/')
if ($HealthDirWsl) {
    $bashCmd = "STACK_HEALTH_DIR='$HealthDirWsl' STACK_ID='$StackId' STACK_MANIFEST='$ManifestWsl' bash '$wslScript'"
} else {
    $bashCmd = "bash '$wslScript'"
}
$out = Join-Path $env:TEMP 'stage2_wsl.log'
$err = Join-Path $env:TEMP 'stage2_wsl.err.log'
$proc = Start-Process -FilePath 'wsl.exe' `
    -ArgumentList @('-d', 'RflySim-20.04', '-e', 'bash', '-lic', $bashCmd) `
    -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
Write-Output "stage2 wsl pid=$($proc.Id)"
exit 0
