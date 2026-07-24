# Local backup runbook

The local snapshot is the source-of-truth backup for personal use. The
destination must be outside the repository and preferably on an encrypted
external disk or a second protected location.

## Create a snapshot

```powershell
$env:AEROCONTROL_BACKUP_ROOT = 'E:\AeroControlBackups'
powershell -ExecutionPolicy Bypass -File .\scripts\backup-local.ps1
```

The snapshot contains the SQLite backup, its manifest and a copy of
`DOCUMENTS_DIR`. The script refuses to write inside the repository.

## Verify a snapshot

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-local-backup.ps1 `
  -Snapshot 'E:\AeroControlBackups\aerocontrol_YYYYMMDD_HHMMSS'
```

Verification checks that every copied file still has the expected size and
SHA-256 checksum.

## Restore to a disposable folder

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-local.ps1 `
  -Snapshot 'E:\AeroControlBackups\aerocontrol_YYYYMMDD_HHMMSS' `
  -DestinationRoot 'E:\AeroControlRestoreDrill\YYYYMMDD'
```

The restore script refuses to overwrite a destination unless `-Force` is
provided and never accepts a destination inside the repository or snapshot.

## Restore drill

Restore the SQLite file to a disposable path and point a temporary `.env` at
it. Copy the snapshot's `documents` directory to a temporary
`DOCUMENTS_DIR`, start Django, and confirm that a test record and its document
are readable. Never overwrite the working database during a drill.

Recommended cadence: after each meaningful data load, weekly during active
use, and before migrations or dependency upgrades. Keep at least three
verified snapshots on separate media.

## Schedule the weekly backup

After choosing the actual backup unit, register the task under the Windows
user that runs AeroControl:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-backup-task.ps1 `
  -DestinationRoot 'E:\AeroControlBackups' `
  -DayOfWeek Sunday `
  -At '18:00'
```

The registration script refuses a destination inside the repository. It is
safe to run again because it replaces the task with the same name.
