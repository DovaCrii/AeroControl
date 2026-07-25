# Spec — Phase 3: HTMX Integration

## Functional Requirements

### F1: HTMX Base Setup
- HTMX 2.x loaded via CDN in `<head>` of base.html
- CSRF token configured via hx-headers (Django CSRF protection)
- hx-boost on main content area for smooth page transitions
- A shared `_search.html` partial template for search components

### F2: Live Search
- All list views with search input: input fires `hx-get` on `keyup` with 300ms delay
- Results update the table body via `hx-target`
- URL updates with `hx-push-url` for bookmarkable search
- Falls back to regular form submit if JS is disabled (progressive enhancement)

### F3: Modal Create Forms
- "New" buttons use `hx-get` to load form content into a modal
- Form submission via `hx-post` with `hx-swap` on success
- Validation errors swap into the modal, success closes modal and refreshes list
- Reusable modal skeleton in base.html

### F4: Dynamic Pagination
- Pagination links use `hx-get` + `hx-target="#table-wrapper"` + `hx-push-url`
- Table and pagination wrapped in a `<div id="table-wrapper">` for swap target

### F5: Alert Badge Auto-Refresh
- Alert count badge in sidebar polls `/api/alert-count/` every 60s via `hx-trigger`
- Lightweight endpoint returns just the count HTML fragment

## Non-Functional
- Zero new JS dependencies beyond HTMX
- All HTMX attributes use progressive enhancement (page works without JS)
- No breaking changes to existing templates
- CSRF protection maintained on all HTMX POST requests
