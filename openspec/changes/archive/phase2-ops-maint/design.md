# Design — Phase 2: Operations & Maintenance

## Architecture

### Status History via Signals
Create `apps/core/signals.py` with a generic handler:

```python
def track_status_changes(sender, instance, **kwargs):
    if not instance.pk:
        return  # new object, no status change yet
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if old.status != instance.status:
        # Create history entry based on sender's history model
```

Connect signals in each app's `apps.py`.

### Permission History Model
Add to operations/models.py:
```python
class PermissionHistory(BaseModel):
    permission = ForeignKey(FlightPermission, related_name="history")
    previous_status = CharField(max_length=20)
    new_status = CharField(max_length=20)
    changed_by = CharField(max_length=150)
    notes = TextField(blank=True)
```

### Views

| View | URL | Description |
|------|-----|-------------|
| FlightPermissionDetail | `/operations/permissions/{pk}/` | Full detail + actions |
| FlightPermissionApprove | POST `.../approve/` | Set status=approved |
| FlightPermissionDeny | POST `.../deny/` | Set status=denied |
| FlightPermissionComplete | POST `.../complete/` | Set status=completed |
| FlightRecordDetail | `/operations/records/{pk}/` | Full detail |
| FlightRecordDelete | POST `.../delete/` | Soft delete |
| MaintenanceRecordDetail | `/maintenance/records/{pk}/` | Full detail + actions |
| MaintenanceStart | POST `.../{pk}/start/` | Set status=in_progress |
| MaintenanceComplete | POST `.../{pk}/complete/` | Set status=completed |
| CalendarView | `/calendar/` | Monthly calendar |

### Status Transition Validation
Base class or mixin:
```python
class StatusTransitionView(LoginRequiredMixin, View):
    model = None
    target_status = None
    valid_from_statuses = []

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk)
        if obj.status not in self.valid_from_statuses:
            messages.error(request, f"Cannot transition from {obj.status}")
            return redirect(obj)
        # ... perform transition
```

### Calendar
- Simple view that groups querysets by month
- Template with date headers and event cards
- Navigation: previous/next month
- URL: `/calendar/?month=2026-07`

## Templates
- `operations/permission_detail.html` — detail + actions + history + flight records
- `operations/permission_list.html` — with status badge and filters
- `operations/flightrecord_detail.html` — record detail
- `operations/flightrecord_form.html` — record form
- `maintenance/record_detail.html` — detail + actions + history
- `maintenance/record_list.html` — with status badge
- `core/calendar.html` — monthly calendar view
- `core/calendar_day.html` — day event list (included)

## Security
- LoginRequiredMixin on all views
- Status transition views are POST-only (CSRF protected)
- No direct status editing via GET
