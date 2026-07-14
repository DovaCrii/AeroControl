# AeroOps Desk — Project Plan

## Phase 0: Foundation ✅ (Current)
- [x] Django project scaffold (config/, manage.py, .env, .gitignore)
- [x] 7 Django apps (core, registry, compliance, operations, maintenance, workboard, dashboard)
- [x] BaseModel with UUID, timestamps, archival pattern
- [x] Settings split (base, dev, prod) with python-decouple
- [x] Data directory isolated at D:\I+D\AeroOpsDesk_Data\
- [x] All models, migrations, admin registrations
- [x] Bootstrap 5 responsive layout with navy/turquoise theme
- [x] Login/authentication scaffolding
- [x] PowerShell automation scripts (setup, run, backup, verify)
- [x] Initial git repository on `main` branch

## Phase 1: Core CRUD & Polish
- [ ] Complete CRUD views for all models (list, detail, create, update) ✅ basic, needs polish
- [ ] Document upload & version replacement UI
- [ ] File storage under D:\I+D\AeroOpsDesk_Data\documents\
- [ ] Document-to-entity associations (Aircraft, Operator, etc.)
- [ ] Expiry validation and alert generation
- [ ] Scheduled alert management command
- [ ] Table-level search and basic filtering
- [ ] Per-model list views with meaningful columns

## Phase 2: Operations & Maintenance
- [ ] Flight permission workflow (request → approved → completed)
- [ ] Flight record log with operator/aircraft tracking
- [ ] Maintenance schedule with status transitions
- [ ] Status change history with automatic tracking
- [ ] Calendar view for expirations and maintenance

## Phase 3: Workboard & Productivity
- [ ] Kanban drag-and-drop (SortableJS or similar)
- [ ] Task assignment to operators
- [ ] Priority labels and filtering
- [ ] Dashboard improvements with charts

## Phase 4: Data Import & Reporting
- [ ] Excel import for batch loading (aircraft, operators, documents)
- [ ] Normalized Chapter 1 import
- [ ] Global search (Django admin search + Haystack or similar)
- [ ] Word/Excel report generation
- [ ] Cross-entity validation (insurance ↔ aircraft ↔ operator ↔ permission)

## Phase 5: Architecture Evolution
- [ ] Django REST Framework API layer
- [ ] Frontend/backend separation (Vue.js or React SPA)
- [ ] PostgreSQL migration readiness
- [ ] Multi-user role-based access

## Milestones

| # | Milestone | Phase |
|---|-----------|-------|
| 1 | Server runs, login works, admin accessible | ✅ 0 |
| 2 | Load real CC, aircraft, operators | ✅ 0 |
| 3 | Document management + alerts | 1 |
| 4 | Permission and maintenance workflows | 2 |
| 5 | Kanban drag-and-drop | 3 |
| 6 | Import from Excel | 4 |
| 7 | REST API + SPA separation | 5 |
