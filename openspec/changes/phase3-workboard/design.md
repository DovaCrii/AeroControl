# Design — Phase 3: Workboard & UX

## Architecture

### New Views

| View | URL | Method | Description |
|------|-----|--------|-------------|
| KanbanBoardView | `/workboard/` | GET | Main board view with columns + cards |
| MoveTaskView | `/workboard/tasks/{pk}/move/` | POST | Update stage + order via HTMX |
| BoardFilterPartial | `/workboard/_board/` | GET | Board content fragment for HTMX reload |
| QuickTaskCreate | `/workboard/tasks/quick/` | GET, POST | Load and submit quick-add task form from a column |
| BoardSelector | `/workboard/_boards/` | GET | Board selector dropdown |

### New Templates

| Template | Purpose |
|----------|---------|
| `workboard/kanban.html` | Main board layout (extends base.html with no sidebar content shift) |
| `workboard/_board.html` | Board columns + cards fragment (HTMX swap target) |
| `workboard/_column.html` | Single stage column |
| `workboard/_card.html` | Single task card |
| `workboard/_quick_form.html` | Quick-add form fragment |
| `workboard/_filters.html` | Filter bar fragment |
| `workboard/_board_selector.html` | Board switcher |

### Drag-and-Drop Flow

```
User drags card from Col A to Col B →
  SortableJS onEnd fires →
  HTMX POST /workboard/tasks/{id}/move/ with {stage_id, new_order} →
  Server:
    1. Updates task.stage = stage_id
    2. Re-orders sibling tasks in old_stage and new_stage
    3. Returns 204 + HX-Trigger: board-refresh →
  Client: htmx:afterOnLoad catches HX-Trigger →
    GET /workboard/_board/ (refreshes all columns)
```

### Filter Flow

```
User selects operator/priority →
  hx-get="/workboard/_board/?operator=X&priority=Y" →
  hx-target="#kanban-board" →
  hx-push-url="true" (preserves filter in URL) →
  Server returns filtered board fragment
```

### Quick-Add Filter Flow

```
User clicks + Add →
  GET /workboard/tasks/quick/?stage_id=S&board=B&operator=O&priority=P →
  form includes hidden board/operator/filter_priority values →
  POST includes those values plus the independently selected task priority →
  Server creates the task and returns the affected filtered column
```

The canonical move payload is `{stage_id, new_order}`. `new_order` is the
SortableJS index and is the only documented order parameter.

### CSS Additions
- Column layout: CSS Grid or Flexbox with horizontal scroll
- Card styling: shadow, hover effect, priority border
- Column header with count badge
- Drop zone highlight during drag
