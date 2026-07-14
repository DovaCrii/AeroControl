# Tasks — Document Management & Alert System

## Task 1: Document Upload & Storage
- [x] 1.1 Create custom `upload_to` callable in compliance/models.py
- [x] 1.2 Add DOCUMENTS_ROOT to settings (from env)
- [x] 1.3 Create DocumentCreate view with file upload + extension/size validation
- [x] 1.4 Create DocumentList view with columns: Title, Type, Entity, Expiry, Current, Actions
- [x] 1.5 Create DocumentDetail view with file download link + version history
- [x] 1.6 Create compliance-specific templates for list/detail/form
- [x] 1.7 Update compliance/urls.py with new routes
- [x] 1.8 Add file download view (authenticated, no direct URL access)

## Task 2: Version Replacement
- [x] 2.1 Create DocumentReplace view (mark old, create new)
- [x] 2.2 Create replacement form template
- [x] 2.3 Add "Replace" button in document list and detail
- [x] 2.4 Wire URL patterns

## Task 3: Search/Filter on List Views
- [x] 3.1 Create SearchMixin in apps/core/views.py or as a mixin
- [x] 3.2 Add search_fields to all existing ListViews
- [x] 3.3 Add search bar and is_active filter to generic/list.html
- [x] 3.4 Add Q-object search logic to RegistryList, ComplianceList, etc.

## Task 4: Alert Generation
- [x] 4.1 Create management command `generate_alerts.py`
- [x] 4.2 Implement expiry checks for Qualification, Document, AlertRule
- [x] 4.3 Implement duplicate detection (skip if unresolved alert exists)
- [x] 4.4 Log generation summary

## Task 5: Alert List & Resolution
- [x] 5.1 Enhance AlertList view with filter/search (by resolved, by entity)
- [x] 5.2 Create alert-specific list template with meaningful columns
- [x] 5.3 Create AlertResolve view (POST, mark is_resolved=True)
- [x] 5.4 Add unresolved alert badge to sidebar in base.html

## Task 6: Document Delete (soft)
- [x] 6.1 Create DocumentDelete view (set is_active=False, not actual file delete)
- [x] 6.2 Wire URL and add Delete button in list with confirmation

## Review Workload Forecast
- Estimated changed lines: ~600
- Files touched: ~15
- 400-line budget risk: **High**
- Chained PRs recommended: **No** (single cohesive feature)
- Decision needed before apply: **Use size:exception**
