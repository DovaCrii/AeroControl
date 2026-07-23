# Frontend boundary decision

## Decision

Keep Django templates, HTMX and Bootstrap as the primary frontend for the
current phase. The application is an operational desk with authenticated
workflows, not yet a public client platform.

## Why

- Server-rendered pages already provide localization, permissions, CSRF and
  accessible fallback navigation.
- HTMX covers the current side panels, filters and quick actions without a
  second build pipeline.
- The versioned JSON API and XLSX/Word reports provide integration points
  without duplicating business rules.

## Reconsider a separate frontend when

- two or more independent clients consume the API;
- offline or mobile requirements become contractual;
- frontend release cadence must be decoupled from Django;
- API contracts, token authentication and object tenancy are production-ready.

Until then, new interactive behavior should remain progressively enhanced:
full URLs must work without JavaScript, and HTMX fragments must never become
public navigation targets.

The current UX modernization keeps this boundary: FullCalendar is an optional
progressive enhancement over the server-rendered calendar, and the Workboard
continues to share Django-rendered Tablero, Lista and Calendario views. The new
operational administration center composes existing permissions and forms; it
does not introduce a second frontend or duplicate domain rules.
