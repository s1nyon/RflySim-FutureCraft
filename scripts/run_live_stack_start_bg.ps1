param()

# Launch live_stack_start.ps1 in the background with captured output so the
# Gate B fresh run can be polled with short commands instead of a long blocking
# tool call.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Stamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
$Log = Join-Path $ProjectRoot "logs\live_stack_start_$Stamp.log"
$Err = "$Log.err"
$Arguments = @(
    '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'live_stack_start.ps1'),
    '-Execute', '-Course', 'competition_course_v2'
)
$Process = Start-Process -FilePath 'powershell.exe' -ArgumentList $Arguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $Log -RedirectStandardError $Err -WindowStyle Hidden -PassThru
Write-Output "bg_pid=$($Process.Id)"
Write-Output "log=$Log"
Write-Output "err=$Err"
