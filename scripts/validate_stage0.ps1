param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$requiredPaths = @(
    'config/env_template.bat',
    'config/uavs.json',
    'future_aircraft_ws/src',
    'logs',
    'scripts/start_single_uav.bat',
    'scripts/start_two_uav.bat',
    'scripts/start_mavros_uav1.bat',
    'scripts/start_mavros_uav2.bat',
    'scripts/start_mission.bat',
    'scripts/record_logs.bat',
    'scripts/kill_all.bat'
)

$missing = @()
foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $ProjectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        $missing += $relativePath
    }
}

$scriptFiles = @(
    'scripts/start_single_uav.bat',
    'scripts/start_two_uav.bat',
    'scripts/start_mavros_uav1.bat',
    'scripts/start_mavros_uav2.bat',
    'scripts/start_mission.bat',
    'scripts/record_logs.bat',
    'scripts/kill_all.bat'
)

$contractErrors = @()
foreach ($relativePath in $scriptFiles) {
    $fullPath = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $fullPath) {
        $content = Get-Content -Raw -LiteralPath $fullPath
        if ($content -notmatch 'env_template\.bat') {
            $contractErrors += "$relativePath does not load config/env_template.bat"
        }
        if ($content -notmatch '--dry-run') {
            $contractErrors += "$relativePath does not document or handle --dry-run"
        }
        if ($content -notmatch 'exit /b 1') {
            $contractErrors += "$relativePath does not fail with exit /b 1"
        }
    }
}

$configPath = Join-Path $ProjectRoot 'config/uavs.json'
if (Test-Path -LiteralPath $configPath) {
    try {
        $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
        foreach ($uav in @('uav1', 'uav2')) {
            if (-not $config.uavs.$uav) {
                $contractErrors += "config/uavs.json missing $uav"
            }
            elseif (-not $config.uavs.$uav.namespace) {
                $contractErrors += "config/uavs.json missing namespace for $uav"
            }
        }
    }
    catch {
        $contractErrors += "config/uavs.json is not valid JSON: $($_.Exception.Message)"
    }
}


foreach ($relativePath in $scriptFiles) {
    $fullPath = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $fullPath) {
        $output = & cmd /c "`"$fullPath`" --dry-run" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $contractErrors += "$relativePath --dry-run failed with exit code ${LASTEXITCODE}: $($output -join ' ')"
        }
    }
}
if ($missing.Count -gt 0 -or $contractErrors.Count -gt 0) {
    if (-not $Quiet) {
        Write-Host '[FAIL] Stage 0 scaffold validation failed.' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  missing: $item" -ForegroundColor Red }
        foreach ($item in $contractErrors) { Write-Host "  contract: $item" -ForegroundColor Red }
    }
    exit 1
}

if (-not $Quiet) {
    Write-Host '[PASS] Stage 0 scaffold validation passed.' -ForegroundColor Green
}
exit 0


