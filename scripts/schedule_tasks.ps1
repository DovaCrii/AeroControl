# Register AeroControl's daily jobs in the Windows Task Scheduler.
#
# Each job runs through `uv run python manage.py`, so it picks up the same
# environment as a manual run. Every execution is recorded as a JobRun row,
# which is how you tell afterwards whether the scheduled work actually ran.
#
# Example:
#   ./scripts/schedule_tasks.ps1 -EnvFile "C:\AeroControl_Data\.env"
#   ./scripts/schedule_tasks.ps1 -AlertsAt "06:30" -DigestAt "07:15" -BackupAt "22:00"
#   ./scripts/schedule_tasks.ps1 -WithCredentialNotice   # enable the optional LV-29 job
#   ./scripts/schedule_tasks.ps1 -Unregister
param(
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$AlertsAt = "06:00",
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$DigestAt = "07:00",
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$BackupAt = "21:00",
    # Weekly executive report (Bloque 6.2)
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$ExecutiveReportAt = "07:30",
    [ValidateSet("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
    [string]$ExecutiveReportDay = "Monday",
    # Month-end compliance close (LV-30). Runs daily and self-guards to the last
    # day of the month, so the time only sets when it fires that day.
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$MonthlyRecordsAt = "23:30",
    # Mid-month review deadline reminder (R6.5). Runs daily and self-guards to
    # the 15th, escalating any review still pending from last month.
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$MonthlyReviewDeadlineAt = "08:00",
    # Compliance snapshot (R7.7). Stores the day's totals so the report can
    # show a real trend. Late in the day, after the day's edits.
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$ComplianceSnapshotAt = "23:00",
    # Optional per-operator expiry notice (LV-29). Off by default; enable with
    # -WithCredentialNotice. -Unregister always removes it regardless.
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$CredentialNoticeAt = "07:30",
    [switch]$WithCredentialNotice,
    [string]$TaskPrefix = "AeroControl",
    # Optional .env consumed by the scheduled run. Scheduled tasks do not
    # inherit your interactive shell, so without this the jobs fall back to the
    # repo defaults and may not find the real database.
    [string]$EnvFile = "",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $PSScriptRoot "run-scheduled-job.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Job runner not found: $runner"
}
if ($EnvFile -and -not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

$jobs = @(
    @{ Name = "GenerateAlerts"; Command = "generate_alerts"; At = $AlertsAt; Weekly = $null
       Description = "Generate compliance alerts and their follow-up tasks" }
    @{ Name = "AlertDigest"; Command = "send_alert_digest"; At = $DigestAt; Weekly = $null
       Description = "Email expiry digests to cost center leads" }
    @{ Name = "Backup"; Command = "backup"; At = $BackupAt; Weekly = $null
       Description = "Create a verified database backup" }
    @{ Name = "ExecutiveReport"; Command = "send_executive_report"
       At = $ExecutiveReportAt; Weekly = $ExecutiveReportDay
       Description = "Email the weekly executive compliance report" }
    @{ Name = "MonthlyRecords"; Command = "check_monthly_records"; At = $MonthlyRecordsAt; Weekly = $null
       Description = "Month-end compliance reviews (daily; acts only on the last day of the month)" }
    @{ Name = "MonthlyReviewDeadline"; Command = "check_monthly_review_deadline"
       At = $MonthlyReviewDeadlineAt; Weekly = $null
       Description = "Escalate still-pending monthly reviews (daily; acts only on the 15th)" }
    @{ Name = "ComplianceSnapshot"; Command = "snapshot_compliance"
       At = $ComplianceSnapshotAt; Weekly = $null
       Description = "Store the day's compliance totals so the report can show a trend (R7.7)" }
    @{ Name = "CredentialNotice"; Command = "notify_expiring_credentials"; At = $CredentialNoticeAt; Weekly = $null
       Optional = $true
       Description = "Email each operator their DGAC expiries (<=30 days)" }
)

foreach ($job in $jobs) {
    $taskName = "$TaskPrefix-$($job.Name)"

    if ($Unregister) {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "Removed scheduled task: $taskName"
        }
        continue
    }

    # Optional jobs (LV-29 credential notice) stay off unless explicitly asked.
    if ($job.Optional -and -not $WithCredentialNotice) {
        Write-Host "Skipping optional task: $taskName (enable with -WithCredentialNotice)"
        continue
    }

    $escapedRunner = $runner.Replace('"', '\"')
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$escapedRunner`" -Command $($job.Command)"
    if ($EnvFile) {
        $escapedEnv = ([IO.Path]::GetFullPath($EnvFile)).Replace('"', '\"')
        $arguments += " -EnvFile `"$escapedEnv`""
    }

    $runAt = [datetime]::ParseExact($job.At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $repoRoot
    if ($job.Weekly) {
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $job.Weekly -At $runAt
        $cadence = "weekly on $($job.Weekly) at $($job.At)"
    }
    else {
        $trigger = New-ScheduledTaskTrigger -Daily -At $runAt
        $cadence = "daily at $($job.At)"
    }

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Description $job.Description -Force | Out-Null
    Write-Host "Scheduled task registered: $taskName ($cadence)"
}

if (-not $Unregister) {
    Write-Host ""
    Write-Host "Verify with:  Get-ScheduledTask -TaskName '$TaskPrefix-*'"
    Write-Host "Job history:  uv run python manage.py shell -c ""from apps.core.models import JobRun; print(*JobRun.objects.all()[:10], sep=chr(10))"""
}
