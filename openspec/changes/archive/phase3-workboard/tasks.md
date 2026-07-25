# Tasks — Phase 3: Workboard & UX

## Task 1: Kanban Board View
- [x] 1.1 Create workboard/kanban.html template (board layout with columns)
- [x] 1.2 Create KanbanBoardView in workboard/views.py
- [x] 1.3 Create _board.html, _column.html, _card.html fragment templates
- [x] 1.4 Update workboard/urls.py with board route
- [x] 1.5 Add sidebar link to board view (update base.html)

## Task 2: Drag-and-Drop with SortableJS
- [x] 2.1 Add SortableJS + HTMX integration in kanban.html
- [x] 2.2 Create MoveTaskView in workboard/views.py
- [x] 2.3 Add URL for move endpoint
- [x] 2.4 Implement server-side reorder logic
- [x] 2.5 Wire HX-Trigger for board refresh after drop

## Task 3: Priority Labels & Filters
- [x] 3.1 Add priority badge colors to _card.html
- [x] 3.2 Create _filters.html with operator + priority selects
- [x] 3.3 Create BoardFilterPartial view
- [x] 3.4 Wire HTMX filter reload

## Task 4: Quick-Add Task
- [x] 4.1 Create _quick_form.html inline form fragment
- [x] 4.2 Create QuickTaskCreate view
- [x] 4.3 Wire + button to load form via HTMX
- [x] 4.4 On submit: create task, refresh column

## Review Workload Forecast
- Estimated changed lines: ~400
- Files touched: ~10
- 400-line budget risk: Medium
- Chained PRs recommended: No
