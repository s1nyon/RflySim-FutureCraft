param(
    [Parameter(Mandatory = $true)][string]$Manifest,
    [switch]$DryRun,
    [switch]$Execute,
    [string]$Reason = 'stack stop requested',
    [double]$IntWait = 5.0,
    [double]$TermWait = 5.0,
    [string]$Distro = 'RflySim-20.04'
)

# P0 Safe Live Stack Lifecycle: manifest-only graceful stop.
# Default is DryRun; real stop requires -Execute.
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
if (-not $Execute) { $DryRun = $true }

$stopArgs = @(
    '--manifest', $Manifest,
    '--distro', $Distro,
    '--reason', $Reason,
    '--int-wait', "$IntWait",
    '--term-wait', "$TermWait"
)
if ($Execute) { $stopArgs += '--execute' }

& $python (Join-Path $PSScriptRoot 'lifecycle\stack_stop.py') @stopArgs
exit $LASTEXITCODE
