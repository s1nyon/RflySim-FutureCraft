$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
$lifecycle = Join-Path $ProjectRoot 'scripts\lifecycle'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][object[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

Push-Location $ProjectRoot
try {
Invoke-Checked $python @(
    'tests\lifecycle_manifest_check.py',
    '--manifest-module', "$lifecycle\stack_manifest.py",
    '--process-table-module', "$lifecycle\process_table.py",
    '--ownership-module', "$lifecycle\stack_ownership.py"
)
Invoke-Checked $python @(
    'tests\lifecycle_ownership_check.py',
    '--ownership-module', "$lifecycle\stack_ownership.py",
    '--process-table-module', "$lifecycle\process_table.py",
    '--manifest-module', "$lifecycle\stack_manifest.py"
)
Invoke-Checked $python @(
    'tests\lifecycle_inspect_check.py',
    '--inspect-module', "$lifecycle\stack_inspect.py",
    '--process-table-module', "$lifecycle\process_table.py",
    '--manifest-module', "$lifecycle\stack_manifest.py"
)
Invoke-Checked $python @(
    'tests\lifecycle_stop_check.py',
    '--stop-module', "$lifecycle\stack_stop.py",
    '--process-table-module', "$lifecycle\process_table.py",
    '--manifest-module', "$lifecycle\stack_manifest.py",
    '--ownership-module', "$lifecycle\stack_ownership.py"
)
Invoke-Checked $python @('tests\lifecycle_health_gate_check.py', '--health-module', "$lifecycle\health_gate.py")
Invoke-Checked $python @('tests\lifecycle_fresh_instance_check.py', '--fresh-module', "$lifecycle\fresh_instance.py")
Invoke-Checked $python @('tests\lifecycle_banned_command_check.py', '--project-root', $ProjectRoot)

# Hazard stubs must refuse with exit code 1.
$stubOutput = & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\cleanup_sim_stack.ps1') 2>&1
if ($LASTEXITCODE -ne 1) {
    throw "cleanup_sim_stack.ps1 hazard stub must exit 1 (got $LASTEXITCODE): $($stubOutput -join ' ')"
}
$stubOutput = & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\restart_live_stack.ps1') 2>&1
if ($LASTEXITCODE -ne 1) {
    throw "restart_live_stack.ps1 hazard stub must exit 1 (got $LASTEXITCODE): $($stubOutput -join ' ')"
}

# Health gate CLI integration (offline, temp dir).
$tempBase = [System.IO.Path]::GetTempPath()
$tempHealth = Join-Path $tempBase ("future_aircraft_lifecycle_health_" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempHealth | Out-Null
try {
    foreach ($status in @('GUI_READY', 'ROSCORE_READY', 'MAVROS_UAV1_CONNECTED', 'MAVROS_UAV2_CONNECTED', 'COURSE_READY')) {
        Invoke-Checked $python @(
            "$lifecycle\health_probe.py", 'write',
            '--health-dir', $tempHealth,
            '--stack-id', 'stack-20260808T120000Z-a1b2c3d4',
            '--status', $status,
            '--ready', 'true',
            '--detail', 'offline'
        )
    }
    Invoke-Checked $python @("$lifecycle\health_probe.py", 'check', '--health-dir', $tempHealth, '--wait-seconds', '0')
    Invoke-Checked $python @(
        "$lifecycle\health_probe.py", 'write',
        '--health-dir', $tempHealth,
        '--stack-id', 'stack-20260808T120000Z-a1b2c3d4',
        '--status', 'MAVROS_UAV2_CONNECTED',
        '--ready', 'false',
        '--detail', 'offline-fail'
    )
    & $python "$lifecycle\health_probe.py" check --health-dir $tempHealth --wait-seconds 0 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        throw 'health gate must fail closed when any status is not ready'
    }
}
finally {
    $resolvedTemp = [System.IO.Path]::GetFullPath($tempBase)
    $resolvedHealth = [System.IO.Path]::GetFullPath($tempHealth)
    if (-not $resolvedHealth.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove non-temporary path: $resolvedHealth"
    }
    if (Test-Path -LiteralPath $resolvedHealth) {
        Remove-Item -Recurse -Force -LiteralPath $resolvedHealth
    }
}

# Manifest init + ownership record (offline, injected process tables).
$tempProj = Join-Path $tempBase ("future_aircraft_lifecycle_record_" + [Guid]::NewGuid().ToString('N'))
$projRoot = Join-Path $tempProj 'proj'
New-Item -ItemType Directory -Path $projRoot | Out-Null
try {
    $stackId = 'stack-20260808T120000Z-a1b2c3d4'
    Invoke-Checked $python @(
        "$lifecycle\stack_manifest.py", 'init',
        '--project-root', $projRoot,
        '--stack-id', $stackId,
        '--git-commit', ('0' * 40),
        '--launcher-kind', 'batch',
        '--launcher-identity', 'offline-test'
    )
    $manifestPath = Join-Path $projRoot "logs\live_stack\$stackId\stack_manifest.json"
    $winJson = Join-Path $tempProj 'win.json'
    $wslSnap = Join-Path $tempProj 'wsl.txt'
    @(
        @{ pid = 1; name = 'RflySim3D'; start_time_utc = '2026-08-08T12:00:03Z'; command_line = '"D:\p\RflySim3D.exe"'; parent_pid = 0 },
        @{ pid = 2; name = 'CopterSim'; start_time_utc = '2026-08-08T12:00:05Z'; command_line = '"D:\p\CopterSim.exe"'; parent_pid = 0 }
    ) | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $winJson -Encoding UTF8
    @(
        '500 500 1 Sat Aug  8 12:00:10 2026 /opt/ros/noetic/bin/roscore',
        '510 500 1 Sat Aug  8 12:00:12 2026 /usr/bin/python3 .../rflysim_mavros_px4.launch uav_namespace:=uav1',
        '520 500 1 Sat Aug  8 12:00:14 2026 /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS'
    ) | Set-Content -LiteralPath $wslSnap -Encoding ASCII
    Invoke-Checked $python @(
        "$lifecycle\stack_record.py",
        '--manifest', $manifestPath,
        '--windows-json', $winJson,
        '--wsl-snapshot-file', $wslSnap
    )
    $recorded = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    if ($recorded.windows_processes.Count -lt 1 -or $recorded.wsl_processes.Count -lt 1) {
        throw 'ownership record did not populate the manifest'
    }
    if ($recorded.windows_processes[0].start_time_utc -eq $null) {
        throw 'ownership record must include process start time'
    }
}
finally {
    $resolvedProj = [System.IO.Path]::GetFullPath($tempProj)
    if (-not $resolvedProj.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove non-temporary path: $resolvedProj"
    }
    if (Test-Path -LiteralPath $resolvedProj) {
        Remove-Item -Recurse -Force -LiteralPath $resolvedProj
    }
}

# Modified launch chain must keep --dry-run working.
Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\start_predicted_course_two_uav.bat', '--dry-run')
Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\start_wsl_mavros_two.bat', '--dry-run')
Invoke-Checked 'git.exe' @('diff', '--check')

Write-Output '[PASS] Lifecycle offline validation PASS'
}
finally {
    Pop-Location
}
