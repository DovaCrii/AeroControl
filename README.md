# AeroControl

Local-first operations desk for RPA/UAS teams. AeroControl centralizes fleet
registry, crew and qualification records, compliance documents, flight
permissions, maintenance, alerts, and an operational Kanban board in one Django
application.

> **Status:** alpha / active stabilization. Suitable for controlled local
> evaluation; production deployment still requires an operational backup,
> antivirus, retention, and access-control policy.

## What it provides

| Area | Current scope |
| --- | --- |
| Registry | Cost centers, aircraft, operators, assignments, qualifications |
| Compliance | Document metadata and uploads, document types, expiry alerts and rules |
| Operations | Flight-permission workflow, permission history, flight records |
| Maintenance | Scheduled/unscheduled records, status transitions and history |
| Workboard | Operational Kanban and list views, typed stages, labels, checklists, progress, priorities and operator assignment |
| Dashboard | Operational counts, upcoming expirations and work distribution |
| Localization | English and Spanish UI with a direct language switch |
| Security | Authenticated access, model permissions, CSV authorization, safe uploads |

## Technical architecture

- **Backend:** Python 3.12, Django 6.0, server-rendered templates.
- **UI:** Django templates, Bootstrap 5 via `crispy-bootstrap5`, HTMX for
  partial interactions, and project CSS in `static/css/app.css`.
- **Persistence:** SQLite by default. The database path is configured through
  `DB_PATH`; PostgreSQL is a future scale option, not the current default.
- **Storage:** uploaded documents are stored outside the repository through
  `DOCUMENTS_DIR`/`DOCUMENTS_ROOT`. Backups are copied to `BACKUPS_DIR`.
- **Operations:** PowerShell scripts wrap repeatable setup, run and backup
  commands. CI runs on GitHub Actions with `uv`, Ruff, pytest, Bandit and
  pip-audit.

### Repository layout

```text
aero-ops-desk/
├── apps/
│   ├── core/           # shared models, permissions, backups, tests
│   ├── registry/       # cost centers, aircraft, operators, assignments
│   ├── compliance/     # documents, alerts and retention/security hooks
│   ├── operations/     # flight permissions and flight records
│   ├── maintenance/    # maintenance records and status history
│   ├── workboard/      # Kanban workflow
│   └── dashboard/      # dashboard views
├── config/settings/    # base and development settings
├── templates/          # server-rendered UI
├── static/             # CSS and visual assets
├── scripts/            # setup.ps1, run.ps1 and backup.ps1
├── docs/               # technical documentation
├── openspec/           # specifications and change records
└── manage.py
```

## Local setup (Windows)

### Prerequisites

- Python 3.12.x
- PowerShell 7+
- Git
- [uv](https://docs.astral.sh/uv/)

Create a `.env` file at the repository root. The minimum values are:

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
DB_PATH=D:/I+D/AeroOpsDesk_Data/db/aero_ops.sqlite3
DOCUMENTS_DIR=D:/I+D/AeroOpsDesk_Data/documents
LOGS_DIR=D:/I+D/AeroOpsDesk_Data/logs
# Optional: executable available on PATH, for example clamscan
# DOCUMENTS_ANTIVIRUS_COMMAND=clamscan
```

Then run:

```powershell
git clone https://github.com/DovaCrii/aero-ops-desk.git
Set-Location aero-ops-desk
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\python.exe manage.py createsuperuser
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Open <http://127.0.0.1:8000/>. The setup script installs locked dependencies,
compiles translations, applies migrations, initializes standard roles, and
creates the initial document types and alert rule.

## Operational commands

Use the project interpreter (`uv run ...` or `.\.venv\Scripts\python.exe ...`):

```powershell
# Application checks
uv run python manage.py check
uv run python manage.py check --deploy

# Tests and quality gates
uv run pytest --cov=apps --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run bandit -q -c pyproject.toml -r apps config
uv run pip-audit

# Backup and integrity verification
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
uv run python manage.py verify_backup <path-to-backup.sqlite3>
uv run python manage.py restore_backup <backup.sqlite3> <destination.sqlite3>

# Document retention (dry-run first; deletion requires --execute)
uv run python manage.py cleanup_documents --older-than-days 3650
uv run python manage.py cleanup_documents --older-than-days 3650 --execute
```

Backups include a JSON manifest with source, timestamp, size, and SHA-256. The
restore command verifies that manifest before copying and refuses to overwrite
an existing destination unless `--force` is supplied.

## Security boundaries

The unauthenticated GET endpoint /health/ reports database and document-storage
dependency status as JSON (HTTP 200 when healthy, 503 when degraded) for local
monitors and reverse proxies.

Each response also carries an X-Request-ID correlation header. Request
completion and failure events are written as JSON lines to LOGS_DIR with method,
path, status code and duration, without recording request bodies or credentials.
Authenticated mutating requests are also stored append-only as AuditEvent records
and can be reviewed from Django Admin.

Authenticated users can search permitted operational records from /search/.
The search never returns entities for which the user lacks a view permission.

Cost centers support a validated CSV import at /registry/costcenter/import/,
aircraft at /registry/aircraft/import/, and operators at
/registry/operator/import/.
The format is code,name; existing codes are rejected, previews show row errors,
and applied batches can be reverted logically from the batch action.
Each import screen also exposes a CSV template download compatible with Excel.
The Kanban list also provides a filtered CSV operational report at
/workboard/reports/tasks.csv.
It also provides a native XLSX report at /workboard/reports/tasks.xlsx with
freeze panes, filters and readable column widths.
The Word version is available at /workboard/reports/tasks.docx.

A read-only API contract is available at /api/v1/workboard/tasks/. It requires
authentication and the Kanban task view permission, supports the existing
filters and returns bounded page/page_size results.
Task updates use PATCH at /api/v1/workboard/tasks/<uuid>/ and require the
Kanban task change permission; unsupported fields and cross-board stages are
rejected.

Before evaluating PostgreSQL, run scale_readiness and follow
docs/postgresql-readiness.md. The command is read-only and does not switch or
modify the active database.

- All operational pages require authentication and model-level view/change
  permissions; CSV export uses the same authorization boundary.
- Uploads allow only PDF, DOCX, XLSX, PNG, JPG and JPEG, enforce a 20 MB limit,
  validate the file signature, normalize the generated path, and write through
  a temporary file before replacement.
- Antivirus scanning is an integration point, enabled with
  `DOCUMENTS_ANTIVIRUS_COMMAND`; it must point to an installed executable.
- SQLite and uploaded files are local resources. They are **not** automatically
  replicated or encrypted by the application. Backups and access to the data
  directory remain an operator responsibility.

## Delivery status and next technical priorities

Completed stabilization includes bilingual UI, dark-theme contrast fixes,
operational form feedback, permission enforcement, document upload hardening,
backup manifests, restoration verification, and regression coverage.

### Kanban operational flow

The board view is available at /workboard/ and the filterable list view at
/workboard/list/. Stages are the source of truth for state; legacy stages remain
Personalized. Labels are scoped to a board and tasks support ordered checklists
with calculated progress. Task details open in a side panel for review/editing,
while archive actions are reversible and drag-and-drop is disabled when active
filters would make ordering ambiguous.

The next priorities are tracked in [`BACKLOG.md`](BACKLOG.md): accessibility
and responsive navigation, structured logs/health checks, CSP and asset
hardening, administrative audit history, validated imports/reports, and a
planned PostgreSQL/API path only when multi-user scale justifies it.

## License

MIT. See [`LICENSE`](LICENSE).
