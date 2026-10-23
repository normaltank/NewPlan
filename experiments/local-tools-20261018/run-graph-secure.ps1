param([ValidateSet('scrapegraph','direct_ds')][string]$Arm, [string[]]$Ids)
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pythonPath = Join-Path $PSScriptRoot '.venv-graph\Scripts\python.exe'
$runArgs = @((Join-Path $PSScriptRoot 'run_graph.py'), $Arm)
if ($Ids) { $runArgs += '--ids'; $runArgs += $Ids }
if (-not [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    & $pythonPath @runArgs
    exit $LASTEXITCODE
}
$credentialPath = Join-Path $sourceRoot '.secrets\deepseek-api-key.dpapi'
$credentialValue = (Get-Content -LiteralPath $credentialPath -Raw).Trim() | ConvertTo-SecureString
$credentialPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credentialValue)
try {
    $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($credentialPointer)
    & $pythonPath @runArgs
    $taskExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($credentialPointer)
}
exit $taskExitCode
