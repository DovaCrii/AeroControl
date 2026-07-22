# PostgreSQL readiness

The application remains SQLite-first for local operation. Before a multi-user
deployment, run the following commands:

    uv run python manage.py scale_readiness
    uv run python manage.py scale_readiness --json

The command reports the active database vendor, connection health and pending
migrations. It always marks rollback as required because changing the database
backend is an operational migration, not a settings-only change.

Migration sequence:

1. Create a verified SQLite backup and preserve its manifest/checksum.
2. Provision PostgreSQL with the target encoding, timezone and least-privilege
   application role.
3. Apply migrations to an empty PostgreSQL schema.
4. Load a rehearsed export/import copy and reconcile record counts.
5. Run the full test and health-check suite against PostgreSQL.
6. Switch database configuration to PostgreSQL only after the rehearsal passes.
7. Keep the SQLite backup and a documented rollback window.

No production database is changed by scale_readiness.
