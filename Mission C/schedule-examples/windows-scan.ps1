# Example only: edit these paths, run manually, then configure Task Scheduler yourself.
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$missionPython = 'C:\Mission C\.venv\Scripts\python.exe'
$missionEntry = 'C:\Mission C\server.py'
$missionData = 'C:\Mission C data'
$missionInputs = 'C:\Mission C input'
$missionManifest = 'C:\Mission C cache\manifest.json'
New-Item -ItemType Directory -Path $missionData -Force | Out-Null
if (-not (Test-Path -LiteralPath $missionPython -PathType Leaf)) { throw 'Configure missionPython first.' }
# Windows PowerShell 5 can turn native stderr into ErrorRecords; preserve native exit status.
$ErrorActionPreference = 'Continue'
& $missionPython $missionEntry --data-root $missionData scan $missionInputs --cache-manifest $missionManifest --run 1>> (Join-Path $missionData 'scan.jsonl') 2>> (Join-Path $missionData 'scan.stderr.log')
exit $LASTEXITCODE
