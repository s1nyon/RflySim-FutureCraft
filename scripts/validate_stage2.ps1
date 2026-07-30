param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$requiredPaths = @(
    'config/stage2_two_uav.json',
    '.gitattributes',
    'scripts/start_vcxsrv.bat',
    'scripts/start_two_uav.bat',
    'scripts/start_rflysim_sitl_two.bat',
    'scripts/start_wsl_mavros_two.bat',
    'scripts/start_mavros_uav1.bat',
    'scripts/start_mavros_uav2.bat',
    'scripts/wsl/stage2_two_mavros.sh'
)

$missing = @()
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relativePath))) {
        $missing += $relativePath
    }
}

$contractErrors = @()
$attributesPath = Join-Path $ProjectRoot '.gitattributes'
if (Test-Path -LiteralPath $attributesPath) {
    $attributesText = Get-Content -Raw -LiteralPath $attributesPath
    if ($attributesText -notmatch 'scripts/wsl/\*\.sh\s+text\s+eol=lf') {
        $contractErrors += '.gitattributes must force scripts/wsl/*.sh to LF line endings'
    }
}
$envPath = Join-Path $ProjectRoot 'config/env_template.bat'
if (Test-Path -LiteralPath $envPath) {
    $envText = Get-Content -Raw -LiteralPath $envPath
    foreach ($name in @('STAGE2_POS_X_STR', 'STAGE2_POS_Y_STR', 'STAGE2_YAW_STR', 'STAGE2_BOOT_WAIT_SECONDS')) {
        if ($envText -notmatch [regex]::Escape($name)) {
            $contractErrors += "config/env_template.bat missing $name"
        }
    }
}

$configPath = Join-Path $ProjectRoot 'config/stage2_two_uav.json'
if (Test-Path -LiteralPath $configPath) {
    try {
        $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
        if ($config.stage -ne 2) { $contractErrors += 'config/stage2_two_uav.json stage must be 2' }
        $expectedFcuUrls = @{
            uav1 = 'udp://:14601@127.0.0.1:14600'
            uav2 = 'udp://:14611@127.0.0.1:14610'
        }
        foreach ($uav in @('uav1', 'uav2')) {
            if (-not $config.uavs.$uav) { $contractErrors += "stage2 config missing $uav" }
            elseif ($config.uavs.$uav.namespace -notmatch '^/uav[12]$') { $contractErrors += "stage2 config namespace invalid for $uav" }
            elseif ($config.uavs.$uav.mavros_fcu_url -ne $expectedFcuUrls[$uav]) { $contractErrors += "stage2 config fcu_url invalid for ${uav}: $($config.uavs.$uav.mavros_fcu_url)" }
        }
        $expectedTopics = @('/uav1/mavros/state', '/uav2/mavros/state', '/uav1/mavros/odometry/in', '/uav2/mavros/odometry/in')
        if (($config.validation.expected_topics | ConvertTo-Json -Compress) -ne ($expectedTopics | ConvertTo-Json -Compress)) {
            $contractErrors += 'stage2 config expected_topics must use MAVROS odometry/in for both UAVs'
        }
    }
    catch {
        $contractErrors += "config/stage2_two_uav.json is not valid JSON: $($_.Exception.Message)"
    }
}

$originalSitl = Join-Path $ProjectRoot '..\28com_sim\28com_SITL\UAVSITL.bat'
$originalSitl = [System.IO.Path]::GetFullPath($originalSitl)
if (Test-Path -LiteralPath $originalSitl) {
    $sitlText = Get-Content -Raw -LiteralPath $originalSitl
    foreach ($marker in @('SET PosXStr=-0.1', 'SET PosYStr=-0.8', 'SET YawStr=0')) {
        if ($sitlText -notmatch [regex]::Escape($marker)) {
            $contractErrors += "original UAVSITL.bat missing expected marker: $marker"
        }
    }
}
else {
    $contractErrors += "missing original SITL script: $originalSitl"
}

$dryRunScripts = @(
    'scripts/start_rflysim_sitl_two.bat',
    'scripts/start_wsl_mavros_two.bat',
    'scripts/start_mavros_uav1.bat',
    'scripts/start_mavros_uav2.bat',
    'scripts/start_two_uav.bat'
)
foreach ($relativePath in $dryRunScripts) {
    $fullPath = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $fullPath) {
        $content = Get-Content -Raw -LiteralPath $fullPath
        if ($content -notmatch '--dry-run') { $contractErrors += "$relativePath missing --dry-run support" }
        if ($content -match 'cmd /k "call ""') {
            $contractErrors += "$relativePath uses invalid cmd nested call quoting"
        }
        if ($relativePath -eq 'scripts/start_two_uav.bat' -and $content -notmatch 'start_vcxsrv\.bat') {
            $contractErrors += 'scripts/start_two_uav.bat must start VcXsrv before launching the RflySim toolchain'
        }
        if ($relativePath -eq 'scripts/start_two_uav.bat' -and $content -match 'timeout /t') {
            $contractErrors += 'scripts/start_two_uav.bat must not use timeout /t for noninteractive startup waits'
        }
        $output = & cmd /c "`"$fullPath`" --dry-run" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "$relativePath --dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
    }
}


$generateScript = Join-Path $ProjectRoot 'scripts/start_rflysim_sitl_two.bat'
if (Test-Path -LiteralPath $generateScript) {
    $output = & cmd /c "`"$generateScript`" --generate-only" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $contractErrors += "scripts/start_rflysim_sitl_two.bat --generate-only failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
    }
    else {
        $tempScript = Join-Path $env:TEMP 'future_aircraft_stage2_uavsitl.bat'
        if (-not (Test-Path -LiteralPath $tempScript)) {
            $contractErrors += "generated two-UAV SITL script missing: $tempScript"
        }
        else {
            $generated = Get-Content -Raw -LiteralPath $tempScript
            foreach ($marker in @('SET PosXStr=0.5,1.5', 'SET PosYStr=1.5,1.5', 'SET YawStr=0,0')) {
                if ($generated -notmatch [regex]::Escape($marker)) {
                    $contractErrors += "generated two-UAV SITL script missing marker: $marker"
                }
            }
            foreach ($forbidden in @('wsl --shutdown', 'taskkill /f /im "cmd.exe"', 'taskkill /f /im "wsl.exe"', 'taskkill /f /im "bash.exe"', 'taskkill /f /IM "vcxsrv.exe"')) {
                if ($generated -match [regex]::Escape($forbidden)) {
                    $contractErrors += "generated two-UAV SITL script keeps original cleanup command: $forbidden"
                }
            }
            if ($generated -notmatch [regex]::Escape('tail -f /dev/null')) {
                $contractErrors += 'generated two-UAV SITL script missing noninteractive WSL keepalive'
            }
            if ($generated -notmatch 'wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic') {
                $contractErrors += 'generated two-UAV SITL script must launch PX4 through wsl -e bash -lic'
            }
        }
    }
}
$wslScript = Join-Path $ProjectRoot 'scripts/wsl/stage2_two_mavros.sh'
if (Test-Path -LiteralPath $wslScript) {
    $wslBytes = [System.IO.File]::ReadAllBytes($wslScript)
    for ($i = 0; $i -lt ($wslBytes.Length - 1); $i++) {
        if ($wslBytes[$i] -eq 13 -and $wslBytes[$i + 1] -eq 10) {
            $contractErrors += 'scripts/wsl/stage2_two_mavros.sh must use LF line endings for WSL execution'
            break
        }
    }
    $wslText = Get-Content -Raw -LiteralPath $wslScript
    foreach ($needle in @('ROS_NAMESPACE=uav1', 'ROS_NAMESPACE=uav2', 'px4-mavlink --instance 1 start -u 14600 -o 14601', 'px4-mavlink --instance 2 start -u 14610 -o 14611', '"$PX4_MAVLINK_BIN" --instance "$sysid" stream -u "$px4_port" -s LOCAL_POSITION_NED -r 30', '"$PX4_MAVLINK_BIN" --instance "$sysid" stream -u "$px4_port" -s ODOMETRY -r 30', 'fcu_url:=udp://:14601@127.0.0.1:14600', 'fcu_url:=udp://:14611@127.0.0.1:14610', 'tgt_system:=1', 'tgt_system:=2')) {
        if ($wslText -notmatch [regex]::Escape($needle)) {
            $contractErrors += "scripts/wsl/stage2_two_mavros.sh missing $needle"
        }
    }
    if ($wslText -notmatch '(?m)^\s*wait\s*$') {
        $contractErrors += 'scripts/wsl/stage2_two_mavros.sh must keep the WSL ROS/MAVROS session alive after startup'
    }
}

if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 2 two-UAV namespace validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 2 two-UAV namespace validation passed.' -ForegroundColor Green
}
exit 0



