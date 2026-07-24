param(
    [Parameter(Mandatory = $true)]
    [string]$Snapshot,
    [Parameter(Mandatory = $true)]
    [string]$DestinationRoot,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$verifyScript = Join-Path $PSScriptRoot "verify-local-backup.ps1"
$snapshotFull = (Resolve-Path $Snapshot).Path
$destinationFull = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
$repoFull = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\')

if ($destinationFull.Equals($repoFull, [StringComparison]::OrdinalIgnoreCase) -or
    $destinationFull.StartsWith("$repoFull\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "The restore destination must be outside the repository."
}
if ($destinationFull.Equals($snapshotFull, [StringComparison]::OrdinalIgnoreCase) -or
    $destinationFull.StartsWith("$snapshotFull\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "The restore destination cannot be inside the snapshot."
}

& powershell -ExecutionPolicy Bypass -File $verifyScript -Snapshot $snapshotFull
if ($LASTEXITCODE -ne 0) { throw "Snapshot verification failed." }

if ((Test-Path -LiteralPath $destinationFull) -and -not $Force) {
    throw "Destination exists; choose a new disposable folder or use -Force explicitly."
}
New-Item -ItemType Directory -Path $destinationFull -Force | Out-Null
$databaseDestination = Join-Path $destinationFull "db\aero_ops.sqlite3"
$documentsDestination = Join-Path $destinationFull "documents"
New-Item -ItemType Directory -Path (Split-Path $databaseDestination) -Force | Out-Null

$databaseSource = Get-ChildItem -Path $snapshotFull -Filter "*.sqlite3" -File | Select-Object -First 1
if (-not $databaseSource) {
    throw "No SQLite database found in snapshot."
}
Copy-Item -LiteralPath $databaseSource.FullName -Destination $databaseDestination -Force

$documentsSource = Join-Path $snapshotFull "documents"
if (Test-Path -LiteralPath $documentsSource) {
    Copy-Item -LiteralPath $documentsSource -Destination $documentsDestination -Recurse -Force
}

[ordered]@{
    format = "aerocontrol-local-restore-v1"
    restored_at = (Get-Date).ToUniversalTime().ToString("o")
    source_snapshot = $snapshotFull
    database = $databaseDestination
    documents = $documentsDestination
} | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $destinationFull "restore-manifest.json") -Encoding UTF8

Write-Host "Local snapshot restored to: $destinationFull"
