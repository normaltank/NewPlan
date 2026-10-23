$ErrorActionPreference = 'Stop'
$missionRoot = $PSScriptRoot
$missionLocalPython = Join-Path $missionRoot '.venv\Scripts\python.exe'
$missionExistingPython = Join-Path $missionRoot '..\..\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $missionLocalPython) {
    $missionPython = $missionLocalPython
} elseif (Test-Path -LiteralPath $missionExistingPython) {
    $missionPython = $missionExistingPython
} else {
    $missionPython = 'python'
}
& $missionPython -B (Join-Path $missionRoot 'audit.py') @args
exit $LASTEXITCODE
