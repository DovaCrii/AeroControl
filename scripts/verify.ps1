$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $Uv) { $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $Uv)) { throw "uv is required. Install it from https://docs.astral.sh/uv/" }

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Uv @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "verify.ps1: step failed ($Name), exit code $LASTEXITCODE"
    }
}

Invoke-Step "compile translations" @("run", "python", "scripts/compile_translations.py")
Invoke-Step "manage.py check" @("run", "python", "manage.py", "check")
Invoke-Step "manage.py check --deploy" @("run", "python", "manage.py", "check", "--deploy")
Invoke-Step "makemigrations --check" @("run", "python", "manage.py", "makemigrations", "--check", "--dry-run")
# Fase 3 del plan de mejora (2026-09-23): `-n auto` reparte la suite en un proceso
# por núcleo (`pytest-xdist`). Medido en el equipo de desarrollo, 20 núcleos:
# 3339 pruebas en 18m55s en serie y 2m57s en paralelo, con la misma cobertura.
# Cada worker crea su propia base de pruebas, así que no comparten filas; lo que
# sí compartirían es disco fuera de `tmp_path` y estado de proceso, y ninguna
# prueba de la suite actual depende de eso (dos corridas completas verdes).
Invoke-Step "pytest" @("run", "pytest", "-n", "auto", "--cov=apps", "--cov-report=term-missing")
Invoke-Step "ruff check" @("run", "ruff", "check", ".")
Invoke-Step "ruff format --check" @("run", "ruff", "format", "--check", ".")
Invoke-Step "bandit" @("run", "bandit", "-q", "-c", "pyproject.toml", "-r", "apps", "config")
Invoke-Step "pip-audit" @("run", "pip-audit")

# El último paso del CI (`Staging preflight`) no estaba aquí, y por eso el CI pudo
# estar en rojo semanas con este script en verde: la base de ese paso es un archivo
# vacío y `backup` necesita las tablas. Se corre igual que allá, pero **sobre una base
# temporal**: este script no puede migrar ni respaldar la base de desarrollo de quien
# lo corra. Las variables se restauran pase lo que pase.
$PreflightVars = @("DB_PATH", "DOCUMENTS_DIR", "LOGS_DIR", "BACKUPS_DIR")
$Saved = @{}
foreach ($Name in $PreflightVars) { $Saved[$Name] = [Environment]::GetEnvironmentVariable($Name) }
$Work = Join-Path ([IO.Path]::GetTempPath()) ("aerocontrol-preflight-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
try {
    New-Item -ItemType Directory -Force (Join-Path $Work "documents"), (Join-Path $Work "logs"), (Join-Path $Work "backups") | Out-Null
    $env:DB_PATH = Join-Path $Work "aero-ops.sqlite3"
    $env:DOCUMENTS_DIR = Join-Path $Work "documents"
    $env:LOGS_DIR = Join-Path $Work "logs"
    $env:BACKUPS_DIR = Join-Path $Work "backups"
    Invoke-Step "staging preflight: migrate" @("run", "python", "manage.py", "migrate", "--no-input")
    Invoke-Step "staging preflight: scale_readiness" @("run", "python", "manage.py", "scale_readiness", "--json")
    Invoke-Step "staging preflight: backup" @("run", "python", "manage.py", "backup")
    Invoke-Step "staging preflight: verify_backup" @("run", "python", "manage.py", "verify_backup")
}
finally {
    foreach ($Name in $PreflightVars) { [Environment]::SetEnvironmentVariable($Name, $Saved[$Name]) }
    if (Test-Path $Work) { Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue }
}

Write-Host "verify.ps1: all checks passed" -ForegroundColor Green
