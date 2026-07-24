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
Invoke-Step "pytest" @("run", "pytest", "--cov=apps", "--cov-report=term-missing")
Invoke-Step "ruff check" @("run", "ruff", "check", ".")
Invoke-Step "ruff format --check" @("run", "ruff", "format", "--check", ".")
Invoke-Step "bandit" @("run", "bandit", "-q", "-c", "pyproject.toml", "-r", "apps", "config")
Invoke-Step "pip-audit" @("run", "pip-audit")

Write-Host "verify.ps1: all checks passed" -ForegroundColor Green
