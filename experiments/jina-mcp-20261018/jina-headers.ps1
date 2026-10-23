# v1.0: stdout is an authentication pipe, never a terminal/log destination.
$ErrorActionPreference = 'Stop'
if (-not [Console]::IsOutputRedirected) { throw 'Run only as an MCP credential helper with captured stdout.' }
$secretPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\credentials\jina-test.dpapi'
if (-not (Test-Path -LiteralPath $secretPath)) { throw 'Jina encrypted credential is missing.' }
$credential = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credential)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if (-not $token.StartsWith('jina_')) { throw 'Unexpected credential format.' }
    $headers = @{ Authorization = 'Bearer ' + $token }
    [Console]::Out.WriteLine(($headers | ConvertTo-Json -Compress))
} finally {
    $token = $null
    $headers = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $credential.Dispose()
}
