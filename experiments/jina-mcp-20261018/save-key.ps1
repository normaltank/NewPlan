$ErrorActionPreference = 'Stop'
$secretDirectory = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\credentials'
$secretPath = Join-Path $secretDirectory 'jina-test.dpapi'
if (Test-Path -LiteralPath $secretPath) { throw 'Credential already exists; no overwrite performed.' }
New-Item -ItemType Directory -Path $secretDirectory -Force | Out-Null
$credential = Read-Host 'Jina API key (hidden)' -AsSecureString
try {
    if ($credential.Length -lt 20) { throw 'Credential is empty or too short.' }
    $credential | ConvertFrom-SecureString | Set-Content -LiteralPath $secretPath -Encoding UTF8
    $acl = Get-Acl -LiteralPath $secretPath
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
    $acl.SetAccessRule($rule)
    Set-Acl -LiteralPath $secretPath -AclObject $acl
    Write-Host 'Credential saved with Windows account encryption.'
} finally {
    $credential.Dispose()
}
