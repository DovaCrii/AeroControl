# Ilustraciones

Dibujos de estilo «doodle» que acompañan los estados vacíos, la portada y las fichas.

**Origen:** copiados el 2026-10-13 de `AeroAcademy` (`apps/core/static/core/img/doodles/`), proyecto del mismo
autor y de licencia MIT. Se renombraron para decir **qué muestran** y no de dónde vienen:

| Aquí | En AeroAcademy | Se usa en |
|---|---|---|
| `drone-scan.svg` | `captura-rpa.svg` | listas vacías, vuelos, aeronaves |
| `permit-clipboard.svg` | `dgac.svg` | permisos |
| `route-map.svg` | `rutas.svg` | planes y solicitudes |
| `survey.svg` | `topografia.svg` | planificación geoespacial |
| `documents.svg` | `documentos.svg` | documentos |
| `certificates.svg` | `certificados.svg` | credenciales y habilitaciones |
| `team.svg` | `equipo.svg` | operadores |
| `maintenance.svg` | `mecanica.svg` | mantenciones |
| `data.svg` | `ia-datos.svg` | informes |
| `hero-planning.svg` | `hero-ideas.svg` | portada de inicio de sesión |

**Reglas**
- Sólo SVG propios o con licencia clara. **No se incorporan fotos ni logos de terceros** (por ejemplo, de DJI) sin
  que el usuario aporte el archivo con derecho de uso.
- El trazo es oscuro: van sobre una **lámina clara** (`.illus-tile`), también en el tema oscuro.
- Se cargan con `<img>`, nunca en línea, y no deben contener scripts ni enlaces externos (lo vigila
  `apps/core/test_lv302_illustrations.py`).
