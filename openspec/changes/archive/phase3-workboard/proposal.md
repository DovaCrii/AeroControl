# Phase 3 — Workboard & UX

## Problem
The Workboard app has all the underlying models (Board, Stage, Task) and CRUD views, but the main
interface is a flat list view (`generic/list.html`). There is no visual Kanban board, no
drag-and-drop, no priority indicators, and no way to filter by operator.

## Proposed Scope
1. Kanban board view: full-width columns per stage with task cards
2. Drag-and-drop between stages using SortableJS + HTMX
3. Priority labels with color-coded badges
4. Filter by operator and priority in the board view
5. Quick-add task form at the bottom of each column

## Non-goals
- Real-time collaboration (single-user desktop app)
- WIP limits on columns
- Swimlanes or custom card layouts
