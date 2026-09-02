param(
    [Parameter(Mandatory = $true)][string]$Manifest,
    [switch]$DryRun,
    [switch]$Execute,
    [string]$PlanToken,
    [string]$Distro = 'RflySim-20.04'
)

# Explicit metadata-only stale ownership retirement. Default is DryRun.
$python = 'D:\PX4PSP\Python38\python.exe'
if (-not $Execute) { $DryRun = $true }
if ($Execute -and [string]::IsNullOrWhiteSpace($PlanToken)) {
    Write-Error '-Execute requires -PlanToken from the immediately preceding eligible DryRun.'
    exit 2
}
$retireArgs = @('--manifest', $Manifest, '--distro', $Distro)
if ($Execute) { $retireArgs += @('--execute', '--plan-token', $PlanToken) }
& $python (Join-Path $PSScriptRoot 'lifecycle\stack_retire_stale.py') @retireArgs
exit $LASTEXITCODE
