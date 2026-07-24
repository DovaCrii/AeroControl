param(
    [string]$OutputRoot = $env:AEROCONTROL_BACKUP_DIR
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $OutputRoot) {
    throw "Set AEROCONTROL_BACKUP_DIR to a directory outside the repository."
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
if ($OutputRoot.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Backup output must be outside the repository: $OutputRoot"
}

$Supabase = (Get-Command supabase -ErrorAction SilentlyContinue).Source
if (-not $Supabase) {
    throw "Supabase CLI is required. Install it from the official Supabase documentation."
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$Destination = Join-Path $OutputRoot $Stamp
$StorageBucket = $env:SUPABASE_STORAGE_BUCKET
New-Item -ItemType Directory -Path $Destination -Force | Out-Null

Push-Location $RepoRoot
try {
    & $Supabase migration list --linked | Out-File (Join-Path $Destination "migration-list.txt") -Encoding utf8
    & $Supabase db dump --linked --file (Join-Path $Destination "schema.sql")
    & $Supabase db dump --linked --data-only --use-copy --file (Join-Path $Destination "data.sql")

    if ($StorageBucket) {
        $StorageDestination = Join-Path $Destination "storage"
        New-Item -ItemType Directory -Path $StorageDestination -Force | Out-Null
        & $Supabase storage cp "ss://$StorageBucket" $StorageDestination --recursive --linked --experimental
    }
}
finally {
    Pop-Location
}

$files = Get-ChildItem -Path $Destination -File -Recurse | ForEach-Object {
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
    [ordered]@{
        path = $_.FullName.Substring($Destination.Length + 1)
        size = $_.Length
        sha256 = $hash.Hash
    }
}
[ordered]@{
    format = "aerocontrol-supabase-backup-v1"
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    destination = $Destination
    bucket = $StorageBucket
    files = @($files)
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Destination "manifest.json") -Encoding utf8

Write-Output "Supabase backup created: $Destination"
