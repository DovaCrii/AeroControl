# AeroOps Desk Architecture

## Current: Modular Django Monolith

AeroOps Desk is a modular Django monolith. Each domain is an installed application with its own models, forms, views, URLs, and admin registrations.

```
repo/
├── apps/
│   ├── core/          # BaseModel, shared behavior, backups
│   ├── registry/      # Cost centers, aircraft, operators
│   ├── compliance/    # Documents, alerts, expirations
│   ├── operations/    # Flight permissions, flight records
│   ├── maintenance/   # Maintenance records, history
│   ├── workboard/     # Kanban boards, stages, tasks
│   └── dashboard/     # Read-only aggregation view
├── config/            # Django settings (base/dev/prod)
├── templates/         # Bootstrap 5 templates
├── static/            # CSS, JS, images
└── scripts/           # PowerShell automation
```

### Key Decisions

- **`apps.core.BaseModel`** — UUID primary keys, `created_at`/`updated_at` timestamps, `is_active` for archival (never delete), `notes` for optional context.
- **Settings split** — `base.py` (shared), `dev.py` (DEBUG, SQLite), `prod.py` (production-ready). Env vars via `python-decouple`.
- **Data isolation** — SQLite database + documents + backups live under `D:\I+D\AeroOpsDesk_Data\`, outside the repo. Paths injected via `.env`.
- **ContentTypes for documents** — Documents use a generic foreign key so they attach to Aircraft, Operator, Assignment, etc. without coupling.
- **Conservative deletes** — `PROTECT` on all operational ForeignKeys. Entities are archived (`is_active=False`), never deleted, preserving audit trail.
- **Bootstrap 5** — Responsive layout with navy (#1B2A4A), turquoise (#2EC4B6), light (#F8F9FA) palette.

## Future: Backend / Frontend Separation

The current Django Template + Bootstrap architecture is intentionally monolithic for rapid iteration. The growth path preserves the backend while decoupling the frontend:

```
Phase 1 (current)
  Django views → Bootstrap 5 templates
  └── Fast to build, easy to iterate

Phase 2 (API layer)
  Django REST Framework serializers + viewsets
  └── Same models, same business logic
  └── No frontend changes yet — DRF browsable API alongside templates

Phase 3 (SPA frontend)
  Vue.js 3 or React SPA consuming DRF API
  └── Templates become static files served by Django or a separate host
  └── BFF (Backend for Frontend) layer if needed

Phase 4 (production)
  uWSGI/Daphne + PostgreSQL + Redis cache + CDN for static assets
  └── SQLite suitable for single-user; migrate to PostgreSQL for multi-user
```

### Separation Principles

1. **Business logic stays in models** — Fat models, thin views. This makes the logic reusable whether the consumer is a Django template or a REST API.
2. **Do NOT add business logic to templates or serializers** — Both are presentation layers.
3. **API versioning from day one of DRF** — Even if the only consumer is the SPA, prefix `/api/v1/`.
4. **No premature abstraction** — The monolith IS the abstraction until the SPA proves valuable. Do not abstract "in case of separation."

## Directory Anatomy

| Path | Purpose |
|------|---------|
| `apps/*/models.py` | Domain models and business logic |
| `apps/*/views.py` | Class-based views (generic CRUD) |
| `apps/*/forms.py` | Crispy Forms for each model |
| `apps/*/urls.py` | URL patterns per app |
| `templates/base.html` | Main layout with sidebar + navbar |
| `templates/generic/` | Reusable list/detail/form templates |
| `templates/registration/` | Login template |
| `static/css/app.css` | Custom styles (navy/turquoise theme) |
| `config/settings/` | Split Django settings |
| `scripts/` | PowerShell automation |
| `prompts/` | OpenCode continuation prompts |
