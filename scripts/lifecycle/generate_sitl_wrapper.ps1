param(
    [Parameter(Mandatory = $true)][string]$SourceScript,
    [Parameter(Mandatory = $true)][string]$Output
)

# P0.1: generate the two-UAV SITL wrapper from the 28com UAVSITL.bat reference.
# - strips administrator/elevation and the name-based kill block;
# - replaces GUI starts with register_launcher.ps1 so PIDs are registered at creation;
# - keeps noninteractive PX4 SITL keepalive.
$ErrorActionPreference = 'Stop'

$lines = Get-Content -LiteralPath $SourceScript
$kept = New-Object System.Collections.Generic.List[string]
foreach ($line in $lines) {
    if ($line -match '^NET SESSION ') { continue }
    if ($line -match '^REM kill all applications when press a key') {
        $kept.Add('REM FutureAircraftSim: original automatic cleanup block removed for noninteractive live runs.')
        $kept.Add('ECHO FutureAircraftSim SITL wrapper ended without automatic cleanup.')
        break
    }
    $kept.Add($line)
}
$src = ($kept -join [Environment]::NewLine)

$src = $src.Replace('echo Press any key to exit; read -n 1', 'echo FutureAircraftSim SITL running. Close this WSL process or window to stop.; tail -f /dev/null')
$src = $src.Replace('SET PosXStr=-0.1', 'SET PosXStr=' + $env:STAGE2_POS_X_STR)
$src = $src.Replace('SET PosYStr=-0.8', 'SET PosYStr=' + $env:STAGE2_POS_Y_STR)
$src = $src.Replace('SET YawStr=0', 'SET YawStr=' + $env:STAGE2_YAW_STR)
$src = $src.Replace('SET UE4_MAP=ChallengeMap', 'SET UE4_MAP=' + $env:RFLYSIM_UE4_MAP)

$q = [char]34
$new = 'wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic ' + $q + 'echo Starting PX4 Build; cd %PSP_PATH_LINUX%/Firmware; ./BkFile/EnvOri.sh; export PATH=$HOME/ninja:$HOME/gcc-arm-none-eabi-7-2017-q4-major/bin:$PATH; make px4_sitl_default; ./Tools/sitl_multiple_run_rfly.sh %VehicleNum% %START_INDEX% %PX4SitlFrame%; echo FutureAircraftSim SITL running. Close this WSL process or window to stop.; tail -f /dev/null' + $q
$src = [regex]::Replace($src, '(?m)^\s*wsl -d RflySim-20\.04 echo Starting PX4 Build;[^\r\n]*tail -f /dev/null\r?$', { param($m) '    ' + $new })

$launcherPs1 = '%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.ps1'

$rfly3dOld = 'tasklist|find /i "RflySim3D.exe" || start %PSP_PATH%\RflySim3D\RflySim3D.exe -cmd=RflyChangeMapbyName-%UE4_MAP%'
$rfly3dNew = @'
tasklist|find /i "RflySim3D.exe" >nul && echo [STACK] RflySim3D already running; not created by this stack (will be unknown) && goto rfly3d_done
if defined STACK_MANIFEST (
  for /f "delims=" %%p in ('powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.ps1" -Manifest "%STACK_MANIFEST%" -Role gui:RflySim3D -FilePath "%PSP_PATH%\RflySim3D\RflySim3D.exe" -Arguments "-cmd=RflyChangeMapbyName-%UE4_MAP%"') do set RFLYSIM3D_PID=%%p
) else (
  start %PSP_PATH%\RflySim3D\RflySim3D.exe -cmd=RflyChangeMapbyName-%UE4_MAP%
)
:rfly3d_done
'@
$src = $src.Replace($rfly3dOld, $rfly3dNew.TrimEnd("`r", "`n"))

$qgcOld = 'tasklist|find /i "QGroundControl.exe" || start %PSP_PATH%\QGroundControl\QGroundControl.exe -noComPix'
$qgcNew = @'
tasklist|find /i "QGroundControl.exe" >nul && echo [STACK] QGroundControl already running; not created by this stack (will be unknown) && goto qgc_done
if defined STACK_MANIFEST (
  for /f "delims=" %%p in ('powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.ps1" -Manifest "%STACK_MANIFEST%" -Role gui:QGroundControl -FilePath "%PSP_PATH%\QGroundControl\QGroundControl.exe" -Arguments "-noComPix"') do set QGC_PID=%%p
) else (
  start %PSP_PATH%\QGroundControl\QGroundControl.exe -noComPix
)
:qgc_done
'@
$src = $src.Replace($qgcOld, $qgcNew.TrimEnd("`r", "`n"))

$src = [regex]::Replace($src, '(?m)^(\s*)start /realtime CopterSim\.exe (.*)$', {
    param($m)
    $indent = $m.Groups[1].Value
    $args2 = $m.Groups[2].Value
    $block = @(
        "tasklist|find /i `"CopterSim.exe`" >nul && echo [STACK] CopterSim already running; not created by this stack (will be unknown) && goto copter_done",
        "if defined STACK_MANIFEST (",
        "  for /f `"delims=`" %%p in ('powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.ps1`" -Manifest `"%STACK_MANIFEST%`" -Role gui:CopterSim -FilePath `"%PSP_PATH%\CopterSim\CopterSim.exe`" -Arguments `"$args2`" -WorkingDirectory `"%PSP_PATH%\CopterSim`"') do set COPTER_PID=%%p",
        ") else (",
        "  start /realtime CopterSim.exe $args2",
        ")",
        ":copter_done"
    )
    ($indent + ($block -join [Environment]::NewLine + $indent))
})

# Remove every name-based kill that survives from the 28com reference.
$src = $src.Replace('tasklist|find /i "CopterSim.exe" && taskkill /im "CopterSim.exe"', 'rem [STACK] name-based kill removed; report unknown instead of killing')
$src = $src.Replace('tasklist|find /i "QGroundControl.exe" && taskkill /f /im "QGroundControl.exe"', 'rem [STACK] name-based kill removed; report unknown instead of killing')
$src = $src.Replace('tasklist|find /i "RflySim3D.exe" && taskkill /f /im "RflySim3D.exe"', 'rem [STACK] name-based kill removed; report unknown instead of killing')

Set-Content -LiteralPath $Output -Value $src -Encoding ASCII
Write-Output "[OK] Generated $Output"
