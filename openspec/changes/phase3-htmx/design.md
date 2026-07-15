# Design — Phase 3: HTMX Integration

## Architecture

### HTMX Setup (base.html)
```
<head>
  <script src="https://unpkg.com/htmx.org@2.x"></script>
  <script>
    document.body.addEventListener('htmx:configRequest', (e) => {
      e.detail.headers['X-CSRFToken'] = '{{ csrf_token }}';
    });
  </script>
</head>
```

### Template Fragments
Each list view gets a partial template for the table body:

| Template | Purpose |
|----------|---------|
| `_search_input.html` | Reusable search input with hx-trigger="keyup changed delay:300ms" |
| `_table_rows.html` | Per-list table rows fragment (swap target for live search) |
| `_modal.html` | Modal skeleton in base.html |
| `alert_badge.html` | Alert count fragment for badge refresh |

### Live Search Flow
```
User types → hx-get="/path/?q=term" 
           → hx-target="#table-body" 
           → hx-push-url="true"
           → hx-trigger="keyup changed delay:300ms, search"
           → Server returns HTML fragment
           → Fragment swaps into #table-body
```

### Modal Flow
```
Click "New" → hx-get="/path/new/" 
            → hx-target="#modal-content"
            → hx-trigger="click"
            → Opens modal with form loaded via AJAX
            → Submit → hx-post="/path/new/"
                     → On success: close modal, refresh list
                     → On error: swap errors into modal
```

### Alert Badge Refresh
```
Sidebar badge → hx-get="/alerts/count/"
              → hx-trigger="every 60s"
              → hx-target="this"
              → hx-swap="outerHTML"
```

### Views
New API-like endpoints that return HTML fragments:

| View | URL | Returns |
|------|-----|---------|
| AlertCountPartial | GET `/alerts/count/` | `<span>` with count |
| TableSearchMixin | Reusable mixin for list views | Filtered queryset + partial template |

### Templates Modified
| Template | Change |
|----------|--------|
| `base.html` | Add HTMX script, CSRF config, modal skeleton |
| `generic/list.html` | Add live search, wrap table in swap target, HTMX pagination |
| `generic/_pagination.html` | Add hx-* attributes to page links |
| `generic/form.html` | Support modal form context |
| `compliance/document_list.html` | Replace search form with live search |
| `operations/permission_list.html` | Add live search |
| `templates/generic/_table_body.html` | New — table rows fragment |

### New Partials
| File | Content |
|------|---------|
| `templates/generic/_search_input.html` | HTMX-powered search input |
| `templates/generic/_modal.html` | Bootstrap modal skeleton |
| `templates/compliance/_alert_badge.html` | Alert count badge fragment |

## Security
- CSRF token injected via htmx:configRequest event
- All HTMX endpoints require login (existing LoginRequiredMixin)
- Modal POST endpoints validate same as regular forms
