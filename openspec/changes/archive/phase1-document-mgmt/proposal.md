# Phase 1 — Document Management & Alert System

## Problem
The AeroOps Desk compliance app has models for Document, AlertRule, and Alert, but no user-facing UI for uploading documents, replacing versions, associating documents with entities (aircraft, operators, etc.), or generating alerts when credentials/permits expire.

## Proposed Scope
1. **Document upload workflow** — upload files, store them under the configured documents directory, associate with any entity via ContentType.
2. **Version replacement** — when a document is replaced, mark the previous version as `is_current_version=False`.
3. **Document list/detail** — table with meaningful columns (type, entity, expiry, actions).
4. **Alert generation command** — `manage.py generate_alerts` that checks all models with expiry dates and creates Alert records.
5. **Alert list/resolve UI** — view pending alerts, mark as resolved.
6. **Search/filter** on list views across all apps (basic text search + status filter).

## Non-goals
- Drag-and-drop Kanban (Phase 3)
- Excel import (Phase 4)
- REST API layer (Phase 5)
- Object-level permissions
