$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $Uv) { $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $Uv)) { throw "uv is required. Install it from https://docs.astral.sh/uv/" }

& $Uv sync --all-groups
& $Uv run python scripts/compile_translations.py
& $Uv run python manage.py migrate
& $Uv run python manage.py bootstrap_roles
& $Uv run python manage.py shell -c "from apps.compliance.models import DocumentType, AlertRule; DocumentType.objects.get_or_create(code='INS', defaults={'name':'Insurance'}); DocumentType.objects.get_or_create(code='MNT', defaults={'name':'Maintenance Certificate'}); DocumentType.objects.get_or_create(code='LIC', defaults={'name':'Operator License'}); AlertRule.objects.get_or_create(name='Qualification expiry', defaults={'entity_type':'Qualification','field_to_watch':'expiry_date','days_before_expiry':30})"
