param(
    [switch]$DryRun,
    [switch]$Execute,
    [string]$TaskUser = 'PC-202307281902\Administrator',
    [string]$Distro = 'RflySim-20.04'
)

# P0 Safe Live Stack Lifecycle: start a NEW stack with a unique stack_id and a
# run-scoped ownership manifest. Real start requires -Execute; default is DryRun.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
$lifecycle = Join-Path $PSScriptRoot 'lifecycle'
$startup = Join-Path $PSScriptRoot 'start_predicted_course_two_uav.bat'

if (-not $Execute) { $DryRun = $true }

function ConvertTo-WslPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($Path -match '^[A-Za-z]:\\') {
        $drive = $Path.Substring(0, 1).ToLowerInvariant()
        $rest = $Path.Substring(2).Replace('\', '/')
        return "/mnt/$drive$rest"
    }
    return $Path.Replace('\', '/')
}

$stackId = 'stack-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + (
    [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
)
$taskName = "\FutureAircraftSim_LiveStack_$stackId"
$manifestDir = Join-Path $projectRoot "logs\live_stack\$stackId"
$manifestPath = Join-Path $manifestDir 'stack_manifest.json'
$healthDir = Join-Path $manifestDir 'health'
$healthDirWsl = ConvertTo-WslPath -Path $healthDir
$contextFile = Join-Path $manifestDir 'stack_context.env'
$gitCommit = ((& git -C $projectRoot rev-parse HEAD 2>$null) -join '')

Write-Host "[live-stack-start] stack_id=$stackId"
Write-Host "[live-stack-start] scheduled_task=$taskName"
Write-Host "[live-stack-start] manifest=$manifestPath"
Write-Host "[live-stack-start] health_dir=$healthDirWsl"

if ($DryRun) {
    Write-Host '[DRY-RUN] 1. init run-scoped manifest v2 (stack_id, git commit, start time, launcher identity, ROS master)'
    Write-Host "[DRY-RUN] 2. create one-shot scheduled task $taskName (far-future /st, then /run) launching $startup --stack-id --health-dir --manifest"
    Write-Host '[DRY-RUN] 3. write stack_context.env (STACK_ID/STACK_MANIFEST/STACK_HEALTH_DIR) for later runners'
    Write-Host '[DRY-RUN] 4. launchers register owned processes AT CREATION (cmd windows via register_launcher.py; GUI via generated SITL wrapper; roscore/MAVROS via stage2 setsid)'
    Write-Host '[DRY-RUN] 5. set simulation_instance_id + ROS master in manifest; wait for per-status health gate all-ready'
    Write-Host '[DRY-RUN] The manifest-recorded scheduled task is removed only by graceful stop (manifest-only).'
    exit 0
}

& $python (Join-Path $lifecycle 'stack_manifest.py') init `
    --project-root $projectRoot --stack-id $stackId --git-commit $gitCommit `
    --launcher-kind scheduled_task --launcher-identity $taskName
if ($LASTEXITCODE -ne 0) { throw 'stack manifest init failed' }

$taskCmd = "cmd /c call `"$startup`" --stack-id $stackId"
schtasks /create /tn $taskName /tr $taskCmd /sc once /st 00:00 /sd 2030/01/01 /ru $TaskUser /rl HIGHEST /it /f | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /create failed: $taskName" }
schtasks /run /tn $taskName | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /run failed: $taskName" }
Write-Host "[live-stack-start] scheduled task launched: $taskName"

@(
    "STACK_ID=$stackId",
    "STACK_MANIFEST=$manifestPath",
    "STACK_MANIFEST_WSL=$(ConvertTo-WslPath -Path $manifestPath)",
    "STACK_HEALTH_DIR=$healthDir",
    "STACK_HEALTH_DIR_WSL=$healthDirWsl"
) | Set-Content -LiteralPath $contextFile -Encoding ASCII
Write-Host "[live-stack-start] stack context: $contextFile"

$guiDeadline = (Get-Date).AddSeconds(240)
$guiOk = $false
while ((Get-Date) -lt $guiDeadline) {
    $gui = @(Get-Process -Name 'RflySim3D', 'CopterSim' -ErrorAction SilentlyContinue)
    if (@($gui | Where-Object { $_.Name -eq 'RflySim3D' }).Count -gt 0 -and
        @($gui | Where-Object { $_.Name -eq 'CopterSim' }).Count -gt 0) {
        $guiOk = $true
        break
    }
    Start-Sleep -Seconds 5
}
if (-not $guiOk) {
    Write-Host '[ERROR] GUI stack did not come up within 240s; manifest written; inspect before stopping.' -ForegroundColor Red
}

$rosMasterUri = if ($env:ROS_MASTER_URI) { $env:ROS_MASTER_URI } else { 'http://127.0.0.1:11311' }
& $python (Join-Path $lifecycle 'stack_register.py') set-ros-master --manifest $manifestPath --uri $rosMasterUri

& $python (Join-Path $lifecycle 'health_probe.py') check --health-dir $healthDir --manifest $manifestPath --wait-seconds 300
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] health gate not ready (statuses and/or dual-UAV topology); fail closed - do not proceed to FAST-LIO/arming.' -ForegroundColor Red
    exit 1
}

$simId = $null
try {
    $simId = wsl -d $Distro -e bash -lic "bash '$(ConvertTo-WslPath -Path $projectRoot)/scripts/wsl/live_stack_wsl_ops.sh' sim-id" 2>$null | Select-Object -Last 1
} catch {
    $simId = $null
}
if (-not $simId) {
    Write-Host '[ERROR] simulation_instance_id could not be computed after the PX4/MAVROS health gate.' -ForegroundColor Red
    exit 1
}
& $python (Join-Path $lifecycle 'stack_register.py') set-sim-id --manifest $manifestPath --simulation-instance-id $simId
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] simulation_instance_id was not recorded; fail closed.' -ForegroundColor Red
    exit 1
}

Write-Host "[OK] live stack started (health + dual-UAV topology ready): $manifestPath"
exit 0
