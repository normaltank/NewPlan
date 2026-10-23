$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath('D:\Agent Workspace\Intern\MyPlan').TrimEnd('\')
$report = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'legacy-archive-verification.json') -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $report.source).ProviderPath.TrimEnd('\')
if ($source -ne (Join-Path $workspaceRoot 'server\outputs')) { throw 'Unexpected legacy output path' }
if (-not $source.StartsWith($workspaceRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside workspace' }
$archive = (Resolve-Path -LiteralPath $report.archive).ProviderPath
$backupRoot = Join-Path $workspaceRoot 'OpenSource\.local-backups\2026-10-21-promotion'
if (-not $archive.StartsWith($backupRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected archive path' }
if (-not $report.verified_all_sha256) { throw 'Archive not verified' }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $report.archive_sha256) { throw 'Archive changed' }
if ((Get-Item -LiteralPath $source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source root is a reparse point' }
$all = @(Get-ChildItem -LiteralPath $source -Recurse -Force)
if (@($all | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Source contains reparse point' }
$files = @($all | Where-Object { -not $_.PSIsContainer })
if ($files.Count -ne $report.files -or [long]($files | Measure-Object Length -Sum).Sum -ne [long]$report.source_bytes) { throw 'Source count or size changed' }
# Compare each original path, size and modification time with the verified archive manifest.
Add-Type -AssemblyName System.IO.Compression
$stream = [IO.File]::OpenRead($archive)
try {
    $zip = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Read, $true)
    try {
        $reader = [IO.StreamReader]::new($zip.GetEntry('ARCHIVE_MANIFEST.json').Open())
        try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json -Depth 12 } finally { $reader.Dispose() }
    } finally { $zip.Dispose() }
} finally { $stream.Dispose() }
$indexed = @{}
foreach ($file in $files) { $indexed[$file.FullName] = $file }
foreach ($entry in $manifest.files) {
    $full = [IO.Path]::GetFullPath((Join-Path $workspaceRoot $entry.path))
    if (-not $full.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path outside source' }
    $file = $indexed[$full]
    if ($null -eq $file -or $file.Length -ne $entry.size) { throw 'Source file changed' }
    $unixNs = [decimal]($file.LastWriteTimeUtc.Ticks - [DateTime]::UnixEpoch.Ticks) * 100
    if ($unixNs -ne [decimal]$entry.mtime_ns) { throw "Source timestamp changed: $($entry.path)" }
}
Remove-Item -LiteralPath $source -Recurse -Force -ErrorAction Stop
if (Test-Path -LiteralPath $source) { throw 'Legacy output removal incomplete' }
@{path='server/outputs';bytes=$report.source_bytes;files=$report.files;archive=$report.archive;removed_at=(Get-Date).ToString('o')} | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'cleanup-results.jsonl') -Encoding utf8
# Remove only this task's incomplete first archive after the verified replacement exists.
$partial = Join-Path $backupRoot 'legacy-server-outputs.partial.zip'
if (Test-Path -LiteralPath $partial) {
    $resolvedPartial = (Resolve-Path -LiteralPath $partial).ProviderPath
    if (-not $resolvedPartial.StartsWith($backupRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Partial archive outside backup directory' }
    Remove-Item -LiteralPath $resolvedPartial -Force
}
Write-Output 'Legacy output originals removed after archive and source verification; archive retained.'
