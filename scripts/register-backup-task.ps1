param(
    [Parameter(Mandatory = $true)]
    [string]$DestinationRoot,
    [string]$TaskName = "AeroControl-LocalBackup",
    [ValidateSet("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
    [string]$DayOfWeek = "Sunday",
    [ValidatePattern("^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$At = "18:00"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backupScript = Join-Path $repoRoot "scripts\backup-local.ps1"
if (-not (Test-Path -LiteralPath $backupScript)) {
    throw "Backup script not found: $backupScript"
}

$repoFull = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
$destinationFull = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
if ($destinationFull.Equals($repoFull, [StringComparison]::OrdinalIgnoreCase) -or
    $destinationFull.StartsWith("$repoFull\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "The backup destination must be outside the repository."
}

$runAt = [datetime]::ParseExact($At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$escapedScript = $backupScript.Replace('"', '\"')
$escapedDestination = $destinationFull.Replace('"', '\"')
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$escapedScript`" -DestinationRoot `"$escapedDestination`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $runAt

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "AeroControl local database and documents backup" -Force | Out-Null
Write-Host "Scheduled task registered: $TaskName ($DayOfWeek at $At)"
Write-Host "Backup destination: $destinationFull"
