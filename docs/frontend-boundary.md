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

## JavaScript islands (amended 2026-07-27 for BLOQUE GEO)

A separate SPA is still postponed. But some components are *intrinsically*
client-side and cannot be progressively enhanced away — an interactive map
editor is the clear case: pan, zoom, vertex dragging and live measurements have
no meaningful no-JavaScript fallback. For these, a **JavaScript island** is
admissible under the following rules, so the boundary bends without breaking:

- The **page shell stays server-rendered**: navigation, permissions, state
  transitions and the list of saved versions are Django + HTMX, exactly like the
  rest of the app. The island is a single `<div>` inside that shell.
- The island receives its configuration through `{{ ... |json_script }}` and is
  loaded as a native **ES module** (`<script type="module">`) from `static/`.
  **No bundler, no build pipeline, no `node_modules`.** No inline handlers
  (`onclick=`) and no inline `<script>` bodies, so the island is CSP-safe and
  actually reduces the inline-JS debt rather than adding to it.
- **Business rules never move to the client.** All validation, the canonical
  document format, versioning and export live on the server with tests; the
  island is a replaceable view over an API. If the JavaScript were deleted, the
  data and its guarantees would be intact.
- Third-party libraries for islands are **vendored into `static/vendor/` with
  Subresource Integrity**, not loaded from a CDN (see `static/vendor/README.md`).

The BLOQUE GEO editor ([docs/dev/geo-editor-plan.md](geo-editor-plan.md)) is the
first island under this rule. It is a bounded exception for map editing, not a
general license to add client frameworks.
