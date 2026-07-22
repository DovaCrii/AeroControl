$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $Uv) { $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $Uv)) { throw "uv is required. Install it from https://docs.astral.sh/uv/" }

& $Uv run python manage.py check
& $Uv run python manage.py makemigrations --check --dry-run
& $Uv run pytest
& $Uv run ruff check .
& $Uv run ruff format --check .
& $Uv run bandit -q -c pyproject.toml -r apps config
& $Uv run pip-audit
