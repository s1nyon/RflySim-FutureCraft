$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
& $python (Join-Path $ProjectRoot 'tests\third_party_dependency_check.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python (Join-Path $ProjectRoot 'tests\future_aircraft_mission_package_check.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python (Join-Path $ProjectRoot 'tests\developer_workspace_config_check.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python (Join-Path $ProjectRoot 'tests\log_cleanup_check.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python (Join-Path $ProjectRoot 'tests\sim_cli_check.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host '[PASS] repository dependency contracts'
exit 0
