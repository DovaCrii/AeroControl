# Backend plan: local-first

## Decision

AeroControl will be operated locally on the personal notebook while it is a
single-user application. The Django backend, SQLite database and private
documents remain outside the Git repository under `AeroOpsDesk_Data`. GitHub
contains code, migrations, documentation and synthetic examples only.

This is still a real backend: the browser talks to Django through
`127.0.0.1:8000`. It does not need to be deployed to the public Internet.

## Environments

| Environment | Data | Purpose |
| --- | --- | --- |
| Local notebook | Private operational data | Daily personal use |
| Supabase Free | Synthetic/anonymized data only | Database and CLI exercises |
| Render Free | Synthetic/anonymized data only | Demo and deployment smoke tests |
| Paid production | Private data, after controls are ready | Future multi-device or multi-user use |

Render Free is not the data-of-record: free web services sleep and have an
ephemeral filesystem. Supabase Free is useful for a prototype but does not
replace an independent backup and restore process.

## Delivery sequence

1. Keep the local SQLite workflow stable and finish the current CI/quality PRs.
2. Use `scripts/backup-local.ps1` to create snapshots outside the repository.
3. Verify every snapshot with `scripts/verify-local-backup.ps1` and perform a
   restore drill using a disposable database. The synthetic drill is now
   implemented by `scripts/restore-local.ps1`.
4. Publish only the anonymized snapshot to Supabase/Render for remote testing.
5. Move private data to a paid, backed-up service only after the production
   security and restore gates pass.

## Production gate

Do not upload real antecedents until all of the following are true:

- backup and restore have been tested end to end;
- documents are in a private bucket or private disk, never public URLs;
- secrets are stored outside GitHub and rotated;
- MFA, access roles, retention and incident procedures are defined;
- PostgreSQL migration has a verified rollback path.

The Supabase CLI remains optional for the remote prototype. It can be run with
`npx --yes supabase`; no global installation or repository-stored credentials
are required.
