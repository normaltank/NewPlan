param(
    [switch]$Initialize,
    [string[]]$PythonArgs = @('deepseek_api.py', '--probe')
)
$ErrorActionPreference = 'Stop'
$secretDirectory = Join-Path $PSScriptRoot '.secrets'
$credentialPath = Join-Path $secretDirectory 'deepseek-api-key.dpapi'
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if ($Initialize) {
    if (Test-Path -LiteralPath $credentialPath) { throw 'Credential already exists; no overwrite performed.' }
    New-Item -ItemType Directory -Path $secretDirectory -Force | Out-Null
    Write-Host 'Enter DeepSeek API key (hidden):'
    $credentialValue = Read-Host -AsSecureString
    if ($credentialValue.Length -lt 16) { throw 'Credential input was empty or too short.' }
    $credentialValue | ConvertFrom-SecureString | Set-Content -LiteralPath $credentialPath -Encoding UTF8
    Write-Host 'Credential saved encrypted for this Windows account.'
    exit 0
}
if (-not [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    Push-Location $PSScriptRoot
    try { & $pythonPath @PythonArgs; $taskExitCode = $LASTEXITCODE } finally { Pop-Location }
    exit $taskExitCode
}
if (-not (Test-Path -LiteralPath $credentialPath)) { throw 'No credential. Set DEEPSEEK_API_KEY or initialize the local encrypted credential.' }
$credentialValue = (Get-Content -LiteralPath $credentialPath -Raw).Trim() | ConvertTo-SecureString
$credentialPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credentialValue)
try {
    $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($credentialPointer)
    Push-Location $PSScriptRoot
    try { & $pythonPath @PythonArgs; $taskExitCode = $LASTEXITCODE } finally { Pop-Location }
} finally {
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($credentialPointer)
}
exit $taskExitCode
