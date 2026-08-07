param(
    [switch]$DryRun,
    [switch]$Execute,
    [switch]$Approved,
    [string]$Reason = 'fresh-instance cycle',
    [string]$Distro = 'RflySim-20.04'
)

# P0 Safe Live Stack Lifecycle: fresh-instance =
#   inspect -> graceful stop -> verify clean -> start NEW stack ->
#   health gate -> readiness -> flight.
# auto_force_retry is ALWAYS NO: any stop/clean-verification failure aborts.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
if (-not $Execute) { $DryRun = $true }

function Get-LatestManifest {
    $root = Join-Path $projectRoot 'logs\live_stack'
    if (-not (Test-Path -LiteralPath $root)) { return $null }
    Get-ChildItem -Directory -LiteralPath $root -ErrorAction SilentlyContinue |
        ForEach-Object {
            $m = Join-Path $_.FullName 'stack_manifest.json'
            if (Test-Path -LiteralPath $m) { Get-Item -LiteralPath $m }
        } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

Write-Host '[fresh-instance] phase sequence: inspect -> graceful stop -> verify clean -> start NEW stack -> health gate -> readiness -> flight'
Write-Host '[fresh-instance] auto_force_retry=NO : any stop/clean-verification failure aborts and reports'

if ($DryRun) {
    $latest = Get-LatestManifest
    if ($latest) {
        Write-Host "[fresh-instance] current manifest: $($latest.FullName)"
        Write-Host '[fresh-instance] running read-only inspect (exit code 0 = no unknown/stale; 2 = fail closed):'
        & $python (Join-Path $PSScriptRoot 'lifecycle\stack_inspect.py') --manifest $latest.FullName --distro $Distro
        Write-Host "[fresh-instance] inspect exit code: $LASTEXITCODE"
    }
    else {
        Write-Host '[fresh-instance] no existing manifest found; start a new stack via live_stack_start.ps1 -Execute'
    }
    Write-Host '[fresh-instance] DRY-RUN only: no processes touched, no scheduled task modified.'
    exit 0
}

if (-not $Approved) {
    Write-Host '[ERROR] live execution requires -Approved after reviewing DryRun output.' -ForegroundColor Red
    exit 2
}

$latest = Get-LatestManifest
if (-not $latest) {
    Write-Host '[ERROR] no existing manifest to stop; nothing to do.' -ForegroundColor Red
    exit 1
}

& $python (Join-Path $PSScriptRoot 'lifecycle\stack_inspect.py') --manifest $latest.FullName --distro $Distro
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] inspect fail-closed; aborting fresh-instance (no auto force retry).' -ForegroundColor Red
    exit 1
}

& $python (Join-Path $PSScriptRoot 'lifecycle\stack_stop.py') --manifest $latest.FullName --distro $Distro --reason $Reason --execute
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] graceful stop failed; aborting (no auto force retry).' -ForegroundColor Red
    exit 1
}

& $python (Join-Path $PSScriptRoot 'lifecycle\stack_inspect.py') --manifest $latest.FullName --distro $Distro
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] clean verification failed; aborting (no auto force retry).' -ForegroundColor Red
    exit 1
}

& (Join-Path $PSScriptRoot 'live_stack_start.ps1') -Execute
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] new stack start failed; aborting.' -ForegroundColor Red
    exit 1
}

Write-Host '[fresh-instance] launching Stage 7 no-arm readiness runner...'
& (Join-Path $PSScriptRoot 'run_live_fastlio_dual.bat')
Write-Host '[fresh-instance] readiness runner launched; wait for sensor_readiness.json PASS before flight.'
Write-Host '[fresh-instance] flight step (user-supervised): scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only'
Write-Host '[fresh-instance] record startup_success / flight_success / shutdown_clean per run.'
exit 0
