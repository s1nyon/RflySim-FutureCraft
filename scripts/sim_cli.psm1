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

function Invoke-SimStart {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [ValidateSet('base','dev')][string]$Profile = 'dev',
        [bool]$Execute = $false
    )

    Write-SimCheck -Status FAIL -Message "command 'start' is not implemented yet; no simulation was started"
    return 2
}

function Invoke-SimStatus {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    Write-SimCheck -Status FAIL -Message "command 'status' is not implemented yet; no lifecycle action was taken"
    return 2
}

function Invoke-SimStop {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [bool]$Execute = $false
    )

    Write-SimCheck -Status FAIL -Message "command 'stop' is not implemented yet; no process was stopped"
    return 2
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
    'Invoke-SimDoctor',
    'Invoke-SimBuild',
    'Invoke-SimValidation',
    'Invoke-SimStart',
    'Invoke-SimStatus',
    'Invoke-SimStop',
    'Invoke-SimLogCleanup'
)
