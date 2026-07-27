# Local demo server with an isolated data directory (not the real .env data).
# Used for live UI review; safe to delete. Data lives under the scratchpad.
#
# Self-sufficient on purpose: migrates, seeds the standard roles and a fixed
# login on every run, so a fresh checkout (or a new session with no memory of
# a previous one) produces a working, known login without a one-off manual
# `createsuperuser`. Idempotent: safe to run repeatedly against the same data
# directory.
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
$env:EXPORTS_DIR = Join-Path $Demo "exports"

$Port = if ($env:AEROCONTROL_DEMO_PORT) { $env:AEROCONTROL_DEMO_PORT } else { "8010" }
# Never the real .env credentials, and never used for anything but this
# throwaway database -- fixed only so the same login works across sessions.
$DemoUser = if ($env:AEROCONTROL_DEMO_USER) { $env:AEROCONTROL_DEMO_USER } else { "demo" }
$DemoPassword = if ($env:AEROCONTROL_DEMO_PASSWORD) { $env:AEROCONTROL_DEMO_PASSWORD } else { "demo-review-only" }

foreach ($dir in @("$Demo\db", "$Demo\docs", "$Demo\logs", "$Demo\backups", "$Demo\exports")) {
    New-Item -ItemType Directory -Force $dir | Out-Null
}

uv run python manage.py migrate --no-input
uv run python manage.py bootstrap_roles

$seed = @"
from django.contrib.auth import get_user_model
User = get_user_model()
user, _ = User.objects.get_or_create(
    username='$DemoUser', defaults={'email': '$DemoUser@localhost'}
)
user.set_password('$DemoPassword')
user.is_staff = True
user.is_superuser = True
user.save()
"@
uv run python manage.py shell -c $seed

Write-Output "Demo login -> user: $DemoUser | password: $DemoPassword"
uv run python manage.py runserver "127.0.0.1:$Port"
