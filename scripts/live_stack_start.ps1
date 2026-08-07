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
$healthDirWsl = ConvertTo-WslPath -Path $manifestDir
$gitCommit = ((& git -C $projectRoot rev-parse HEAD 2>$null) -join '')

Write-Host "[live-stack-start] stack_id=$stackId"
Write-Host "[live-stack-start] scheduled_task=$taskName"
Write-Host "[live-stack-start] manifest=$manifestPath"
Write-Host "[live-stack-start] health_dir=$healthDirWsl"

if ($DryRun) {
    Write-Host '[DRY-RUN] 1. init run-scoped manifest (stack_id, git commit, start time, launcher identity, ROS master)'
    Write-Host "[DRY-RUN] 2. create one-shot scheduled task $taskName (far-future /st, then /run) launching $startup --stack-id --health-dir"
    Write-Host '[DRY-RUN] 3. wait for GUI processes (RflySim3D/CopterSim), record owned Windows processes into manifest'
    Write-Host '[DRY-RUN] 4. snapshot WSL ownership (roscore/mavros/px4/sensor/fastlio/ego), simulation_instance_id, ROS master'
    Write-Host '[DRY-RUN] 5. wait for health gate all-ready (GUI/ROSCORE/MAVROS_UAV1/MAVROS_UAV2/COURSE)'
    Write-Host '[DRY-RUN] The manifest-recorded scheduled task is removed only by graceful stop (manifest-only).'
    exit 0
}

& $python (Join-Path $lifecycle 'stack_manifest.py') init `
    --project-root $projectRoot --stack-id $stackId --git-commit $gitCommit `
    --launcher-kind scheduled_task --launcher-identity $taskName
if ($LASTEXITCODE -ne 0) { throw 'stack manifest init failed' }

$taskCmd = "cmd /c call `"$startup`" --stack-id $stackId --health-dir $manifestDir"
schtasks /create /tn $taskName /tr $taskCmd /sc once /st 00:00 /sd 01/01/2030 /ru $TaskUser /rl HIGHEST /f | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /create failed: $taskName" }
schtasks /run /tn $taskName | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /run failed: $taskName" }
Write-Host "[live-stack-start] scheduled task launched: $taskName"

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

& $python (Join-Path $lifecycle 'stack_record.py') --manifest $manifestPath --distro $Distro
if ($LASTEXITCODE -ne 0) {
    Write-Host '[WARN] ownership recording incomplete; inspect before proceeding.' -ForegroundColor Yellow
}

& $python (Join-Path $lifecycle 'health_probe.py') check --health-dir $manifestDir --wait-seconds 300
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] health gate not ready; fail closed - do not proceed to FAST-LIO/arming.' -ForegroundColor Red
    exit 1
}

Write-Host "[OK] live stack started: $manifestPath"
exit 0
