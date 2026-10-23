$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath('D:\Agent Workspace\Intern\MyPlan').TrimEnd('\')
$app = Join-Path $root 'OpenSource'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'retirement-manifest.json') -Raw | ConvertFrom-Json -Depth 12
if ($manifest.root -ne $root -or $manifest.app -ne $app) { throw 'Workspace identity mismatch' }
$allowedRootNames = @('_archive','.claude','.github','.planning','.playwright-mcp','.pytest_cache','.ruff_cache','.runtime','Archived','Claude outputs','docs','Opus','scratch','scripts','server','Sheets','tests','教师列表.xlsx','启动自动巡检接单.bat','双击启动局域网服务.bat','重启本地服务.bat','AGENT_HANDOVER.md','CHANGELOG.md','CONSTITUTION.md','CONTEXT.md','harvest_script.js','pyproject.toml','requirements-dev.lock','requirements-dev.txt','requirements.lock','requirements.txt')
$allowedNested = @((Join-Path $root '.agents\plugins'),(Join-Path $app '.local-backups\2026-10-21-promotion\documentation-before.zip'),(Join-Path $app '.local-backups\2026-10-21-promotion\legacy-server-outputs.zip'),(Join-Path $app '.local-backups\2026-10-21-promotion\working-tree-before.patch'))
$inputs = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'retained-inputs.json') -Raw | ConvertFrom-Json
foreach ($inputFile in $inputs) {
    if ((Get-FileHash -LiteralPath $inputFile.destination -Algorithm SHA256).Hash -ne $inputFile.sha256) { throw 'Retained college input changed' }
}
# Validate every absolute root and enumerate without following reparse points.
$checked = @()
foreach ($entry in $manifest.items) {
    $resolved = (Resolve-Path -LiteralPath $entry.path -ErrorAction Stop).ProviderPath.TrimEnd('\')
    if ($resolved -ne [IO.Path]::GetFullPath($entry.path).TrimEnd('\')) { throw 'Target resolution changed' }
    if (-not $resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside workspace' }
    $isRootChild = ([IO.Path]::GetDirectoryName($resolved) -eq $root) -and ([IO.Path]::GetFileName($resolved) -in $allowedRootNames)
    if (-not $isRootChild -and $resolved -notin $allowedNested) { throw 'Target outside explicit deletion scope' }
    $top = Get-Item -LiteralPath $resolved -Force
    if ($top.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Top-level target became a reparse point' }
    $entries = if ($top.PSIsContainer) { @(Get-ChildItem -LiteralPath $resolved -Recurse -Force) } else { @($top) }
    $links = @($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    $ordinaryFiles = @($entries | Where-Object { -not $_.PSIsContainer -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) })
    $bytes = [long]($ordinaryFiles | Measure-Object Length -Sum).Sum
    if ($ordinaryFiles.Count -ne $entry.files -or $bytes -ne $entry.bytes) { throw "Contents changed: $resolved" }
    $actualLinks = @($links.FullName | Sort-Object)
    $expectedLinks = @($entry.reparse_points | Sort-Object)
    if ($actualLinks.Count -ne $expectedLinks.Count) { throw 'Link inventory changed' }
    if ($actualLinks.Count -gt 0 -and @(Compare-Object $actualLinks $expectedLinks).Count) { throw 'Link paths changed' }
    $checked += @{entry=$entry;path=$resolved;links=$links}
}
foreach ($item in $checked) {
    foreach ($link in $item.links) {
        $linkPath = [IO.Path]::GetFullPath($link.FullName)
        if (-not $linkPath.StartsWith($item.path + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Link outside target' }
        $liveLink = Get-Item -LiteralPath $linkPath -Force
        if (-not ($liveLink.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Link changed to ordinary file' }
        # No recursion: remove only the junction/symlink, never its destination.
        Remove-Item -LiteralPath $linkPath -Force -Confirm:$false
    }
    if ($item.entry.directory) {
        $remainingLinks = @(Get-ChildItem -LiteralPath $item.path -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
        if ($remainingLinks.Count) { throw 'Reparse point remained before recursive deletion' }
        Remove-Item -LiteralPath $item.path -Recurse -Force -Confirm:$false
    } else {
        Remove-Item -LiteralPath $item.path -Force -Confirm:$false
    }
    if (Test-Path -LiteralPath $item.path) { throw 'Deletion incomplete' }
    @{path=$item.entry.relative;bytes=$item.entry.bytes;files=$item.entry.files;links_unlinked=$item.links.Count;removed_at=(Get-Date).ToString('o')} | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'deleted.jsonl') -Encoding utf8
    Write-Output ('Deleted retired MyPlan material: ' + $item.entry.relative)
}
