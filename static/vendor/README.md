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
| Leaflet-Geoman (free) | 2.20.0 | `leaflet-geoman/leaflet-geoman.min.js` | `sha384-lQvyfQizM1lAcgrQCt06G9R/LyriCixUPr2SkbZm6D+qYYghxeaK/wkmOard+Om0` | https://unpkg.com/@geoman-io/leaflet-geoman-free@2.20.0/dist/leaflet-geoman.min.js | 2026-07-27 |
| Leaflet-Geoman (free) | 2.20.0 | `leaflet-geoman/leaflet-geoman.css` | `sha384-++juJE6hRzkkV4Ri9H2C+3yjCTdEk4PaZxptm3cpgKKjuMcAHErn35Q/0sGitZCR` | https://unpkg.com/@geoman-io/leaflet-geoman-free@2.20.0/dist/leaflet-geoman.css | 2026-07-27 |
| Bootstrap | 5.3.3 | `bootstrap/bootstrap.min.css` | `sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH` | https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css | 2026-07-29 |
| Bootstrap | 5.3.3 | `bootstrap/bootstrap.bundle.min.js` | `sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz` | https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js | 2026-07-29 |
| htmx | 2.0.10 | `htmx/htmx.min.js` | `sha384-H5SrcfygHmAuTDZphMHqBJLc3FhssKjG7w/CeCpFReSfwBWDTKpkzPP8c+cLsK+V` | https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js | 2026-07-29 |
| Chart.js | 4.4.7 | `chartjs/chart.umd.min.js` | `sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC` | https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js | 2026-07-29 |
| FullCalendar | 6.1.15 | `fullcalendar/index.global.min.js` | `sha384-B1OFx8Gy9GjPu8UbUyXbGQpzll9ubAUQ9agInFJ8NnD7nYG1u/CLR+Sqr5yifl4q` | https://cdn.jsdelivr.net/npm/fullcalendar@6.1.15/index.global.min.js | 2026-07-29 |
| SortableJS | 1.15.6 | `sortable/Sortable.min.js` | `sha384-HZZ/fukV+9G8gwTNjN7zQDG0Sp7MsZy5DDN6VfY3Be7V9dvQpEpR2jF2HlyFUUjU` | https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js | 2026-07-29 |

`leaflet/images/*` (`layers.png`, `layers-2x.png`, `marker-icon.png`,
`marker-icon-2x.png`, `marker-shadow.png`) are referenced by `leaflet.css` by
relative path and ship unmodified from the same dist; they carry no SRI because
CSS-referenced images cannot.

Geoman is loaded only on the editable plan detail page (GEO-8); the read-only
viewer (GEO-7) does not pull it in.
