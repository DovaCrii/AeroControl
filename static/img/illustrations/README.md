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

**Propias** (dibujadas para AeroControl el 2026-11-03, `LV-397`; mismo trazo y paleta que las anteriores):

| Archivo | Muestra | Se usa en |
|---|---|---|
| `fixed-wing-drone.svg` | dron de ala fija sobre un terreno | página «Cómo funciona» (siguiente PR) |
| `light-aircraft.svg` | avión liviano de ala alta | página «Cómo funciona» |
| `helicopter.svg` | helicóptero en vuelo estacionario | página «Cómo funciona» |
| `control-tower.svg` | torre de control, pista y manga de viento | página «Cómo funciona» |
| `kmz-area.svg` | área de vuelo KMZ sobre un mapa | solicitudes de vuelo vacías |
| `compliance-shield.svg` | escudo de cumplimiento, documentos y semáforo | no conformidades vacías |

Las nuevas llevan su movimiento (hélices, manga, baliza) **sólo** dentro de
`@media (prefers-reduced-motion: no-preference)`; cargadas con `<img>` no ejecutan nada más.

Las siluetas de equipos de `static/img/aircraft/` (`matrice-4`, `matrice-400`, `dock`, `gnss-base`) también son
propias, dibujadas de la forma del equipo y **sin logos ni texto de marca**. Las fotos de internet viven aparte, en
`static/img/photos/`, cada una con su licencia en `LICENSES.md`.

**Reglas**
- Sólo SVG propios o con licencia clara. **No se incorporan logos de terceros** (por ejemplo, de DJI) ni fotos sin
  licencia libre registrada en `static/img/photos/LICENSES.md` o aportadas por el usuario con derecho de uso.
- El trazo es oscuro: van sobre una **lámina clara** (`.illus-tile`), también en el tema oscuro.
- Se cargan con `<img>`, nunca en línea, y no deben contener scripts ni enlaces externos (lo vigila
  `apps/core/test_lv302_illustrations.py`).
