#!/usr/bin/env python3
"""Generated SITL wrapper contract:
- CopterSim loop must NOT use a global "any CopterSim.exe" name guard;
- each instance gets a stack-scoped pid file and an instance-scoped role/marker;
- %~dp0-relative resources (UAVSITL.py) resolve to the real 28com_SITL dir;
- WSL manifest path conversion uses to_wsl_path.ps1 (no inline set /p pattern);
- RflySim3D renderer child attach is wired.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


FIXTURE = r"""@ECHO OFF
REM Run script as administrator
NET SESSION >nul 2>&1 || powershell -Command "try {Start-Process cmd -ArgumentList '/c, ""%~f0""' -Verb RunAs} catch {}" && exit /b

if not defined PSP_PATH (
    SET PSP_PATH=D:\PX4PSP
    SET PSP_PATH_LINUX=/mnt/d/PX4PSP
)
SET PosXStr=-0.1
SET PosYStr=-0.8
SET YawStr=0
SET /a START_INDEX=1
SET /a CLASS_3D_ID=310
set DLLModel=0
SET /A DLLModelVal=DLLModel
if %DLLModelVal% EQU %DLLModel% goto SkipDLLCopy
if exist "%~dp0%DLLModel%" (
    copy /Y "%~dp0%DLLModel%" "%PSP_PATH%\CopterSim\external\XML\%DLLModel%"
)
:SkipDLLCopy
set SimMode=2
set PX4SitlFrame=iris
SET UE4_MAP=ChallengeMap
SET /a ORIGIN_POS_X=0
SET /a ORIGIN_POS_Y=0
SET /a ORIGIN_YAW=0
SET /a VEHICLE_INTERVAL=2
SET IS_BROADCAST=0
SET UDPSIMMODE=Mavlink_Vision
cd /d %PSP_PATH%\RflySim3D
tasklist|find /i "RflySim3D.exe" || start %PSP_PATH%\RflySim3D\RflySim3D.exe -cmd=RflyChangeMapbyName-%UE4_MAP%
choice /t 3 /d y /n >nul
tasklist|find /i "QGroundControl.exe" || start %PSP_PATH%\QGroundControl\QGroundControl.exe -noComPix
ECHO Start QGroundControl
tasklist|find /i "CopterSim.exe" && taskkill /im "CopterSim.exe"
ECHO Kill all CopterSims
cd /d %PSP_PATH%\CopterSim
set /a cntr=%START_INDEX%
SET string=%PosXStr%
SET stringY=%PosYStr%
SET stringYaw=%YawStr%
:MYSPLIT
    for /f "tokens=1,* delims=," %%i in ("%string%") do (
        set xPos=%%i
        set string=%%j
    )
    for /f "tokens=1,* delims=," %%i in ("%stringY%") do (
        set yPos=%%i
        set stringY=%%j
    )
    for /f "tokens=1,* delims=," %%i in ("%stringYaw%") do (
        set yawAng=%%i
        set stringYaw=%%j
    )
    start /realtime CopterSim.exe 1 %cntr% %CLASS_3D_ID% %DLLModel% %SimMode% %UE4_MAP% %IS_BROADCAST% %xPos% %yPos% %yawAng% 1 %UDPSIMMODE%
    ECHO start Copter #%cntr%
    choice /t 2 /d y /n >nul
    set /a cntr=%cntr%+1
if not "%string%"=="" goto MYSPLIT
set /a VehicleNum=%cntr%-%START_INDEX%
SET /a ToolChainType=1
if "%IS_BROADCAST%" == "0" (
    SET IS_BROADCAST=0
) else (
    SET IS_BROADCAST=1
)
choice /t 5 /d y /n >nul
start /B /separate %PSP_PATH%\Python38\python.exe "%~dp0\UAVSITL.py"
SET WINDOWSPATH=%PATH%
if %ToolChainType% EQU 1 (
    wsl -d RflySim-20.04 echo Starting PX4 Build; cd %PSP_PATH_LINUX%/Firmware; ./BkFile/EnvOri.sh; export PATH=$HOME/ninja:$HOME/gcc-arm-none-eabi-7-2017-q4-major/bin:$PATH;make px4_sitl_default; ./Tools/sitl_multiple_run_rfly.sh %VehicleNum% %START_INDEX% %PX4SitlFrame%;echo Press any key to exit; read -n 1
) else (
    echo no cygwin path in fixture
)
SET PATH=%WINDOWSPATH%
REM kill all applications when press a key
wsl --shutdown
tasklist|find /i "CopterSim.exe" && taskkill /im "CopterSim.exe"
tasklist|find /i "QGroundControl.exe" && taskkill /f /im "QGroundControl.exe"
tasklist|find /i "RflySim3D.exe" && taskkill /f /im "RflySim3D.exe"
tasklist|find /i "python.exe" && taskkill /f /im "python.exe"
ECHO Start End.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", required=True, type=Path)
    parser.add_argument("--output-file", type=Path, default=None)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = tmp / "UAVSITL.bat"
        source.write_text(FIXTURE, encoding="ascii")
        out = args.output_file or (tmp / "generated_uavsitl.bat")

        env = os.environ.copy()
        env["STAGE2_POS_X_STR"] = "-0.7,0.7"
        env["STAGE2_POS_Y_STR"] = "16,16"
        env["STAGE2_YAW_STR"] = "90,90"
        env["RFLYSIM_UE4_MAP"] = "SLAMScene"

        result = subprocess.run(
            [
                "powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(args.generator),
                "-SourceScript", str(source),
                "-Output", str(out),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return 1

        text = out.read_text(encoding="ascii", errors="replace")
        errors: list = []

        # 1. No global name guard inside the CopterSim loop.
        if re_search(text, r'tasklist\|find /i "CopterSim\.exe" >nul'):
            errors.append("generated wrapper still contains the global CopterSim.exe name guard")

        # 2. Instance-scoped role + marker + stack-scoped pid file.
        if '--role "gui:CopterSim/uav%cntr%"' not in text:
            errors.append('missing instance-scoped role gui:CopterSim/uav%cntr%')
        if '--instance-marker "uav%cntr%"' not in text:
            errors.append("missing --instance-marker uav%cntr%")
        if "%STACK_PID_DIR%pids\\copter_uav%cntr%.pid" not in text:
            errors.append("missing stack-scoped per-instance pid file path")
        # 2b. Batch-syntax regression: no empty-but-defined `if defined` gate and
        # no parentheses inside echo text within parenthesized blocks.
        if "if defined EXISTING_COPTER_PID (" in text:
            errors.append("generated wrapper uses the empty-but-defined if defined gate")
        if re_search(text, r"echo \[STACK\] copter uav%cntr% pid file stale \("):
            errors.append("generated wrapper has parentheses in echo text inside a block")
        if "goto copter_start" not in text:
            errors.append("generated wrapper missing goto copter_start structure")

        # 3. %~dp0 fully replaced by the real 28com_SITL directory.
        if "%~dp0" in text:
            errors.append("generated wrapper still contains %~dp0")
        if not re_search(text, r'set "UAV_SITL_DIR=[^"\r\n]+"'):
            errors.append("UAV_SITL_DIR injection is empty or unterminated")
        if '%UAV_SITL_DIR%\\UAVSITL.py' not in text:
            errors.append("UAVSITL.py does not resolve through UAV_SITL_DIR")

        # 3b. The WSL PX4 launch must stay on a single line (array-literal regression).
        lines = text.splitlines()
        wsl_line = None
        for index, line in enumerate(lines):
            if line.strip() == ":wsl_px4_launch":
                wsl_line = lines[index + 1] if index + 1 < len(lines) else ""
                break
        if wsl_line is None or "wsl -d %RFLYSIM_WSL_DISTRO%" not in wsl_line:
            errors.append("WSL PX4 launch line was split or missing")
        if wsl_line and not wsl_line.strip().startswith("wsl "):
            errors.append(f"WSL PX4 launch line has unexpected prefix: {wsl_line.strip()[:60]}")

        # 4. WSL manifest conversion must use the fail-fast helper.
        if "to_wsl_path.ps1" not in text:
            errors.append("trace header does not use to_wsl_path.ps1")
        if re_search(text, r'set /p STACK_MANIFEST_WSL=<'):
            errors.append("wrapper still uses set /p for the WSL manifest path")

        # 5. RflySim3D renderer child attach wired.
        if "attach-children" not in text or "Binaries\\Win64\\RflySim3D.exe" not in text:
            errors.append("RflySim3D renderer child attach not wired")

        # 6. Name-based kills from the reference must be removed.
        if "taskkill /im" in text.lower():
            errors.append("name-based taskkill survived in the generated wrapper")
        if "Kill all CopterSims" in text:
            errors.append("generated wrapper retained the misleading CopterSim kill message")
        if "Start stack-owned CopterSims" not in text:
            errors.append("generated wrapper missing the stack-owned CopterSim startup message")

        if errors:
            for error in errors:
                print(f"[FAIL] {error}", file=sys.stderr)
            print("--- generated wrapper (head) ---", file=sys.stderr)
            print("\n".join(text.splitlines()[:40]), file=sys.stderr)
            return 1
    print("[PASS] generated SITL wrapper contract PASS")
    return 0


def re_search(text: str, pattern: str) -> bool:
    import re

    return re.search(pattern, text, flags=re.IGNORECASE) is not None


if __name__ == "__main__":
    raise SystemExit(main())
