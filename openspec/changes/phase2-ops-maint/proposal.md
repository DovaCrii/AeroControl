# Phase 2 — Operations & Maintenance

## Problem
The Operations and Maintenance apps have basic models but no user-facing workflow for managing flight permissions through their lifecycle, logging flight records with proper context, tracking status changes, or viewing a calendar of upcoming events.

## Proposed Scope
1. Flight permission workflow: detail view with status transitions (approve/deny/complete)
2. Flight record management with direct operator/aircraft links
3. Automatic status change history for permissions and maintenance records
4. Calendar view showing maintenance schedules and flight dates
5. Operations and maintenance-specific templates with meaningful columns and actions

## Non-goals
- Drag-and-drop Kanban
- Excel import
- REST API layer
- Email notifications
