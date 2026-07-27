# Vendored front-end libraries

Third-party JavaScript/CSS that the app serves from its own origin instead of a
CDN. Vendoring here is the pattern that lets the Content-Security-Policy tighten
to `'self'` (MASTER_PLAN T5.9 / V.10-V.11) and removes the runtime dependency on
external CDNs staying up and unmodified.

## Rules

- Commit the exact, unmodified library files (minified build as published).
- Reference them from templates with **Subresource Integrity**:
  `<script src="{% static 'vendor/leaflet/leaflet.js' %}"
   integrity="sha384-..." crossorigin="anonymous">`.
- Record below the exact version and the upstream URL each file came from, so a
  future upgrade is a deliberate, verifiable step.
- Compute the hash from the downloaded file, e.g. (PowerShell):
  `"sha384-" + [Convert]::ToBase64String((Get-FileHash leaflet.js -Algorithm SHA384).Hash -as [byte[]])`
  or, portably: `openssl dgst -sha384 -binary leaflet.js | openssl base64 -A`.

## Pending (added in GEO-7, when the map island is built)

The BLOQUE GEO editor ([../../docs/dev/geo-editor-plan.md](../../docs/dev/geo-editor-plan.md))
needs these. They are intentionally **not** committed yet — GEO-0 only
establishes the directory and the policy; the binaries land with the code that
loads them, each with its SRI hash recorded here:

| Librería | Versión objetivo | Archivos | Origen |
| --- | --- | --- | --- |
| Leaflet | 1.9.4 | `leaflet/leaflet.js`, `leaflet/leaflet.css`, `leaflet/images/*` | https://unpkg.com/leaflet@1.9.4/dist/ |
| Leaflet-Geoman (free) | 2.x (última estable) | `leaflet-geoman/leaflet-geoman.min.js`, `leaflet-geoman/leaflet-geoman.css` | https://unpkg.com/@geoman-io/leaflet-geoman-free/dist/ |

Cuando se agreguen, mover cada fila a una sección "Vendored" con su `sha384` y la
fecha de descarga.
