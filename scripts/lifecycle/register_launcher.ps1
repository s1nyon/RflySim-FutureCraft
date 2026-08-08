param(
    [Parameter(Mandatory = $true)][string]$Manifest,
    [Parameter(Mandatory = $true)][string]$Role,
    [Parameter(Mandatory = $true)][string]$CommandLine,
    [string]$FilePath = 'cmd.exe',
    [string]$Arguments = '',
    [string]$WorkingDirectory = ''
)

# P0.1 lifecycle: launch a process and register its PID in the stack manifest at
# creation time (Process.Start -PassThru). Never used to adopt existing processes.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = 'D:\PX4PSP\Python38\python.exe'
$register = Join-Path $PSScriptRoot 'stack_register.py'

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $FilePath
$psi.Arguments = $Arguments
$psi.WorkingDirectory = if ($WorkingDirectory) { $WorkingDirectory } else { (Get-Location).Path }
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$proc = [System.Diagnostics.Process]::Start($psi)

if ($FilePath -eq 'cmd.exe') {
    $cmdline = "cmd /k call $CommandLine"
} else {
    $cmdline = "$FilePath $Arguments"
}
& $python $register register `
    --manifest $Manifest `
    --side windows `
    --pid $proc.Id `
    --role $Role `
    --name ([System.IO.Path]::GetFileNameWithoutExtension($FilePath)) `
    --cmdline $cmdline `
    --reason 'created via register_launcher.ps1 (Process.Start -PassThru at creation)' 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Output ''
    exit 1
}
Write-Output $proc.Id
exit 0
