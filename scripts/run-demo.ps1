# Local demo server with an isolated data directory (not the real .env data).
# Used for live UI review; safe to delete. Data lives under the scratchpad.
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$Demo = $env:AEROCONTROL_DEMO_ROOT
if (-not $Demo) { $Demo = Join-Path $env:TEMP "aerocontrol-demo" }
$env:DJANGO_SETTINGS_MODULE = "config.settings.dev"
$env:SECRET_KEY = "demo-only-not-for-production-12345"
$env:DEBUG = "True"
$env:DB_PATH = Join-Path $Demo "db\demo.sqlite3"
$env:DOCUMENTS_DIR = Join-Path $Demo "docs"
$env:LOGS_DIR = Join-Path $Demo "logs"
$env:BACKUPS_DIR = Join-Path $Demo "backups"
uv run python manage.py runserver 127.0.0.1:8010
