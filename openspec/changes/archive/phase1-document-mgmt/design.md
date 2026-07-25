# Design — Document Management & Alert System

## Architecture

### File Storage
- Use Django's `FileField` with a custom `upload_to` callable:
  `{doc_type_code}/{content_type.model}/{object_id}/{uuid}_{filename}`
- Storage root: `settings.DOCUMENTS_ROOT` from env variable `DOCUMENTS_DIR`
- Store the relative path in DB; full path constructed in views for download

### Document Replace Flow
```
GET /document/{pk}/replace/ → Form (same fields, file required)
POST /document/{pk}/replace/ →
  1. doc = get_object_or_404(Document, pk=pk)
  2. doc.is_current_version = False; doc.save()
  3. new_doc = Document.objects.create(
       content_type=doc.content_type, object_id=doc.object_id,
       doc_type=doc.doc_type, title=doc.title,
       file=uploaded_file, issue_date=..., expiry_date=...,
       is_current_version=True
     )
  4. redirect(new_doc.get_absolute_url())
```

### Alert Generation
- Management command in `apps/compliance/management/commands/generate_alerts.py`
- For each `AlertRule` (enabled, is_active):
  - Model class from `entity_type` (stored as "Qualification", "Document", etc.)
  - Look up records where `field_to_watch` (e.g., "expiry_date") <= today + days_before_expiry
  - Skip if unresolved Alert already exists for same entity + rule
  - Create Alert records
- Run via Windows Task Scheduler or `manage.py generate_alerts` on demand

### Search/Filter
- Create a reusable `SearchMixin(ListView)` that adds:
  - `search_fields = []` — override per view
  - `search_query = request.GET.get('q', '')`
  - Filters queryset with Q objects across `search_fields`
  - `is_active` filter toggle
- Keep it simple: Q object OR search (no django-filters dependency initially)

## Views & URLs

### New/Modified URLs (compliance app)
```
GET|POST  /compliance/document/new/          → DocumentCreate (with file upload)
GET       /compliance/document/{pk}/          → DocumentDetail
GET|POST  /compliance/document/{pk}/replace/  → DocumentReplace
GET|POST  /compliance/document/{pk}/delete/   → DocumentDelete (soft)
```

### Enhanced Alert URLs
```
GET       /compliance/alert/                   → AlertList (with filter/search)
POST      /compliance/alert/{pk}/resolve/      → AlertResolve
```

## Templates
- `compliance/document_list.html` — extends generic/list, custom columns
- `compliance/document_detail.html` — extends generic/detail, adds file download + version history
- `compliance/document_form.html` — extends generic/form, adds file input
- `compliance/document_replace.html` — simpler form for version replacement
- `compliance/alert_list.html` — extends generic/list, filter form

## Security
- All views require login (LoginRequiredMixin on base classes)
- File download: serve via Django view (not direct URL) — check login
- File extension validation in form clean()
