# Spec — Phase 3: Workboard & UX

## Functional Requirements

### F1: Kanban Board View
- URL: `/workboard/` shows all tasks grouped by `KanbanStage`
- Each stage is a column with the stage name + task count header
- Tasks are rendered as cards with: title, priority badge, assigned operator, due date
- Cards are sorted by `order` field within each stage
- Default view loads the first active board (or a board selector)

### F2: Drag-and-Drop
- Drag a task card from one stage column to another via SortableJS
- On drop: HTMX POST to `/workboard/tasks/{pk}/move/` with `{stage_id, new_order}`
- Server updates the task's stage and order, reorders siblings
- Optimistic UI update via SortableJS `onEnd`

### F3: Priority Labels
- Task cards show colored badge:
  - Low: gray/outline
  - Medium: blue
  - High: orange
  - Critical: red

### F4: Filters
- Dropdown filters above the board:
  - By operator (select from Operator list)
  - By priority (Low/Medium/High/Critical/All)
- Filtering triggers HTMX reload of the board content
- Board state (`board` query parameter) persists

### F5: Quick-Add Task
- "+" button at bottom of each stage column
- Opens inline form via HTMX (loads form fragment)
- On submit: creates task in that stage, refreshes column
- The quick-add form MUST preserve the active `board`, `operator`, and `priority`
  filters in its GET and POST requests. The task's `priority` field is distinct
  from the preserved filter value.
