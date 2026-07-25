# Tasks — Phase 2: Operations & Maintenance

## Task 1: PermissionHistory Model & Signal
- [x] 1.1 Create PermissionHistory model in operations/models.py
- [x] 1.2 Create `track_status_changes` signal handler in core/signals.py
- [x] 1.3 Connect signal in operations/apps.py and maintenance/apps.py
- [x] 1.4 Create and run migration
- [x] 1.5 Verify signal auto-creates history on status change

## Task 2: Flight Permission Detail & Workflow
- [x] 2.1 Create FlightPermissionDetailView with all fields, history timeline, actions
- [x] 2.2 Create StatusTransitionView mixin/base in core/views.py
- [x] 2.3 Create FlightPermissionApprove, Deny, Complete views (POST-only)
- [x] 2.4 Create operations/permission_detail.html template
- [x] 2.5 Create operations/permission_list.html with status badges and filters
- [x] 2.6 Update operations/urls.py with all new routes
- [x] 2.7 Add sidebar link to calendar

## Task 3: Flight Record Enhancement
- [x] 3.1 Create FlightRecordDetailView
- [x] 3.2 Create FlightRecordDeleteView (soft delete)
- [x] 3.3 Create operations/flightrecord_detail.html
- [x] 3.4 Create operations/flightrecord_form.html
- [x] 3.5 Add flight records table to permission detail template
- [x] 3.6 Update URLs

## Task 4: Maintenance Detail & Workflow
- [x] 4.1 Create MaintenanceRecordDetailView
- [x] 4.2 Create MaintenanceStart and MaintenanceComplete views (POST-only)
- [x] 4.3 Create maintenance/record_detail.html
- [x] 4.4 Create maintenance/record_list.html with status badges
- [x] 4.5 Update maintenance/urls.py

## Task 5: Calendar View
- [x] 5.1 Create CalendarView in operations/views.py (date-grouped events)
- [x] 5.2 Create core/calendar.html template with month navigation
- [x] 5.3 Add URL at /calendar/ in config/urls.py
- [x] 5.4 Add sidebar link to Calendar

## Task 6: Operations CRUD Completion
- [x] 6.1 Add search_fields to all ops list views
- [x] 6.2 Add filter by status to permission list
- [x] 6.3 Ensure all success_url redirect to proper list views

## Review Workload Forecast
- Estimated changed lines: ~650
- Files touched: ~20
- 400-line budget risk: High
- Chained PRs recommended: No (cohesive feature)
- Decision: size:exception
