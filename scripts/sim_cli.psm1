$script:WslDistro = 'RflySim-20.04'
$script:PythonExe = 'D:\PX4PSP\Python38\python.exe'

function Write-SimCheck {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('PASS','WARN','FAIL')][string]$Status,
        [Parameter(Mandatory = $true)][string]$Message
    )

    Write-Host "[$Status] $Message"
}

function ConvertTo-BashSingleQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)

    $singleQuote = [string][char]39
    $replacement = $singleQuote + '"' + $singleQuote + '"' + $singleQuote
    return $singleQuote + $Value.Replace($singleQuote, $replacement) + $singleQuote
}

function Resolve-WslProjectPath {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    # Windows PowerShell 5.1 promotes native stderr to NativeCommandError when
    # the caller uses Stop. Keep native failures observable through exit codes.
    $ErrorActionPreference = 'Continue'

    try {
        $resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
    }
    catch {
        return [pscustomobject]@{
            ExitCode = 2
            Path = $null
            Error = "cannot resolve project root: $ProjectRoot"
        }
    }

    $output = @(& wsl -d $script:WslDistro -e wslpath -a -u $resolvedRoot 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        return [pscustomobject]@{
            ExitCode = [int]$exitCode
            Path = $null
            Error = "wslpath failed for project root: $resolvedRoot ($($output -join ' '))"
        }
    }

    $wslPath = @($output | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) | Select-Object -Last 1
    if (-not $wslPath -or -not $wslPath.StartsWith('/')) {
        return [pscustomobject]@{
            ExitCode = 2
            Path = $null
            Error = "wslpath returned an invalid path for project root: $resolvedRoot"
        }
    }

    return [pscustomobject]@{
        ExitCode = 0
        Path = $wslPath
        Error = $null
    }
}

function Invoke-WorkspaceBuild {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [string[]]$AdditionalArguments = @()
    )

    $ErrorActionPreference = 'Continue'

    $pathResult = Resolve-WslProjectPath -ProjectRoot $ProjectRoot
    if ($pathResult.ExitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message $pathResult.Error
        return [int]$pathResult.ExitCode
    }

    $quotedRoot = ConvertTo-BashSingleQuoted -Value $pathResult.Path
    $argumentText = if ($AdditionalArguments.Count -gt 0) {
        ' ' + (($AdditionalArguments | ForEach-Object { ConvertTo-BashSingleQuoted -Value $_ }) -join ' ')
    }
    else {
        ''
    }
    $commandLine = "cd $quotedRoot && bash scripts/wsl/build_future_aircraft_ws.sh$argumentText"
    Write-Host "[build] WSL $($script:WslDistro): $commandLine"
    & wsl -d $script:WslDistro -e bash -lic $commandLine 2>&1 |
        ForEach-Object { Write-Host $_ }
    return [int]$LASTEXITCODE
}

function Invoke-ValidatorScript {
    param([Parameter(Mandatory = $true)][string]$ScriptPath)

    $ErrorActionPreference = 'Continue'

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        Write-SimCheck -Status FAIL -Message "validator not found: $ScriptPath"
        return 2
    }

    Write-Host "[validate] $ScriptPath"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath 2>&1 |
        ForEach-Object { Write-Host $_ }
    $exitCode = [int]$LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message "$ScriptPath (exit $exitCode)"
    }
    return $exitCode
}

function Invoke-SimDoctor {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $ErrorActionPreference = 'Continue'

    Write-Host '[doctor] repository diagnostics'
    $failed = $false
    try {
        $resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
    }
    catch {
        Write-SimCheck -Status FAIL -Message "project root is not readable: $ProjectRoot"
        return 2
    }

    if (Test-Path -LiteralPath $script:PythonExe -PathType Leaf) {
        $null = & $script:PythonExe -c 'import sys; sys.exit(0)' 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-SimCheck -Status PASS -Message "Python runs: $script:PythonExe"
        }
        else {
            Write-SimCheck -Status FAIL -Message "Python failed to run: $script:PythonExe"
            $failed = $true
        }
    }
    else {
        Write-SimCheck -Status FAIL -Message "Python not found: $script:PythonExe"
        $failed = $true
    }

    $distros = @(& wsl -l -q 2>&1)
    $distroNames = @(
        $distros | ForEach-Object { "$_".Replace([string][char]0, '').Trim() } | Where-Object { $_ }
    )
    if ($LASTEXITCODE -eq 0 -and $distroNames -contains $script:WslDistro) {
        Write-SimCheck -Status PASS -Message "WSL distro is installed: $script:WslDistro"
    }
    else {
        Write-SimCheck -Status FAIL -Message "WSL distro is unavailable: $script:WslDistro"
        $failed = $true
    }

    $submoduleRelativePath = 'third_party/ego-planner-swarm'
    $submodulePath = Join-Path $resolvedRoot $submoduleRelativePath
    $gitlinkOutput = @(& git -C $resolvedRoot ls-files --stage -- $submoduleRelativePath 2>&1)
    $gitlinkExit = $LASTEXITCODE
    $gitlinkMatch = if ($gitlinkOutput.Count -gt 0) {
        [regex]::Match("$($gitlinkOutput[0])", '^160000\s+([0-9a-fA-F]{40})\s+\d+\s+')
    }
    else {
        $null
    }
    if ($gitlinkExit -ne 0 -or -not $gitlinkMatch -or -not $gitlinkMatch.Success) {
        Write-SimCheck -Status FAIL -Message "submodule is not pinned in Git: $submoduleRelativePath"
        $failed = $true
    }
    elseif (-not (Test-Path -LiteralPath $submodulePath -PathType Container)) {
        Write-SimCheck -Status FAIL -Message "submodule is not initialized: $submoduleRelativePath"
        $failed = $true
    }
    else {
        $expectedCommit = $gitlinkMatch.Groups[1].Value.ToLowerInvariant()
        $actualOutput = @(& git -C $submodulePath rev-parse HEAD 2>&1)
        $actualExit = $LASTEXITCODE
        $actualCommit = if ($actualOutput.Count -gt 0) { "$($actualOutput[0])".Trim().ToLowerInvariant() } else { '' }
        $dirtyOutput = @(& git -C $submodulePath status --porcelain --untracked-files=all 2>&1)
        $dirtyExit = $LASTEXITCODE
        if ($actualExit -eq 0 -and $dirtyExit -eq 0 -and $actualCommit -eq $expectedCommit -and $dirtyOutput.Count -eq 0) {
            Write-SimCheck -Status PASS -Message "submodule is initialized, clean, and pinned: $submoduleRelativePath@$expectedCommit"
        }
        else {
            Write-SimCheck -Status FAIL -Message "submodule must be initialized, clean, and pinned: $submoduleRelativePath"
            $failed = $true
        }
    }

    $egoSetup = Join-Path $submodulePath 'devel\setup.bash'
    if (Test-Path -LiteralPath $egoSetup -PathType Leaf) {
        Write-SimCheck -Status PASS -Message "EGO overlay exists: $egoSetup"
    }
    else {
        Write-SimCheck -Status FAIL -Message "EGO overlay is missing: $egoSetup"
        $failed = $true
    }

    $catkinTopLevel = Join-Path $resolvedRoot 'future_aircraft_ws\src\CMakeLists.txt'
    if (Test-Path -LiteralPath $catkinTopLevel -PathType Leaf) {
        Write-SimCheck -Status PASS -Message "Catkin workspace metadata exists: $catkinTopLevel"
    }
    else {
        Write-SimCheck -Status FAIL -Message "Catkin workspace metadata is missing: $catkinTopLevel"
        $failed = $true
    }

    $localEnvironment = Join-Path $resolvedRoot 'config\env_local.bat'
    if (-not (Test-Path -LiteralPath $localEnvironment)) {
        Write-SimCheck -Status WARN -Message "optional local environment is absent: $localEnvironment"
    }
    else {
        try {
            $null = Get-Content -LiteralPath $localEnvironment -Raw -ErrorAction Stop
            Write-SimCheck -Status PASS -Message "local environment is readable: $localEnvironment"
        }
        catch {
            Write-SimCheck -Status FAIL -Message "local environment is unreadable: $localEnvironment"
            $failed = $true
        }
    }

    $activeConfiguration = Join-Path $resolvedRoot 'config\uavs.json'
    try {
        $configuration = Get-Content -LiteralPath $activeConfiguration -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $namespaces = @($configuration.uavs.psobject.Properties | ForEach-Object { $_.Value.namespace })
        if ($namespaces -contains '/uav1' -and $namespaces -contains '/uav2') {
            Write-SimCheck -Status PASS -Message "active configuration contains /uav1 and /uav2: $activeConfiguration"
        }
        else {
            Write-SimCheck -Status FAIL -Message "active configuration must contain /uav1 and /uav2: $activeConfiguration"
            $failed = $true
        }
    }
    catch {
        Write-SimCheck -Status FAIL -Message "active configuration is unreadable: $activeConfiguration"
        $failed = $true
    }

    if ($failed) { return 2 }
    return 0
}

function Invoke-SimBuild {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    return Invoke-WorkspaceBuild -ProjectRoot $ProjectRoot
}

function Invoke-SimValidation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [ValidateSet('mission','core','lifecycle','all')]
        [string]$Suite
    )

    try {
        $resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
    }
    catch {
        Write-SimCheck -Status FAIL -Message "project root is not readable: $ProjectRoot"
        return 2
    }

    $suiteScripts = switch ($Suite) {
        'mission' { @('validate_repository.ps1') }
        'core' {
            @('validate_stage6c.ps1','validate_stage6d.ps1','validate_stage7.ps1','validate_stage8.ps1')
        }
        'lifecycle' { @('validate_lifecycle.ps1') }
        'all' {
            @(
                'validate_repository.ps1',
                'validate_stage1.ps1',
                'validate_stage2.ps1',
                'validate_stage2_1.ps1',
                'validate_stage3.ps1',
                'validate_stage4.ps1',
                'validate_stage5.ps1',
                'validate_stage5b.ps1',
                'validate_stage5c.ps1',
                'validate_stage5d.ps1',
                'validate_stage5e.ps1',
                'validate_stage6a.ps1',
                'validate_stage6b.ps1',
                'validate_stage6c.ps1',
                'validate_stage6d.ps1',
                'validate_stage7.ps1',
                'validate_stage8.ps1',
                'validate_lifecycle.ps1'
            )
        }
    }

    foreach ($scriptName in $suiteScripts) {
        $scriptPath = Join-Path $resolvedRoot "scripts\$scriptName"
        $exitCode = Invoke-ValidatorScript -ScriptPath $scriptPath
        if ($exitCode -ne 0) {
            return [int]$exitCode
        }
    }

    if ($Suite -eq 'mission') {
        $buildScript = Join-Path $resolvedRoot 'scripts\wsl\build_future_aircraft_ws.sh'
        if (-not (Test-Path -LiteralPath $buildScript -PathType Leaf)) {
            Write-SimCheck -Status FAIL -Message "focused build script not found: $buildScript"
            return 2
        }
        $exitCode = Invoke-WorkspaceBuild -ProjectRoot $resolvedRoot -AdditionalArguments @('--pkg','future_aircraft_mission')
        if ($exitCode -ne 0) {
            Write-SimCheck -Status FAIL -Message "$buildScript (exit $exitCode)"
            return [int]$exitCode
        }
    }

    Write-SimCheck -Status PASS -Message "validation suite completed: $Suite"
    return 0
}

function Resolve-ActiveStackManifest {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $manifestRoot = Join-Path $ProjectRoot 'logs\live_stack'
    if (-not (Test-Path -LiteralPath $manifestRoot -PathType Container)) {
        return $null
    }

    $activeCandidates = @()
    $stackDirectories = @(Get-ChildItem -LiteralPath $manifestRoot -Directory -Force -ErrorAction Stop)
    foreach ($stackDirectory in $stackDirectories) {
        $manifestPath = Join-Path $stackDirectory.FullName 'stack_manifest.json'
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            continue
        }

        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw -ErrorAction Stop |
                ConvertFrom-Json -ErrorAction Stop
            if ($manifest -isnot [pscustomobject] -or
                $manifest.schema_version -isnot [int] -or
                $manifest.schema_version -ne 2 -or
                $manifest.stack_id -isnot [string] -or
                -not $manifest.stack_id.Trim() -or
                $manifest.stack_id -ne $stackDirectory.Name) {
                throw 'manifest must be a schema v2 JSON object'
            }
        }
        catch {
            throw "malformed stack manifest: $manifestPath ($($_.Exception.Message))"
        }

        $isClean = $manifest.stop.clean -is [bool] -and $manifest.stop.clean -eq $true
        if (-not $isClean) {
            try {
                $activeCandidates += Get-Item -LiteralPath $manifestPath -ErrorAction Stop
            }
            catch {
                throw "malformed stack manifest: $manifestPath ($($_.Exception.Message))"
            }
        }
    }

    if ($activeCandidates.Count -gt 1) {
        $paths = ($activeCandidates | ForEach-Object { $_.FullName }) -join ', '
        throw "multiple active stack manifests: $paths"
    }
    if ($activeCandidates.Count -eq 1) {
        return $activeCandidates[0]
    }
    return $null
}

function Invoke-ProtectedScript {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        Write-SimCheck -Status FAIL -Message "protected wrapper not found: $ScriptPath"
        return 2
    }

    $ErrorActionPreference = 'Continue'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @Arguments 2>&1 |
        ForEach-Object { Write-Host $_ }
    return [int]$LASTEXITCODE
}

function Invoke-ProtectedBatch {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        Write-SimCheck -Status FAIL -Message "protected runner not found: $ScriptPath"
        return 2
    }

    $ErrorActionPreference = 'Continue'
    & $ScriptPath @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
    return [int]$LASTEXITCODE
}

function Get-Stage7RunContext {
    param(
        [Parameter(Mandatory = $true)][string]$ContextPath,
        [switch]$AllowIncomplete
    )

    if (-not (Test-Path -LiteralPath $ContextPath -PathType Leaf)) {
        return $null
    }

    try {
        $item = Get-Item -LiteralPath $ContextPath -ErrorAction Stop
        $values = @{}
        foreach ($line in @(Get-Content -LiteralPath $ContextPath -ErrorAction Stop)) {
            if ($line -match '^([A-Z0-9_]+)=(.*)$') {
                $value = $Matches[2].Trim()
                if (($value.StartsWith("'") -and $value.EndsWith("'")) -or
                    ($value.StartsWith('"') -and $value.EndsWith('"'))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                $values[$Matches[1]] = $value.Replace('\ ', ' ')
            }
        }
        $context = [pscustomobject]@{
            RunId = $values['STAGE7_RUN_ID']
            ReadinessReport = $values['STAGE7_READINESS_REPORT']
            WriteTimeUtc = $item.LastWriteTimeUtc
        }
        if (-not $context.RunId -or -not $context.ReadinessReport) {
            if ($AllowIncomplete) {
                return $context
            }
            throw "malformed Stage 7 run context: $ContextPath"
        }
        return $context
    }
    catch {
        if ($AllowIncomplete) {
            return $null
        }
        if ($_.Exception.Message -like 'malformed Stage 7 run context:*') {
            throw
        }
        throw "malformed Stage 7 run context: $ContextPath ($($_.Exception.Message))"
    }
}

function Wait-StackManifestRole {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$Role,
        [ValidateRange(0, 3600)][int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $manifest = Get-Content -LiteralPath $ManifestPath -Raw -ErrorAction Stop |
                ConvertFrom-Json -ErrorAction Stop
            if ($manifest -isnot [pscustomobject] -or $manifest.wsl_processes -isnot [array]) {
                throw 'wsl_processes must be an array'
            }
        }
        catch {
            throw "malformed stack manifest during Stage 7 role wait: $ManifestPath ($($_.Exception.Message))"
        }
        if (@($manifest.wsl_processes | Where-Object { $_.role -eq $Role }).Count -gt 0) {
            return $true
        }
        if ((Get-Date) -ge $deadline) {
            break
        }
        Start-Sleep -Seconds 1
    } while ($true)
    return $false
}

function Test-ProtectedManifestRoleAlive {
    param(
        [Parameter(Mandatory = $true)][string]$InspectWrapper,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$Role
    )

    if (-not (Test-Path -LiteralPath $InspectWrapper -PathType Leaf)) {
        return [pscustomobject]@{ ExitCode = 2; RoleAlive = $false }
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'powershell.exe'
    $startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$InspectWrapper`" -Manifest `"$ManifestPath`""
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $exitCode = [int]$process.ExitCode
    }
    catch {
        Write-SimCheck -Status FAIL -Message "protected inspect failed to run: $($_.Exception.Message)"
        return [pscustomobject]@{ ExitCode = 2; RoleAlive = $false }
    }
    finally {
        $process.Dispose()
    }

    if ($stdout.Trim()) { Write-Host $stdout.TrimEnd() }
    if ($stderr.Trim()) { Write-Host $stderr.TrimEnd() }
    if ($exitCode -ne 0) {
        return [pscustomobject]@{ ExitCode = $exitCode; RoleAlive = $false }
    }
    try {
        $report = $stdout | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Write-SimCheck -Status FAIL -Message 'protected inspect returned malformed output'
        return [pscustomobject]@{ ExitCode = 2; RoleAlive = $false }
    }
    $roleAlive = @(
        $report.owned | Where-Object {
            $_.entry.role -eq $Role -and $_.status -eq 'owned_and_alive'
        }
    ).Count -gt 0
    return [pscustomobject]@{ ExitCode = 0; RoleAlive = $roleAlive }
}

function Convert-WslPathToWindows {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ($Path -match '^/mnt/([A-Za-z])(/.*)?$') {
        $suffix = if ($Matches[2]) { $Matches[2].Replace('/', '\') } else { '' }
        return "$($Matches[1].ToUpperInvariant()):$suffix"
    }
    return $Path
}

function Invoke-SimStart {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [ValidateSet('base','dev')][string]$Profile = 'dev',
        [bool]$Execute = $false
    )

    $startWrapper = Join-Path $ProjectRoot 'scripts\live_stack_start.ps1'
    if (-not $Execute) {
        $exitCode = Invoke-ProtectedScript -ScriptPath $startWrapper -Arguments @('-DryRun')
        if ($exitCode -ne 0) {
            Write-SimCheck -Status FAIL -Message "live stack start (exit $exitCode)"
            return [int]$exitCode
        }
        if ($Profile -eq 'base') {
            Write-Host '[profile base] protected live stack start -> health gate'
        }
        else {
            Write-Host '[profile dev] protected live stack start -> health gate -> dual FAST-LIO readiness -> dual EGO-Swarm'
        }
        return 0
    }

    $activeManifest = Resolve-ActiveStackManifest -ProjectRoot $ProjectRoot
    if ($null -ne $activeManifest) {
        Write-SimCheck -Status FAIL -Message "active stack manifest blocks start: $($activeManifest.FullName)"
        return 2
    }

    $exitCode = Invoke-ProtectedScript -ScriptPath $startWrapper -Arguments @('-Execute')
    if ($exitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message "live stack start (exit $exitCode)"
        return [int]$exitCode
    }
    if ($Profile -eq 'base') {
        return 0
    }

    $devManifest = Resolve-ActiveStackManifest -ProjectRoot $ProjectRoot
    if ($null -eq $devManifest) {
        Write-SimCheck -Status FAIL -Message 'active stack manifest resolution (exit 2)'
        return 2
    }
    try {
        $devStackId = (Get-Content -LiteralPath $devManifest.FullName -Raw -ErrorAction Stop |
            ConvertFrom-Json -ErrorAction Stop).stack_id
    }
    catch {
        Write-SimCheck -Status FAIL -Message 'active stack manifest resolution (exit 2)'
        return 2
    }

    $currentRunPath = Join-Path $ProjectRoot 'logs\stage7_live\current_run.env'
    try {
        $previousRun = Get-Stage7RunContext -ContextPath $currentRunPath
    }
    catch {
        Write-SimCheck -Status FAIL -Message "Stage 7 current-run snapshot (exit 2): $($_.Exception.Message)"
        return 2
    }
    $fastlioRunner = Join-Path $ProjectRoot 'scripts\run_live_fastlio_dual.bat'
    $runnerArguments = @('--stack-id', $devStackId, '--manifest', $devManifest.FullName)
    $exitCode = Invoke-ProtectedBatch -ScriptPath $fastlioRunner -Arguments $runnerArguments
    if ($exitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message "Stage 7 dual FAST-LIO launch (exit $exitCode)"
        return [int]$exitCode
    }

    $readiness = $null
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        $candidate = Get-Stage7RunContext -ContextPath $currentRunPath -AllowIncomplete
        $isNewRun = $null -ne $candidate -and $candidate.RunId -and
            ($null -eq $previousRun -or $candidate.RunId -ne $previousRun.RunId) -and
            ($null -eq $previousRun -or $candidate.WriteTimeUtc -ne $previousRun.WriteTimeUtc)
        if ($isNewRun -and $candidate.ReadinessReport) {
            $readinessPath = Convert-WslPathToWindows -Path $candidate.ReadinessReport
            if (Test-Path -LiteralPath $readinessPath -PathType Leaf) {
                $readiness = $candidate
                break
            }
        }
        Start-Sleep -Seconds 1
    }
    if ($null -eq $readiness) {
        Write-SimCheck -Status FAIL -Message 'Stage 7 sensor readiness wait (exit 2)'
        return 2
    }

    $egoRunner = Join-Path $ProjectRoot 'scripts\run_live_ego_swarm_dual.bat'
    $exitCode = Invoke-ProtectedBatch -ScriptPath $egoRunner -Arguments $runnerArguments
    if ($exitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message "Stage 7 dual EGO-Swarm launch (exit $exitCode)"
        return [int]$exitCode
    }
    try {
        $egoRegistered = Wait-StackManifestRole -ManifestPath $devManifest.FullName `
            -Role 'wsl:ego_swarm_session' -TimeoutSeconds 180
    }
    catch {
        Write-SimCheck -Status FAIL -Message "Stage 7 dual EGO-Swarm launch (exit 2): $($_.Exception.Message)"
        return 2
    }
    if (-not $egoRegistered) {
        Write-SimCheck -Status FAIL -Message 'Stage 7 dual EGO-Swarm launch (exit 2)'
        return 2
    }
    # The protected runner registers its shell immediately before exec roslaunch.
    # Give immediate exec/roslaunch failures time to surface, then require the
    # registered identity to remain alive according to the protected inspector.
    Start-Sleep -Seconds 2
    $inspectWrapper = Join-Path $ProjectRoot 'scripts\live_stack_inspect.ps1'
    $egoInspection = Test-ProtectedManifestRoleAlive -InspectWrapper $inspectWrapper `
        -ManifestPath $devManifest.FullName -Role 'wsl:ego_swarm_session'
    if ($egoInspection.ExitCode -ne 0 -or -not $egoInspection.RoleAlive) {
        $failureCode = if ($egoInspection.ExitCode -ne 0) { $egoInspection.ExitCode } else { 2 }
        Write-SimCheck -Status FAIL -Message "Stage 7 dual EGO-Swarm launch (exit $failureCode)"
        return [int]$failureCode
    }
    return 0
}

function Invoke-SimStatus {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $activeManifest = Resolve-ActiveStackManifest -ProjectRoot $ProjectRoot
    if ($null -eq $activeManifest) {
        Write-Host 'no active stack'
        return 0
    }

    $inspectWrapper = Join-Path $ProjectRoot 'scripts\live_stack_inspect.ps1'
    $exitCode = Invoke-ProtectedScript -ScriptPath $inspectWrapper -Arguments @(
        '-Manifest', $activeManifest.FullName
    )
    if ($exitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message "live stack inspect (exit $exitCode)"
    }
    return [int]$exitCode
}

function Invoke-SimStop {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [bool]$Execute = $false
    )

    $activeManifest = Resolve-ActiveStackManifest -ProjectRoot $ProjectRoot
    if ($null -eq $activeManifest) {
        Write-Host 'no active stack'
        return 0
    }

    $stopWrapper = Join-Path $ProjectRoot 'scripts\end_live_stack.ps1'
    $arguments = @('-Manifest', $activeManifest.FullName)
    if (-not $Execute) {
        $arguments += '-DryRun'
    }
    $exitCode = Invoke-ProtectedScript -ScriptPath $stopWrapper -Arguments $arguments
    if ($exitCode -ne 0) {
        Write-SimCheck -Status FAIL -Message "live stack stop (exit $exitCode)"
    }
    return [int]$exitCode
}

function Invoke-SimLogCleanup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [bool]$Execute = $false
    )

    Write-SimCheck -Status FAIL -Message "command 'clean-logs' is not implemented yet; no files were removed"
    return 2
}

Export-ModuleMember -Function @(
    'Resolve-ActiveStackManifest',
    'Invoke-SimDoctor',
    'Invoke-SimBuild',
    'Invoke-SimValidation',
    'Invoke-SimStart',
    'Invoke-SimStatus',
    'Invoke-SimStop',
    'Invoke-SimLogCleanup'
)
