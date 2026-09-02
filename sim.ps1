[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start','status','stop','build','validate','doctor','clean-logs')]
    [string]$Command = 'status',
    [ValidateSet('base','dev')][string]$Profile = 'dev',
    [ValidateSet('mission','core','lifecycle','all')][string]$Suite = 'core',
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'

try {
    $projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
    $modulePath = Join-Path $projectRoot 'scripts\sim_cli.psm1'
    Import-Module -Force -Name $modulePath

    $result = switch ($Command) {
        'doctor' {
            Invoke-SimDoctor -ProjectRoot $projectRoot
            break
        }
        'build' {
            Invoke-SimBuild -ProjectRoot $projectRoot
            break
        }
        'validate' {
            Invoke-SimValidation -ProjectRoot $projectRoot -Suite $Suite
            break
        }
        'start' {
            Invoke-SimStart -ProjectRoot $projectRoot -Profile $Profile -Execute:$Execute.IsPresent
            break
        }
        'status' {
            Invoke-SimStatus -ProjectRoot $projectRoot
            break
        }
        'stop' {
            Invoke-SimStop -ProjectRoot $projectRoot -Execute:$Execute.IsPresent
            break
        }
        'clean-logs' {
            Invoke-SimLogCleanup -ProjectRoot $projectRoot -Execute:$Execute.IsPresent
            break
        }
    }

    exit [int]$result
}
catch {
    Write-Error $_
    exit 1
}
