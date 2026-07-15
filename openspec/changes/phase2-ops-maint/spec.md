# Spec — Phase 2: Operations & Maintenance

## Functional Requirements

### F1: Flight Permission Detail & Workflow
- Detail view at `/operations/permissions/{pk}/` shows:
  - All permission fields (number, operator, aircraft, CC, purpose, dates, location, status)
  - Associated flight records table
  - Action buttons depending on current status:
    - Requested → Approve, Deny
    - Approved → Complete
    - Denied/Completed → no actions (read-only)
  - Status history timeline
- Approve/Deny: POST to `/operations/permissions/{pk}/approve/` or `.../deny/`
  - Optional form field: notes/reason
- Complete: POST to `/operations/permissions/{pk}/complete/`

### F2: Flight Record Management
- List at `/operations/records/` with columns: Permission, Date, Pilot, Aircraft, Times
- Detail at `/operations/records/{pk}/` with full info
- Create form pre-fills permission, operator, aircraft from context
- Delete (soft) with confirmation

### F3: Permission List with Filters
- List at `/operations/permissions/` with columns: Number, Operator, Aircraft, Date, Status, Actions
- Filter by status (requested/approved/denied/completed)
- Filter by date range
- Search by permission number

### F4: Maintenance Record Detail & Workflow
- Detail view at `/maintenance/records/{pk}/` shows:
  - All maintenance fields
  - Status history timeline
  - Action buttons: Start (→ in_progress), Complete (→ completed)
  - Form for completion: actual completed_date, performed_by, cost, notes

### F5: Automatic Status History
- MaintenanceHistory auto-created when MaintenanceRecord.status changes
- FlightPermission gets a PermissionHistory model auto-created on status change
- Both via `save()` method override or Django signals

### F6: Calendar View
- `/operations/calendar/` shows a simple monthly calendar
- Events: FlightPermission.flight_date, MaintenanceRecord.scheduled_date
- Click on a date shows that day's events
- Simple Django template with date grouping (no JS calendar library initially)

## Non-Functional
- All views require login
- Status transitions validate current status (can't approve an already-approved permission)
- History is append-only, never editable
