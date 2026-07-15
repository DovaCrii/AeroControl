# Tasks — Phase 3: HTMX Integration

## Task 1: HTMX Base Setup
- [x] 1.1 Add HTMX CDN script + CSRF config in base.html
- [x] 1.2 Add modal skeleton in base.html (hidden Bootstrap modal)
- [x] 1.3 Add `hx-headers` config for CSRF
- [x] 1.4 Update settings to include needed context processors (csrf already present)

## Task 2: Live Search
- [x] 2.1 Create `generic/_search_input.html` partial with hx-trigger
- [x] 2.2 Create `generic/_table_body.html` partial (table rows fragment)
- [x] 2.3 Create `SearchMixin` update in core/views.py (returns partial on hx-request)
- [x] 2.4 Update `generic/list.html` — wrap table in #table-wrapper, use partials
- [x] 2.5 Update `generic/_pagination.html` — add hx-* attributes
- [x] 2.6 Update `compliance/document_list.html` — convert search to HTMX
- [x] 2.7 Create `compliance/_document_rows.html` partial

## Task 3: Modal Create Forms
- [x] 3.1 Create view mixin that returns form partial for hx-get
- [x] 3.2 Create `generic/_form_content.html` partial (form without layout chrome)
- [x] 3.3 Wire up "New" buttons with hx-get/hx-target
- [x] 3.4 Support hx-post on form submit with success/error handling
- [x] 3.5 Test modal create on at least one model (Aircraft)

## Task 4: Dynamic Pagination
- [x] 4.1 Update `generic/list.html` to include pagination inside #table-wrapper
- [x] 4.2 Update `_pagination.html` links with hx-get + hx-target
- [x] 4.3 Ensure hx-push-url updates browser URL

## Task 5: Alert Badge Auto-Refresh
- [x] 5.1 Create `core/views.py` AlertCountPartial view
- [x] 5.2 Create `core/_alert_badge.html` partial
- [x] 5.3 Update sidebar in base.html to use hx-trigger="every 60s"
- [x] 5.4 Add URL route in config/urls.py

## Review Workload Forecast
- Estimated changed lines: ~350
- Files touched: ~15
- 400-line budget risk: Medium
- Chained PRs recommended: No
- Decision: single change
