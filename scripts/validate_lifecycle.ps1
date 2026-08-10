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
        '--manifest-module', "$lifecycle\stack_manifest.py"
    )
    Invoke-Checked $python @(
        'tests\lifecycle_inspect_check.py',
        '--inspect-module', "$lifecycle\stack_inspect.py",
        '--process-table-module', "$lifecycle\process_table.py",
        '--manifest-module', "$lifecycle\stack_manifest.py",
        '--ownership-module', "$lifecycle\stack_ownership.py"
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
    Invoke-Checked $python @(
        'tests\lifecycle_spawn_attest_check.py',
        '--attest-module', "$lifecycle\spawn_attest.py",
        '--manifest-module', "$lifecycle\stack_manifest.py",
        '--ownership-module', "$lifecycle\stack_ownership.py",
        '--process-table-module', "$lifecycle\process_table.py",
        '--stop-module', "$lifecycle\stack_stop.py"
    )
    Invoke-Checked $python @('tests\lifecycle_banned_command_check.py', '--project-root', $ProjectRoot)
    Invoke-Checked $python @(
        'tests\lifecycle_topology_check.py',
        '--topology-module', "$lifecycle\stack_topology.py",
        '--process-table-module', "$lifecycle\process_table.py",
        '--manifest-module', "$lifecycle\stack_manifest.py",
        '--ownership-module', "$lifecycle\stack_ownership.py"
    )
    Invoke-Checked $python @(
        'tests\lifecycle_wrapper_generation_check.py',
        '--generator', "$lifecycle\generate_sitl_wrapper.ps1"
    )

    $startText = Get-Content -LiteralPath (Join-Path $ProjectRoot 'scripts\live_stack_start.ps1') -Raw
    $healthGateIndex = $startText.IndexOf("health_probe.py') check")
    $simIdIndex = $startText.IndexOf("live_stack_wsl_ops.sh' sim-id")
    if ($healthGateIndex -lt 0 -or $simIdIndex -lt 0 -or $simIdIndex -lt $healthGateIndex) {
        throw 'live_stack_start.ps1 must compute simulation_instance_id only after the PX4/MAVROS health gate'
    }

    # Hazard stubs must refuse with exit code 1.
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\cleanup_sim_stack.ps1') 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 1) { throw "cleanup_sim_stack.ps1 hazard stub must exit 1 (got $LASTEXITCODE)" }
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\restart_live_stack.ps1') 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 1) { throw "restart_live_stack.ps1 hazard stub must exit 1 (got $LASTEXITCODE)" }

    # Health CLI integration: per-status files, all-ready, fail closed, concurrent producers.
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
            if (-not (Test-Path -LiteralPath (Join-Path $tempHealth "$status.json"))) {
                throw "health status file missing: $status.json"
            }
        }
        if (Test-Path -LiteralPath (Join-Path $tempHealth 'health.json')) {
            throw 'shared health.json must not exist (per-status files only)'
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

        # Concurrent producers writing different status files must not lose status.
        $tempConcurrent = Join-Path $tempBase ("future_aircraft_lifecycle_conc_" + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tempConcurrent | Out-Null
        try {
            $jobs = @()
            foreach ($status in @('GUI_READY', 'ROSCORE_READY', 'MAVROS_UAV1_CONNECTED', 'MAVROS_UAV2_CONNECTED', 'COURSE_READY')) {
                $jobs += Start-Job -ScriptBlock {
                    param($Py, $Script, $Dir, $Status)
                    & $Py $Script write --health-dir $Dir --stack-id 'stack-20260808T120000Z-a1b2c3d4' --status $Status --ready true --detail 'concurrent' | Out-Null
                    exit $LASTEXITCODE
                } -ArgumentList $python, "$lifecycle\health_probe.py", $tempConcurrent, $status
            }
            $jobs | Wait-Job | Out-Null
            $failed = @($jobs | Where-Object { (Receive-Job -Job $_ -ErrorAction SilentlyContinue) -ne $null })
            $jobs | Remove-Job -Force
            if ($failed.Count -gt 0) { throw 'concurrent health writes failed' }
            Invoke-Checked $python @("$lifecycle\health_probe.py", 'check', '--health-dir', $tempConcurrent, '--wait-seconds', '0')
        }
        finally {
            $resolvedConc = [System.IO.Path]::GetFullPath($tempConcurrent)
            if ($resolvedConc.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedConc)) {
                Remove-Item -Recurse -Force -LiteralPath $resolvedConc
            }
        }
    }
    finally {
        $resolvedHealth = [System.IO.Path]::GetFullPath($tempHealth)
        if (-not $resolvedHealth.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove non-temporary path: $resolvedHealth"
        }
        if (Test-Path -LiteralPath $resolvedHealth) {
            Remove-Item -Recurse -Force -LiteralPath $resolvedHealth
        }
    }

    # Registration integration: stack_register.py grants ownership at creation; duplicate is rejected.
    $tempProj = Join-Path $tempBase ("future_aircraft_lifecycle_reg_" + [Guid]::NewGuid().ToString('N'))
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
        Invoke-Checked $python @(
            "$lifecycle\stack_register.py", 'register',
            '--manifest', $manifestPath,
            '--side', 'windows',
            '--pid', '111',
            '--role', 'gui:RflySim3D',
            '--name', 'RflySim3D',
            '--cmdline', '"D:\p\RflySim3D.exe"',
            '--start-time', '2026-08-08T12:00:03Z',
            '--reason', 'launcher captured PID via Start-Process -PassThru'
        )
        Invoke-Checked $python @(
            "$lifecycle\stack_register.py", 'register',
            '--manifest', $manifestPath,
            '--side', 'wsl',
            '--pid', '500',
            '--pgid', '500',
            '--role', 'wsl:roscore',
            '--name', 'roscore',
            '--cmdline', '/opt/ros/noetic/bin/roscore',
            '--start-time', '2026-08-08T12:00:10Z',
            '--reason', 'created by stage2_two_mavros.sh (setsid)'
        )
        $registered = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
        if ($registered.windows_processes.Count -ne 1 -or $registered.wsl_processes.Count -ne 1) {
            throw 'registration did not populate the manifest exactly'
        }
        if ($registered.windows_processes[0].ownership.granted -ne 'at_creation' -or
            $registered.wsl_processes[0].ownership.granted -ne 'at_creation') {
            throw 'registered entries must carry at_creation ownership'
        }
        if ($registered.wsl_processes[0].pgid -ne 500) {
            throw 'wsl registration must store PGID'
        }
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $python "$lifecycle\stack_register.py" register `
            --manifest $manifestPath --side windows --pid 111 --role gui:X --name X `
            --cmdline 'x' --start-time '2026-08-08T12:00:03Z' --reason 'dup' 2>$null | Out-Null
        $dupExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEap
        if ($dupExit -eq 0) {
            throw 'duplicate pid+side registration must be rejected'
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
    Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\start_two_uav.bat', '--dry-run')
    Invoke-Checked 'cmd.exe' @('/d', '/c', 'scripts\start_rflysim_sitl_two.bat', '--dry-run')
    Invoke-Checked 'git.exe' @('diff', '--check')

    Write-Output '[PASS] Lifecycle offline validation PASS'
}
finally {
    Pop-Location
}
