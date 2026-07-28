function ConvertTo-WslPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ($Path -match '^[A-Za-z]:\\') {
        $drive = $Path.Substring(0, 1).ToLowerInvariant()
        $rest = $Path.Substring(2).Replace('\', '/')
        return "/mnt/$drive$rest"
    }

    return $Path.Replace('\', '/')
}

function Get-ArrayTail {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Values
    )

    if ($Values.Count -le 1) {
        return @()
    }

    return @($Values[1..($Values.Count - 1)])
}

function Test-ContractPythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    try {
        $extraArgs = Get-ArrayTail -Values $Command
        & $Command[0] @extraArgs --version 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Get-ContractPythonRunner {
    param(
        [string]$WindowsPython = 'D:\PX4PSP\Python38\python.exe',
        [string]$WslDistro = 'RflySim-20.04'
    )

    foreach ($candidate in @(@($WindowsPython), @('python'))) {
        if (Test-ContractPythonCommand -Command $candidate) {
            return @{
                Kind = 'windows'
                Command = $candidate[0]
                Args = Get-ArrayTail -Values $candidate
            }
        }
    }

    try {
        & wsl.exe -d $WslDistro -- python3 --version 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return @{
                Kind = 'wsl'
                Command = 'wsl.exe'
                Distro = $WslDistro
                Python = 'python3'
            }
        }
    }
    catch {}

    return $null
}

function ConvertTo-ContractArgument {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Value,
        [string]$Kind
    )

    if ($Kind -eq 'wsl' -and $Value -is [string] -and $Value -match '^[A-Za-z]:\\') {
        return ConvertTo-WslPath -Path $Value
    }

    return $Value
}

function Invoke-ContractPythonScript {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Runner,

        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [Parameter(Mandatory = $true)]
        [object[]]$Arguments
    )

    if ($Runner.Kind -eq 'windows') {
        $command = @($Runner.Command) + @($Runner.Args) + @($ScriptPath) + $Arguments
        $extraArgs = Get-ArrayTail -Values $command
        & $command[0] @extraArgs 2>&1
        return $LASTEXITCODE
    }

    if ($Runner.Kind -eq 'wsl') {
        $wslScript = ConvertTo-WslPath -Path $ScriptPath
        $wslArguments = @()
        foreach ($argument in $Arguments) {
            $wslArguments += ConvertTo-ContractArgument -Value $argument -Kind $Runner.Kind
        }
        & $Runner.Command -d $Runner.Distro -- $Runner.Python $wslScript @wslArguments 2>&1
        return $LASTEXITCODE
    }

    throw "Unsupported contract python runner kind '$($Runner.Kind)'"
}
