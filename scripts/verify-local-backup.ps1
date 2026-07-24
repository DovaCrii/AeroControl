param(
    [Parameter(Mandatory = $true)]
    [string]$Snapshot
)

$ErrorActionPreference = "Stop"
$snapshotFull = (Resolve-Path $Snapshot).Path
$snapshotRoot = $snapshotFull.TrimEnd('\')
$manifestPath = Join-Path $snapshotFull "snapshot-manifest.json"
if (-not (Test-Path $manifestPath)) {
    throw "snapshot-manifest.json not found in $snapshotFull"
}

$manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
if ($manifest.format -ne "aerocontrol-local-backup-v1") {
    throw "Unsupported snapshot format."
}

foreach ($entry in $manifest.files) {
    $relativePath = ($entry.path -replace '/', '\')
    $filePath = [IO.Path]::GetFullPath((Join-Path $snapshotRoot $relativePath))
    if (-not $filePath.StartsWith("$snapshotRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escapes the snapshot: $($entry.path)"
    }
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "Missing file: $($entry.path)"
    }
    $file = Get-Item -LiteralPath $filePath
    if ($file.Length -ne [int64]$entry.size) {
        throw "Size mismatch: $($entry.path)"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $filePath).Hash.ToLowerInvariant()
    if ($hash -ne $entry.sha256) {
        throw "Checksum mismatch: $($entry.path)"
    }
}

Write-Host "Local snapshot verified: $snapshotFull"
