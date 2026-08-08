param(
    [string]$StackId,
    [string]$Manifest,
    [switch]$DryRun,
    [string]$Distro = 'RflySim-20.04'
)

# Single entry point to end a live stack cleanly:
#   1. clean the Stage 7 flight-chain leftovers (unregistered roslaunch children)
#   2. run the manifest-only lifecycle stop
#   3. (stop itself verifies clean; re-inspect afterwards)
# Usage: powershell -File scripts\end_live_stack.ps1 -StackId <stack_id> [-DryRun]
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'

if (-not $Manifest) {
    if (-not $StackId) {
        Write-Error 'provide -StackId or -Manifest'
        exit 2
    }
    $Manifest = Join-Path $projectRoot "logs\live_stack\$StackId\stack_manifest.json"
}
if (-not (Test-Path -LiteralPath $Manifest)) {
    Write-Error "manifest not found: $Manifest"
    exit 2
}

$cleanupWsl = '/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/scripts/wsl/cleanup_stage7_flight_chain.sh'

Write-Host "[end-live-stack] manifest=$Manifest"
if ($DryRun) {
    Write-Host '[end-live-stack] phase 1 (dry): list stage7 flight-chain processes to clean'
} else {
    Write-Host '[end-live-stack] phase 1: cleaning stage7 flight-chain leftovers'
}
wsl -d $Distro -e bash -lic "bash '$cleanupWsl' $(if ($DryRun) { '--dry-run' })"
if ($LASTEXITCODE -ne 0 -and -not $DryRun) {
    Write-Error '[end-live-stack] flight-chain cleanup failed; inspect before stopping'
    exit 1
}

Write-Host '[end-live-stack] phase 2: lifecycle stop'
if ($DryRun) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'live_stack_stop.ps1') -Manifest $Manifest -DryRun
} else {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'live_stack_stop.ps1') -Manifest $Manifest -Execute -Reason 'end_live_stack single-entry cleanup'
}
if ($LASTEXITCODE -ne 0) {
    Write-Error '[end-live-stack] lifecycle stop failed; inspect output'
    exit 1
}

Write-Host '[end-live-stack] phase 3: verify clean'
& $python (Join-Path $PSScriptRoot 'lifecycle\stack_inspect.py') --manifest $Manifest --distro $Distro
if ($LASTEXITCODE -ne 0) {
    Write-Error '[end-live-stack] verify-clean failed; do not start a new stack'
    exit 1
}
Write-Host '[end-live-stack] DONE (owned entities=0, no unknown, no stale)'
exit 0
