# Backend plan: local-first

## Decision

AeroControl will be operated locally on the personal notebook while it is a
single-user application. The Django backend, SQLite database and private
documents remain outside the Git repository under `AeroOpsDesk_Data`. GitHub
contains code, migrations, documentation and synthetic examples only.

This is still a real backend: the browser talks to Django through
`127.0.0.1:8000`. It does not need to be deployed to the public Internet.

## Estado operativo — 24 julio 2026

- La base activa del PC está fuera del repositorio en
  `D:\I+D\AeroOpsDesk_Data-PC`.
- El snapshot verificado de referencia está en
  `D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\aerocontrol_20260724_112625`.
- La restauración al PC fue realizada en una carpeta de trabajo separada y la
  aplicación levanta correctamente con Django y SQLite.
- OneDrive conserva snapshots; no se usa como ubicación de la SQLite activa.
- El respaldo semanal queda registrado en el notebook; falta observar y
  documentar ejecuciones exitosas en el historial del Programador de tareas.
- En la revisión del PC del 24 de julio sólo se encontró un snapshot; B-01 debe
  generar y verificar dos snapshots adicionales antes de considerar completa
  la rotación mínima.
- No se ha subido SQLite, documentos, secretos ni `.env` a GitHub.

La evidencia detallada y el checklist para futuras sesiones están en
`docs/backend-follow-up.md`.

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
2. Use `scripts/backup-local.ps1` to create snapshots outside the repository;
   OneDrive may hold a second copy, but never the live SQLite used concurrently.
3. Verify every snapshot with `scripts/verify-local-backup.ps1` and perform a
   restore drill using a disposable database. The synthetic drill is now
   implemented by `scripts/restore-local.ps1`.
4. Publish only the anonymized snapshot to Supabase/Render for remote testing.
5. Move private data to a paid, backed-up service only after the production
   security and restore gates pass.

## Próximos bloques de avance

1. **B-01 — Operación de respaldos:** confirmar la tarea semanal, revisar su
   último resultado y conservar tres snapshots verificados.
2. **B-02 — Cambio seguro de equipo:** repetir notebook → OneDrive → PC con un
   snapshot nuevo y una restauración en carpeta limpia.
3. **B-03 — Calidad de datos:** resolver asignaciones de centro de costo y
   duplicados sólo con una fuente oficial confirmada.
4. **B-04 — Cumplimiento:** modelar habilitaciones DGAC, documentos versionados
   y alertas de vencimiento.
5. **B-05 — Compatibilidad operacional:** validar la relación
   operador–aeronave–habilitación antes de crear permisos confirmados.
6. **B-06 — Prototipo remoto:** usar Supabase CLI únicamente con datos
   sintéticos/anónimos y sin credenciales guardadas en el repositorio.
7. **B-07 — Escalamiento:** ejecutar ensayo PostgreSQL con backup, migración,
   verificación y rollback antes de evaluar acceso multiusuario.

Cada bloque se cierra con evidencia reproducible, pruebas, un commit pequeño y
un push a `codex/impeccable-ui-audit`.

## Production gate

Do not upload real antecedents until all of the following are true:

- backup and restore have been tested end to end;
- documents are in a private bucket or private disk, never public URLs;
- secrets are stored outside GitHub and rotated;
- MFA, access roles, retention and incident procedures are defined;
- PostgreSQL migration has a verified rollback path.

The Supabase CLI remains optional for the remote prototype. It can be run with
`npx --yes supabase`; no global installation or repository-stored credentials
are required. The CLI is not a reason to move private antecedents to Supabase
Free: its free tier is for synthetic tests only until retention, access,
backups and recovery have been validated.
