# Spec — Document Management & Alert System

## Functional Requirements

### F1: Document Upload
- User can upload a document via a form at `/compliance/document/new/`
- Form fields: title, doc_type (select from DocumentType), entity type + entity ID (generic lookup), file (file upload), issue_date, expiry_date (if required by doc_type)
- File stored at `{DOCUMENTS_DIR}/{app_label}/{model_name}/{object_id}/{filename}`
- After upload, redirect to document list

### F2: Document List
- Table columns: Title, Type, Entity (linked), Expiry, Current version badge, Actions (View, Replace, Delete)
- Pagination (25 per page)
- Search by title, filter by doc_type, filter by is_current_version
- Link to download/view the file

### F3: Document Detail
- Shows all document fields, file download link, entity link
- Shows previous versions (other documents with same content_type + object_id where is_current_version=False)

### F4: Version Replacement
- On `/compliance/document/{pk}/replace/`:
  1. Mark current document as `is_current_version=False`
  2. Create new Document record with `is_current_version=True`, same content_type/object_id
  3. Upload new file
  4. Redirect to new document detail

### F5: Alert Generation Command
- `python manage.py generate_alerts`
- Checks: Qualification.expiry_date, Document.expiry_date (when doc_type.requires_expiry=True), FlightPermission.status
- Creates Alert records for items expiring within `AlertRule.days_before_expiry` days
- Does NOT create duplicate alerts for the same entity + rule combination if already unresolved
- Logs summary: "Generated N alerts, skipped M duplicates"

### F6: Alert List and Resolution
- Table: Entity type, Entity, Rule, Triggered, Expiry date, Actions
- Filter by is_resolved, by entity_type
- Button to mark as resolved
- Sidebar badge showing unresolved alert count

### F7: Search/Filter on Lists
- All list views get a search bar (text search on `name` or `title` field)
- All list views get `is_active` filter toggle
- Add `django-filters` or manual Q-object search

## Non-Functional
- Files stored outside repo (DOCUMENTS_DIR from .env)
- Only PDF, DOCX, XLSX, images allowed for upload (validate extension)
- File size limit: 20MB
