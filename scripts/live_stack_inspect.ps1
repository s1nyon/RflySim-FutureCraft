param(
    [Parameter(Mandatory = $true)][string]$Manifest,
    [string]$Distro = 'RflySim-20.04'
)

# P0 Safe Live Stack Lifecycle: read-only inspection. Never kills anything.
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
& $python (Join-Path $PSScriptRoot 'lifecycle\stack_inspect.py') --manifest $Manifest --distro $Distro
exit $LASTEXITCODE
