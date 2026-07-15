# Phase 3 — HTMX Integration

## Problem
The app currently requires full page reloads for every action: search, filter, pagination, create, edit. This makes the UX feel sluggish for a desktop operations tool where users navigate lists constantly.

## Proposed Scope
1. Add HTMX via CDN + CSRF setup in base template
2. Live search on all list views (search-as-you-type, no submit button needed)
3. Modal-based create forms using HTMX (hx-get + hx-post)
4. Dynamic pagination via HTMX (page navigation without reload)
5. Alert badge auto-refresh every 60s via hx-trigger

## Non-goals
- Full SPA conversion
- Replacing all forms with modals
- Drag-and-drop Kanban (separate change)
- Removing existing search/form functionality

## Dependencies
- None — standalone enhancement
- HTMX 2.x via CDN (no pip package needed)
