# Editor geoespacial KMZ/KML (BLOQUE GEO) — propuesta técnica

> **Estado:** propuesta aprobada 2026-07-27. **No implementada aún.** El trabajo
> arranca en `GEO-0` solo con el "go" explícito del usuario. Este documento es la
> fuente de verdad del diseño; el tablero de tareas vive en `MASTER_PLAN.md`
> (sección "BLOQUE GEO").
>
> **Supera** la decisión "Áreas de vuelo en KMZ — archivar sí, interpretar no"
> del 2026-07-25. Aquella no fue un olvido: fue una decisión deliberada que el
> usuario ahora revierte con un alcance acotado (editor liviano, no un GIS).

## Objetivo

Un editor geoespacial **liviano** para planificación RPA/UAS integrado al
workflow operativo: importar un KMZ/KML, visualizar e interpretar su estructura
(carpetas, puntos, líneas, polígonos), editar geometrías y atributos, versionar
de forma inmutable, aprobar por rol, y re-exportar un KMZ/KML válido que abra en
Google Earth. **No** es un reemplazo de QGIS/ArcGIS ni un GIS corporativo.

Un único KMZ (p. ej. `CC716_PLANIFICACION_VUELO.kmz`) puede contener toda la
planificación: área de levantamiento, ruta, despegue/aterrizaje, torres,
infraestructura, restricciones. AeroControl interpreta esa estructura interna;
no se exige un KMZ por capa.

## Decisiones tomadas (2026-07-27)

| Decisión | Elección | Motivo resumido |
|---|---|---|
| Motor de mapa | **Leaflet 1.9 + Leaflet-Geoman free** | 42 KB gz, sin WebGL (corre en notebooks/VMs industriales), raster nativo, no rompe el CSP. MapLibre descartado para MVP (plugin de edición joven, 3× peso, exige `worker-src blob:`). |
| Anclaje del plan | **`cost_center` obligatorio + `flight_permission` opcional** | La planificación suele preceder al permiso; el scoping entra por `cost_center` como el resto del sistema. No existe un modelo "Operación" paraguas. |
| Mapa base | **OSM (calles) + Esri World Imagery (satélite) + Esri Reference (etiquetas)**, sin API keys | Cero fricción para partir; proveedor intercambiable vía config. Sin tiles de Google. |
| Formato maestro | **JSON canónico "AeroKML" por versión** (no GeoJSON, no filas por feature) | GeoJSON solo como intercambio hacia el frontend. Ver §Modelo de datos. |
| Parser | **lxml endurecido, parser propio** | fastkml es lossy; defusedxml.lxml está deprecado. lxml ya está en el árbol (transitiva de python-docx) → se promueve a dependencia directa pineada. |

## 1. Arquitectura

```
KMZ/KML original ──▶ Document (compliance, intacto, pipeline de subida existente)
        │
   apps/geo/kml/parse.py (lxml endurecido) + kmz.py (zipfile en memoria, guards)
        ▼
   Canónico "AeroKML JSON" (schema_version 1)   ←── formato maestro
        ▼
   GeoPlanVersion.content (JSONField inmutable, append-only)
        ▼
   API JSON (canónico completo; el navegador deriva GeoJSON solo para render)
        ▼
   Isla JS: Leaflet + Geoman (static/js/geo/, ES modules, vendorizado con SRI)
        ▼
   POST commit (payload completo + base_version) ──▶ nueva GeoPlanVersion
        ▼
   apps/geo/kml/build.py ──▶ KML/KMZ exportado (recursos copiados del original)
```

- **App nueva `apps/geo/`** con submódulo `kml/` (parse, kmz, canonical, build)
  puro-Python, testeable sin HTTP.
- **Shell HTMX + isla JS**: la página del plan es server-rendered (cabecera,
  transiciones de estado, lista de versiones); el editor es un `<div>` autónomo
  con `{{ config|json_script }}` (CSP-safe) + `<script type="module">`. htmx no
  entra al interior de la isla.
- **DJI futuro = adapter** que lee `GeoPlanVersion.content` de un plan aprobado y
  emite misión (WPML/KMZ); la comparación planificado-vs-ejecutado importa el log
  como plan de solo lectura ligado al mismo `flight_permission`. Nada del módulo
  importa ni conoce DJI — es un boundary, no una dependencia.

## 2. Modelo de datos — blob canónico por versión (no filas por feature)

Un plan típico (50-500 features) pesa 100 KB-1 MB. Modelar cada feature como fila
explota en snapshots (50 commits × 500 features = 25.000 filas duplicadas) y
reparte la preservación KML en dos lugares. El blob por versión hace del commit
un `INSERT`, hereda el patrón append-only de `AuditEvent`, y SQLite JSON1 +
columnas derivadas (bbox, feature_count) cubren las consultas previsibles.

```python
class GeoPlan(BaseModel):            # uuid pk, created/updated, is_active, notes
    STATUS = draft | editing | in_review | approved | rejected
    EDITABLE_STATUSES = {"draft", "editing"}
    title
    cost_center       FK(registry.CostCenter, PROTECT)          # obligatorio
    flight_permission FK(operations.FlightPermission, SET_NULL, null=True)  # opcional
    status
    created_by        FK(user, PROTECT)
    source_document   FK(compliance.Document, PROTECT)          # el KMZ original, intacto
    current_version   FK(GeoPlanVersion, PROTECT, null=True)
    Meta.permissions = [("approve_geoplan", "Can approve geo plan")]
    índices: (status, is_active), (cost_center, is_active)

class GeoPlanVersion(models.Model):  # inmutable: sin updated_at / is_active
    plan            FK(GeoPlan, PROTECT)
    version_number  PositiveInteger
    parent_version  FK(self, null=True)
    restored_from   FK(self, null=True)
    content         JSONField                 # canónico completo
    content_checksum sha256 hex
    source          import | editor | restore
    summary         CharField                 # mensaje de commit
    feature_count; size_bytes
    bbox_west / south / east / north
    created_by      FK(user, PROTECT); created_at
    objects = queryset append-only (mismos 4 cerrojos que AuditEvent)
    UniqueConstraint(plan, version_number); CheckConstraint(version_number >= 1)

class GeoPlanHistory(BaseModel):     # espejo de operations.PermissionHistory
    plan FK(CASCADE); previous_status; new_status; changed_by; changed_by_user
```

### Canónico "AeroKML JSON" (schema_version 1)

Árbol fiel al KML con **orden de hermanos preservado**. Tres tipos de nodo:
`folder`, `placemark`, `raw`. Cada nodo lleva:

- `uid` estable (generado al importar, conservado entre commits) → habilita diffs
  legibles ("movido"/"renombrado" en vez de "borrado+creado").
- `extras: [xml_crudo]` para hijos **conocidos pero no editables** (LookAt,
  Camera, TimeSpan, Region, `gx:*`), re-emitidos en su posición.
- Los contenedores **desconocidos** (NetworkLink, GroundOverlay, Schema)
  sobreviven como nodos `{"kind": "raw", "raw_xml": "..."}` intercalados en orden.
- `shared_styles`: el Style/StyleMap **resuelto** para edición + `raw_xml`
  completo para re-emisión intacta si el usuario no lo tocó.
- `kmz_resources`: nombres de recursos embebidos (iconos, imágenes). **No entran
  a la BD**: al exportar KMZ se copian byte a byte desde el `source_document`.
- Coordenadas `[lon, lat, alt?]` WGS84, como KML.
- `extended_data`: `{raw_xml, pairs}` — el raw es la verdad para export; pairs es
  la vista editable (si se edita, se regenera el raw).

**Caps duros** (validados en import y en cada commit): `content` serializado
≤ 8 MB, ≤ 2.000 features.

## 3. Parser / generador KML (round-trip)

**Parser propio sobre lxml endurecido.** lxml 6.1.1 ya está en el árbol como
transitiva de python-docx → se promueve a dependencia directa pineada.

**Endurecimiento** (`apps/geo/kml/parse.py`):
1. Pre-chequeo de bytes: rechazar si aparece `<!DOCTYPE` (case-insensitive) →
   mata XXE y billion-laughs antes de instanciar el parser.
2. `etree.XMLParser(resolve_entities=False, load_dtd=False, dtd_validation=False,
   no_network=True, huge_tree=False)`.
3. Tope de nodos (~200.000) y de profundidad de Folders (32).

**KMZ** (`apps/geo/kml/kmz.py`, todo en memoria sobre `BytesIO`):
- ≤ 200 entradas; nombre rechazado si es absoluto, contiene `..`, `\` o nulo.
- Por entrada: `file_size` ≤ 50 MB y ratio `file_size / compress_size` ≤ 100;
  total descomprimido ≤ 120 MB. Lectura con `read(limit+1)` verificando lo
  declarado (los zip bombs mienten en la cabecera).
- KML principal: primera entrada `*.kml` en la raíz (regla de facto: `doc.kml`).

**Preservación de elementos no soportados**: híbrida por nivel, crudo en
posición (ver canónico). Regla rectora: **si el usuario no lo tocó, sale
byte-equivalente.**

**Generador** (`apps/geo/kml/build.py`): construye el árbol con `etree` para lo
estructurado y re-parsea los `raw_xml` **con el mismo parser endurecido** (los
fragmentos vienen de la BD pero se desconfía por defecto).

**Test round-trip** (`apps/geo/tests/test_roundtrip.py` + corpus de fixtures
reales de Google Earth Pro, QGIS, MultiGeometry+ExtendedData, CDATA/HTML, KMZ con
imágenes, `gx:Track` no soportado): aserción central
`parse(export(parse(fixture))) == parse(fixture)` comparando canónicos (ignorando
`uid`), más estabilidad de punto fijo. Fixtures maliciosos (DOCTYPE, ratio
1000:1, entrada `../../evil`, 300 entradas) deben levantar `KmlImportError`.

## 4. Seguridad — threat model KML/KMZ

| Amenaza | Defensa |
|---|---|
| XXE / billion laughs | Rechazo de `<!DOCTYPE` + parser sin entidades/DTD/red |
| ZIP bomb | En memoria: ≤200 entradas, ratio ≤100:1, descomprimido ≤120 MB, lectura con límite verificado |
| Path traversal en entradas ZIP | Nombre rechazado si absoluto / `..` / `\` / nulo; nunca se extrae a disco |
| XSS vía `description`/`name` (KML permite HTML/CDATA) | Inspector renderiza SIEMPRE con `textContent`; test explícito |
| Payload de commit malicioso | Servidor re-valida todo: schema, caps, rangos de coordenadas, y cada `raw_xml` se re-parsea con el parser endurecido |
| Export sin rastro | Export es **POST** (el middleware no audita GETs) → AuditEvent por el canal normal |
| Archivos gigantes | Tope 20 MB existente + fijar `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE` explícitos (hoy sin definir) |

## 5. Workflow y permisos

`draft → editing → in_review → approved | rejected`, con `rejected → editing` y
`approved → editing` (des-aprobar exige el mismo permiso que aprobar). Seis
subclases de `StatusTransitionView` (patrón exacto de FlightPermission);
`permission_action="approve"` construye `geo.approve_geoplan` automáticamente.
Historial vía extensión del mapping en `apps/core/signals.py` con
`"geoplan": (GeoPlanHistory, "plan")`.

`bootstrap_roles`: Operations → add/change/view; Compliance → view + **approve**;
Viewer → view; Administrator → todo.

**Bloqueo de edición de aprobados en 3 capas**: (1) la API de commit rechaza con
409 `plan_locked` si `status ∉ EDITABLE_STATUSES` — **autoritativa**, toda
mutación de contenido pasa por el commit; (2) `GeoPlanVersion.clean()`
re-verifica; (3) el editor carga read-only (cosmético, nunca la única defensa).

Archivar = `is_active=False` (convención del repo); las versiones jamás se borran
(FK `PROTECT` + queryset append-only).

## 6. API (patrón `apps/workboard/api.py`: rutas a mano, sin router)

| Método/Ruta | Función |
|---|---|
| `GET /api/v1/geo/plans/<uuid>/` | Meta (status, current_version, updated_at) |
| `GET .../versions/` | Lista de versiones (sin content) |
| `GET .../versions/<n>/content/` | Canónico completo, `ETag: checksum` |
| `POST .../versions/` | **Commit**: `{base_version, summary, content}` → 201 · 409 `conflict`/`plan_locked` · 400 validación · dedupe por checksum → 200 `no_change` |
| `POST .../versions/<n>/restore/` | Nueva versión copiando `n` (server-side) |
| `POST .../export/` | `{version, format: kml\|kmz}` → FileResponse (POST para auditar) |

Concurrencia en dos capas: `If-Unmodified-Since` (patrón existente) + `base_version`
contra la última versión (autoritativa). Throttling scoped: `geo-commit 30/min`,
`geo-export 10/min`. Un `AuditEvent` por commit/restore/export/transición con
metadata (`version`, `checksum`, `feature_count`) — **jamás por vértice** (el
undo/redo es 100% cliente). OpenAPI manual extendido.

## 7. Frontend — isla JS sin build pipeline

`static/js/geo/`: `main.js` (entry), `state.js` (store canónico + dirty +
undo/redo), `doc.js` (helpers del canónico ↔ GeoJSON), `map.js` (Leaflet +
switcher de proveedores), `panel.js` (árbol de capas), `inspector.js`
(propiedades, render con `textContent`), `measure.js` (haversine + shoelace
esférico propios), `api.js` (fetch con CSRF, `If-Unmodified-Since`, manejo
400/403/409/429). ES modules nativos, sin bundler.

Vendorizado en `static/vendor/` con SRI (establece el patrón que cierra T5.9).
Guardado explícito (botón → modal con `summary`), nunca autosave por movimiento;
`beforeunload` si hay cambios sin guardar; 409 → banner con rescate (descarga del
canónico local). Undo/redo: pila de `structuredClone` capada a 50, un paso por
gesto.

Proveedores de tiles: `settings.GEO_TILE_PROVIDERS` (lista de dicts) → serializado
al `json_script`. `api_key_env` soportado para proveedores futuros; las claves
nunca van al repo ni al JSON del cliente (proxy view si hiciera falta, V2).

Esto **rompe deliberadamente** el "cero archivos .js" de
`docs/frontend-boundary.md`; GEO-0 enmienda ese documento: las islas JS con
módulos ES sin build son admisibles cuando el componente es intrínsecamente
cliente (editor de mapa); el shell sigue server-rendered + htmx.

## 8. Brechas del stack que el bloque aprovecha o registra

1. **T5.9/V.11 (vendorización + SRI)** deja de ser opcional: GEO-0 vendoriza
   Leaflet/Geoman con SRI y establece `static/vendor/`; migrar el resto de CDNs
   queda a un paso (cerraría V.11 y habilitaría CSP enforcing V.10).
2. **CSP**: el editor es 100% CSP-safe (`json_script`, cero inline, cero
   `onclick=`) — reduce la deuda V.10 como precedente.
3. **`FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE`** sin definir
   (defaults 2.5 MB): fijarlos explícitos en GEO-0.
4. **Huecos de auditoría** en `DocumentReplace`, `DocumentDelete`,
   `StatusTransitionView`, `FlightRecordDelete` (mutan sin `set_audit_context`):
   arreglo ortogonal en GEO-0b.
5. **`DocumentDownload` autoriza a nivel modelo, no objeto**: relevante porque los
   KMZ fuente pasan por ahí; ya registrado como F-05/T2.2.
6. **El drag del Kanban no maneja 4xx** (tarjeta fantasma): el editor GEO no
   repite eso; arreglar el del Kanban queda en GEO-0b.
7. **lxml** pasa de transitiva a directa pineada.

## 9. Tareas (tablero en MASTER_PLAN)

MVP = `GEO-0`..`GEO-10`, en dos hitos: **visor** (GEO-0..7: importar, ver, medir,
exportar tal cual) y **editor** (GEO-8..10: editar, versionar, aprobar). V2 =
`GEO-11`..`GEO-14` (capas avanzado, diff visual, iconos embebidos/StyleMap
highlight/XSD, hooks DJI). Cada tarea: rama `codex/geo-N`, tests 403 por vista
nueva, strings al catálogo `es`, cobertura ≥83, `verify.ps1` verde.

## 10. Los 5 riesgos principales

1. **Cola larga de fidelidad round-trip** — KML real trae extensiones creativas.
   Mitigación: preservación cruda en posición + corpus creciente + original
   siempre descargable.
2. **Crecimiento del blob en SQLite** — caps duros, dedupe por checksum,
   `size_bytes` monitoreable; compresión zlib a futuro si duele.
3. **Primera isla JS grande sin build** — enmienda del boundary, módulos chicos,
   toda la lógica que importa en el servidor con tests.
4. **Concurrencia sin merge** — 409 + rescate local; lock advisory en V2.
5. **Nueva superficie ZIP/XML** — fixtures maliciosos en el gate de CI desde
   GEO-2; `description` jamás a `innerHTML`; `raw_xml` re-validado en export.

## Verificación (al implementar cada tarea)

- `uv run pytest` — modelos, parser (corpus + maliciosos), **round-trip**, API
  (401/403/404/409/429), workflow (403 por rol), import atómico.
- Navegador: importar un KMZ real de Google Earth → editar → commit → export →
  **abrirlo en Google Earth** y verificar carpetas/estilos/geometrías.
- Gate existente: `manage.py check --deploy`, `ruff`, `makemigrations --check`,
  test de deriva de traducciones.
