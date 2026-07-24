param(
    [string]$DestinationRoot = $env:AEROCONTROL_BACKUP_ROOT
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}
if (-not (Test-Path $uv)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/"
}
if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    throw "Set AEROCONTROL_BACKUP_ROOT to a folder outside the repository before running this script."
}

$repoFull = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
$destinationFull = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
if ($destinationFull.Equals($repoFull, [StringComparison]::OrdinalIgnoreCase) -or
    $destinationFull.StartsWith("$repoFull\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "The backup destination must be outside the repository."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $destinationFull "aerocontrol_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

Push-Location $repoRoot
try {
    $dbEngine = (& $uv run python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])" | Select-Object -Last 1).Trim()
    if ($dbEngine -ne "django.db.backends.sqlite3") {
        throw "backup-local.ps1 supports the local SQLite workflow only; detected $dbEngine"
    }

    # Override the command destination so the database and its manifest are
    # created in the same snapshot as the document copy.
    $env:BACKUPS_DIR = $backupDir
    & $uv run python manage.py backup
    if ($LASTEXITCODE -ne 0) { throw "Database backup failed." }

    $documentsRoot = (& $uv run python manage.py shell -c "from django.conf import settings; print(settings.DOCUMENTS_ROOT)" | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($documentsRoot) -or -not (Test-Path $documentsRoot)) {
        throw "DOCUMENTS_ROOT does not exist: $documentsRoot"
    }
    $documentsFull = [IO.Path]::GetFullPath($documentsRoot).TrimEnd('\')
    if ($documentsFull.Equals($backupDir, [StringComparison]::OrdinalIgnoreCase) -or
        $documentsFull.StartsWith("$backupDir\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "The backup destination cannot be inside DOCUMENTS_ROOT."
    }
    if ($backupDir.Equals($documentsFull, [StringComparison]::OrdinalIgnoreCase) -or
        $backupDir.StartsWith("$documentsFull\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "The backup destination cannot be inside DOCUMENTS_ROOT."
    }

    $documentsDestination = Join-Path $backupDir "documents"
    Copy-Item -Path $documentsRoot -Destination $documentsDestination -Recurse -Force

    $manifestEntries = @()
    Get-ChildItem -Path $backupDir -File -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($backupDir.Length).TrimStart('\', '/') -replace '\\', '/'
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        $manifestEntries += [ordered]@{
            path = $relative
            size = $_.Length
            sha256 = $hash
        }
    }
    [ordered]@{
        format = "aerocontrol-local-backup-v1"
        created_at = (Get-Date).ToUniversalTime().ToString("o")
        database_backend = "sqlite3"
        source_documents = $documentsFull
        files = $manifestEntries
    } | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $backupDir "snapshot-manifest.json") -Encoding UTF8
    Write-Host "Local snapshot created: $backupDir"
}
finally {
    Pop-Location
    Remove-Item Env:BACKUPS_DIR -ErrorAction SilentlyContinue
}
