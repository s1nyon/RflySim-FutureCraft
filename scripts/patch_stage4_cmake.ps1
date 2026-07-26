$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CMakePath = Join-Path $ProjectRoot 'future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt'
$Text = Get-Content -Raw -LiteralPath $CMakePath
if ($Text -notmatch 'scripts/ego_swarm_adapter\.py') {
    $Text = $Text -replace "catkin_install_python\(PROGRAMS\r?\n", "catkin_install_python(PROGRAMS`r`n  scripts/ego_swarm_adapter.py`r`n"
    Set-Content -LiteralPath $CMakePath -Value $Text -Encoding ASCII
}
Write-Host '[PASS] CMakeLists.txt includes ego_swarm_adapter.py'
