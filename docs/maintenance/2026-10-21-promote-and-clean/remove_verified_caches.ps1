$ErrorActionPreference = 'Stop'
$expectedRoot = [IO.Path]::GetFullPath('D:\Agent Workspace\Intern\MyPlan').TrimEnd('\')
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'cleanup-manifest.json') -Raw | ConvertFrom-Json
if ($manifest.root.TrimEnd('\') -ne $expectedRoot) { throw 'Unexpected workspace root' }
$checked = @()
foreach ($entry in $manifest.items) {
    $resolved = (Resolve-Path -LiteralPath $entry.path -ErrorAction Stop).ProviderPath.TrimEnd('\')
    if (-not $resolved.StartsWith($expectedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside workspace' }
    if ($resolved -ne [IO.Path]::GetFullPath($entry.path).TrimEnd('\')) { throw 'Resolved path changed' }
    if (($resolved -notmatch '\\.runtime\\(dev-venv|worker-venv)$') -and
        ($resolved -notmatch '\\OpenSource\\Mission B\\SmallMission\\') -and
        ($resolved -ne (Join-Path $expectedRoot 'OpenSource\experiments\local-tools-20261018\.uv-cache'))) { throw 'Outside approved cache scope' }
    $rootItem = Get-Item -LiteralPath $resolved -Force
    if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Root is a reparse point' }
    $files = @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
    if (@($files | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Reparse point found' }
    $leafFiles = @($files | Where-Object { -not $_.PSIsContainer })
    $bytes = ($leafFiles | Measure-Object -Property Length -Sum).Sum
    if (($leafFiles.Count -ne $entry.files) -or ([long]$bytes -ne [long]$entry.bytes)) { throw "Candidate changed: $resolved" }
    $checked += $entry
}
$logPath = Join-Path $PSScriptRoot 'cleanup-results.jsonl'
foreach ($entry in $checked) {
    Remove-Item -LiteralPath $entry.path -Recurse -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $entry.path) { throw "Removal incomplete: $($entry.path)" }
    @{path=$entry.relative;bytes=$entry.bytes;files=$entry.files;removed_at=(Get-Date).ToString('o')} | ConvertTo-Json -Compress | Add-Content -LiteralPath $logPath -Encoding utf8
    Write-Output "Removed verified cache: $($entry.relative)"
}
