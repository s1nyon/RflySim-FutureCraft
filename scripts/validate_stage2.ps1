param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$requiredPaths = @(
    'config/stage2_two_uav.json',
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
        foreach ($uav in @('uav1', 'uav2')) {
            if (-not $config.uavs.$uav) { $contractErrors += "stage2 config missing $uav" }
            elseif ($config.uavs.$uav.namespace -notmatch '^/uav[12]$') { $contractErrors += "stage2 config namespace invalid for $uav" }
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
            foreach ($marker in @('SET PosXStr=-0.1,0.1', 'SET PosYStr=-0.8,-0.8', 'SET YawStr=0,0')) {
                if ($generated -notmatch [regex]::Escape($marker)) {
                    $contractErrors += "generated two-UAV SITL script missing marker: $marker"
                }
            }
        }
    }
}
$wslScript = Join-Path $ProjectRoot 'scripts/wsl/stage2_two_mavros.sh'
if (Test-Path -LiteralPath $wslScript) {
    $wslText = Get-Content -Raw -LiteralPath $wslScript
    foreach ($needle in @('ROS_NAMESPACE=uav1', 'ROS_NAMESPACE=uav2', 'fcu_url:=udp://:14541@127.0.0.1:14581', 'fcu_url:=udp://:14542@127.0.0.1:14582', 'tgt_system:=1', 'tgt_system:=2')) {
        if ($wslText -notmatch [regex]::Escape($needle)) {
            $contractErrors += "scripts/wsl/stage2_two_mavros.sh missing $needle"
        }
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

