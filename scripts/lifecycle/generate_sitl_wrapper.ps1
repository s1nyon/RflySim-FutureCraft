param(
    [Parameter(Mandatory = $true)][string]$SourceScript,
    [Parameter(Mandatory = $true)][string]$Output
)

# P0.1: generate the two-UAV SITL wrapper from the 28com UAVSITL.bat reference.
# - strips administrator/elevation and the name-based kill block;
# - replaces GUI starts with register_launcher.py so PIDs are registered at creation;
# - CopterSim instances are stack-scoped + instance-scoped (gui:CopterSim/uavN with
#   per-instance pid files); the loop must NEVER use a global "any CopterSim.exe" guard;
# - injects the real 28com_SITL directory so %~dp0-relative resources (UAVSITL.py)
#   resolve regardless of where the generated wrapper is placed;
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

$sitlDir = Split-Path -Parent $SourceScript
$sitlDirEscaped = $sitlDir.Replace('%', '%%').Replace('&', '^&')
# NOTE: build concatenated lines BEFORE the array literal - inside @(...)
# PowerShell parses `'a' + $var + 'b'` as three separate array elements.
$uavSitlDirLine = 'set "UAV_SITL_DIR=' + $sitlDirEscaped + '"'

$traceHeader = @(
    'set SITL_TRACE=%TEMP%\sitl_wrapper_trace.txt',
    'echo === wrapper start %DATE% %TIME% === > "%SITL_TRACE%"',
    'echo STACK_ID=%STACK_ID% STACK_MANIFEST=%STACK_MANIFEST% PYTHON_EXE=%PYTHON_EXE% >> "%SITL_TRACE%"',
    $uavSitlDirLine,
    'echo UAV_SITL_DIR=%UAV_SITL_DIR% >> "%SITL_TRACE%"',
    'set "STACK_PID_DIR="',
    'if defined STACK_MANIFEST for %%I in ("%STACK_MANIFEST%") do set "STACK_PID_DIR=%%~dpI"',
    'if defined STACK_PID_DIR if not exist "%STACK_PID_DIR%pids" mkdir "%STACK_PID_DIR%pids"',
    'echo STACK_PID_DIR=%STACK_PID_DIR% >> "%SITL_TRACE%"',
    'if not defined STACK_MANIFEST goto manifest_wsl_done',
    'powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\to_wsl_path.ps1" -Path "%STACK_MANIFEST%" -OutFile "%TEMP%\stack_manifest_wsl.txt"',
    'if errorlevel 1 echo [ERROR] manifest WSL path conversion failed >> "%SITL_TRACE%"',
    'set STACK_MANIFEST_WSL=',
    'for /f "usebackq delims=" %%P in ("%TEMP%\stack_manifest_wsl.txt") do set STACK_MANIFEST_WSL=%%P',
    'echo STACK_MANIFEST_WSL=%STACK_MANIFEST_WSL% >> "%SITL_TRACE%"',
    ':manifest_wsl_done'
) -join [Environment]::NewLine
$src = $traceHeader + [Environment]::NewLine + $src

$src = $src.Replace('echo Press any key to exit; read -n 1', 'echo FutureAircraftSim SITL running. Close this WSL process or window to stop.; tail -f /dev/null')
$src = $src.Replace('SET PosXStr=-0.1', 'SET PosXStr=' + $env:STAGE2_POS_X_STR)
$src = $src.Replace('SET PosYStr=-0.8', 'SET PosYStr=' + $env:STAGE2_POS_Y_STR)
$src = $src.Replace('SET YawStr=0', 'SET YawStr=' + $env:STAGE2_YAW_STR)
$src = $src.Replace('SET UE4_MAP=ChallengeMap', 'SET UE4_MAP=' + $env:RFLYSIM_UE4_MAP)

$q = [char]34
$wslLaunch = 'wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic ' + $q + 'export STACK_MANIFEST=''%STACK_MANIFEST_WSL%''; export RFLY_STACK_ID=''%STACK_ID%''; export RFLY_SIM_INSTANCE_ID=''%STACK_ID%''; source ''%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/lifecycle_common.sh''; stack_register wsl $$ $$ wsl:px4_build_session sitl_multiple_run_rfly.sh created-by-stack-sitl-wrapper; echo Starting PX4 Build; cd %PSP_PATH_LINUX%/Firmware; ./BkFile/EnvOri.sh; export PATH=$HOME/ninja:$HOME/gcc-arm-none-eabi-7-2017-q4-major/bin:$PATH; make px4_sitl_default; ./Tools/sitl_multiple_run_rfly.sh %VehicleNum% %START_INDEX% %PX4SitlFrame%; python3 ''%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/lifecycle/spawn_attest.py'' attest --parent-pid $$ > /tmp/px4_attest.log 2>&1; echo [STACK] px4 attestation exit=$? >> /tmp/px4_attest.log; cat /tmp/px4_attest.log; echo FutureAircraftSim SITL running. Close this WSL process or window to stop.; tail -f /dev/null' + $q
$wslLaunchLine = '    ' + $wslLaunch
$wslBlock = @(
    'echo [STACK] wsl px4 launch section start >> "%SITL_TRACE%"',
    'if defined STACK_MANIFEST if not defined STACK_MANIFEST_WSL goto manifest_wsl_failed',
    'goto wsl_px4_launch',
    ':manifest_wsl_failed',
    'echo [ERROR] STACK_MANIFEST_WSL empty; PX4 would be unowned; NOT launching >> "%SITL_TRACE%"',
    'echo [STACK] PX4 NOT launched (manifest WSL path conversion failed) >> "%SITL_TRACE%"',
    'goto after_wsl_launch',
    ':wsl_px4_launch',
    $wslLaunchLine,
    ':after_wsl_launch'
) -join [Environment]::NewLine
$src = [regex]::Replace($src, '(?m)^\s*wsl -d RflySim-20\.04 echo Starting PX4 Build;[^\r\n]*tail -f /dev/null\r?$', { param($m) $wslBlock })

$rfly3dOld = 'tasklist|find /i "RflySim3D.exe" || start %PSP_PATH%\RflySim3D\RflySim3D.exe -cmd=RflyChangeMapbyName-%UE4_MAP%'
$rfly3dNew = @'
tasklist|find /i "RflySim3D.exe" >nul && echo [STACK] RflySim3D already running; not created by this stack (will be unknown) && goto rfly3d_done
if not defined STACK_MANIFEST goto rfly3d_plain
del /q "%STACK_PID_DIR%pids\rflysim3d.pid" >nul 2>&1
"%PYTHON_EXE%" "%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role gui:RflySim3D --command-line "%PSP_PATH%\RflySim3D\RflySim3D.exe -cmd=RflyChangeMapbyName-%UE4_MAP%" --file-path "%PSP_PATH%\RflySim3D\RflySim3D.exe" --arguments "-cmd=RflyChangeMapbyName-%UE4_MAP%" --pid-file "%STACK_PID_DIR%pids\rflysim3d.pid" >> "%SITL_TRACE%" 2>&1
set /p RFLYSIM3D_PID=<"%STACK_PID_DIR%pids\rflysim3d.pid"
echo rfly3d registered pid=%RFLYSIM3D_PID% >> "%SITL_TRACE%"
"%PYTHON_EXE%" "%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.py" attach-children --manifest "%STACK_MANIFEST%" --parent-pid %RFLYSIM3D_PID% --role-prefix gui:RflySim3D --exe-fragment "RflySim3D\Binaries\Win64\RflySim3D.exe" --max-wait 20 >> "%SITL_TRACE%" 2>&1
echo rfly3d child attach done >> "%SITL_TRACE%"
goto rfly3d_done
:rfly3d_plain
echo rfly3d plain start (no STACK_MANIFEST) >> "%SITL_TRACE%"
start %PSP_PATH%\RflySim3D\RflySim3D.exe -cmd=RflyChangeMapbyName-%UE4_MAP%
:rfly3d_done
echo rfly3d done >> "%SITL_TRACE%"
'@
$src = $src.Replace($rfly3dOld, $rfly3dNew.TrimEnd("`r", "`n"))

$qgcOld = 'tasklist|find /i "QGroundControl.exe" || start %PSP_PATH%\QGroundControl\QGroundControl.exe -noComPix'
$qgcNew = @'
tasklist|find /i "QGroundControl.exe" >nul && echo [STACK] QGroundControl already running; not created by this stack (will be unknown) && goto qgc_done
if not defined STACK_MANIFEST goto qgc_plain
del /q "%STACK_PID_DIR%pids\qgc.pid" >nul 2>&1
"%PYTHON_EXE%" "%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role gui:QGroundControl --command-line "%PSP_PATH%\QGroundControl\QGroundControl.exe -noComPix" --file-path "%PSP_PATH%\QGroundControl\QGroundControl.exe" --arguments "-noComPix" --pid-file "%STACK_PID_DIR%pids\qgc.pid" >> "%SITL_TRACE%" 2>&1
set /p QGC_PID=<"%STACK_PID_DIR%pids\qgc.pid"
echo qgc registered pid=%QGC_PID% >> "%SITL_TRACE%"
goto qgc_done
:qgc_plain
echo qgc plain start (no STACK_MANIFEST) >> "%SITL_TRACE%"
start %PSP_PATH%\QGroundControl\QGroundControl.exe -noComPix
:qgc_done
echo qgc done >> "%SITL_TRACE%"
'@
$src = $src.Replace($qgcOld, $qgcNew.TrimEnd("`r", "`n"))

$src = [regex]::Replace($src, '(?m)^(\s*)start /realtime CopterSim\.exe ([^\r]*?)\r?$', {
    param($m)
    $indent = $m.Groups[1].Value
    $args2 = $m.Groups[2].Value
    $block = @(
        "set COPTER_PID_FILE=%STACK_PID_DIR%pids\copter_uav%cntr%.pid",
        # NOTE: do NOT put parentheses in echo text inside parenthesized blocks
        # ("starting was unexpected at this time") and do NOT gate on
        # `set VAR=` + `if defined` (an empty-but-defined var is still defined).
        "if not exist `"%COPTER_PID_FILE%`" goto copter_start",
        "set /p EXISTING_COPTER_PID=<`"%COPTER_PID_FILE%`"",
        "tasklist /FI `"PID eq %EXISTING_COPTER_PID%`" 2>nul | find /i `"CopterSim.exe`" >nul",
        "if not errorlevel 1 (",
        "  echo [STACK] copter uav%cntr% already running pid=%EXISTING_COPTER_PID%; skipping >> `"%SITL_TRACE%`"",
        "  goto copter_done",
        ")",
        "echo [STACK] copter uav%cntr% pid file stale; starting fresh >> `"%SITL_TRACE%`"",
        ":copter_start",
        "if not defined STACK_MANIFEST goto copter_plain",
        "`"%PYTHON_EXE%`" `"%FUTURE_AIRCRAFT_SIM_DIR%\scripts\lifecycle\register_launcher.py`" launch --manifest `"%STACK_MANIFEST%`" --role `"gui:CopterSim/uav%cntr%`" --instance-marker `"uav%cntr%`" --command-line `"CopterSim.exe $args2`" --file-path `"%PSP_PATH%\CopterSim\CopterSim.exe`" --arguments `"$args2`" --working-directory `"%PSP_PATH%\CopterSim`" --pid-file `"%COPTER_PID_FILE%`" >> `"%SITL_TRACE%`" 2>&1",
        "if errorlevel 1 echo [ERROR] copter uav%cntr% launch/registration failed >> `"%SITL_TRACE%`"",
        "set /p COPTER_PID=<`"%COPTER_PID_FILE%`"",
        "echo copter uav%cntr% registered pid=%COPTER_PID% >> `"%SITL_TRACE%`"",
        "goto copter_done",
        ":copter_plain",
        "echo copter plain start (no STACK_MANIFEST) >> `"%SITL_TRACE%`"",
        "  start /realtime CopterSim.exe $args2",
        ":copter_done",
        "echo copter uav%cntr% done >> `"%SITL_TRACE%`""
    )
    ($indent + ($block -join ([Environment]::NewLine + $indent)))
})

# Remove every name-based kill that survives from the 28com reference.
$src = $src.Replace('tasklist|find /i "CopterSim.exe" && taskkill /im "CopterSim.exe"', 'rem [STACK] name-based kill removed; report unknown instead of killing')
$src = $src.Replace('ECHO Kill all CopterSims', 'ECHO Start stack-owned CopterSims')
$src = $src.Replace('tasklist|find /i "QGroundControl.exe" && taskkill /f /im "QGroundControl.exe"', 'rem [STACK] name-based kill removed; report unknown instead of killing')
$src = $src.Replace('tasklist|find /i "RflySim3D.exe" && taskkill /f /im "RflySim3D.exe"', 'rem [STACK] name-based kill removed; report unknown instead of killing')

# UAVSITL.py and any other %~dp0-relative resource must resolve against the real
# 28com_SITL source directory, never against the generated wrapper's location.
$src = $src.Replace('%~dp0\', '%UAV_SITL_DIR%\')
$src = $src.Replace('%~dp0', '%UAV_SITL_DIR%')
$src = [regex]::Replace($src, '(?m)^(\s*)(start /B /separate %PSP_PATH%\\Python38\\python\.exe "%UAV_SITL_DIR%\\UAVSITL\.py")', {
    param($m)
    ($m.Groups[1].Value + 'echo launching UAVSITL.py from %UAV_SITL_DIR% >> "%SITL_TRACE%"' + [Environment]::NewLine + $m.Groups[1].Value + $m.Groups[2].Value)
})

Set-Content -LiteralPath $Output -Value $src -Encoding ASCII
Write-Output "[OK] Generated $Output"
