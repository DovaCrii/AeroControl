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

## Vendored

| Librería | Versión | Archivo | `sha384` (integrity) | Origen | Descargado |
| --- | --- | --- | --- | --- | --- |
| Leaflet | 1.9.4 | `leaflet/leaflet.js` | `sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH` | https://unpkg.com/leaflet@1.9.4/dist/leaflet.js | 2026-07-27 |
| Leaflet | 1.9.4 | `leaflet/leaflet.css` | `sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H` | https://unpkg.com/leaflet@1.9.4/dist/leaflet.css | 2026-07-27 |

`leaflet/images/*` (`layers.png`, `layers-2x.png`, `marker-icon.png`,
`marker-icon-2x.png`, `marker-shadow.png`) are referenced by `leaflet.css` by
relative path and ship unmodified from the same dist; they carry no SRI because
CSS-referenced images cannot.

## Pending (land with the code that loads them)

| Librería | Versión objetivo | Archivos | Origen | Bloque |
| --- | --- | --- | --- | --- |
| Leaflet-Geoman (free) | 2.x (última estable) | `leaflet-geoman/leaflet-geoman.min.js`, `leaflet-geoman/leaflet-geoman.css` | https://unpkg.com/@geoman-io/leaflet-geoman-free/dist/ | GEO-8 (edición) |

GEO-7 es un visor de solo lectura, así que no carga Geoman; se vendoriza cuando
GEO-8 traiga la edición. Al agregarlo, mover su fila a "Vendored" con `sha384` y
fecha.
