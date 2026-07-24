# Run one AeroControl management command as a scheduled job.
#
# Registered by scripts/schedule_tasks.ps1. Kept separate so the scheduler
# invokes a stable entry point (and so the command's exit code reaches the Task
# Scheduler, which reports the "last result" you see in its UI).
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "generate_alerts",
        "send_alert_digest",
        "backup",
        "send_executive_report"
    )]
    [string]$Command,
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

# Scheduled tasks start with a bare environment, so load the operator's .env
# (KEY=VALUE lines; # comments and blanks ignored) before running.
if ($EnvFile) {
    if (-not (Test-Path -LiteralPath $EnvFile)) { throw "Env file not found: $EnvFile" }
    foreach ($line in Get-Content -LiteralPath $EnvFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $separator = $trimmed.IndexOf("=")
        if ($separator -lt 1) { continue }
        $key = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim().Trim('"')
        Set-Item -Path "env:$key" -Value $value
    }
}

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $uv)) { throw "uv is required. Install it from https://docs.astral.sh/uv/" }

& $uv run python manage.py $Command
if ($LASTEXITCODE -ne 0) {
    throw "Scheduled job failed: $Command (exit code $LASTEXITCODE)"
}
