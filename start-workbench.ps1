param([switch]$SeedNantong)
$ErrorActionPreference = 'Stop'
$arguments = @('workbench.py')
if ($SeedNantong) { $arguments += @('--seed', 'ntu-batch.json') }
& (Join-Path $PSScriptRoot 'secure-api-run.ps1') -PythonArgs $arguments
exit $LASTEXITCODE
