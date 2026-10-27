# HANDOFF — AeroControl

## 🟡 2026-10-27 — tanda fusionada, **pendiente de un despliegue** (`main` en `934c926`, producción en `1dfde39`)

`p340` corre **`1dfde39`** (informe mensual v2, desplegado y verificado; timer de cierre del 1-11 06:30 UTC registrado). Desde ahí se fusionaron 60 commits **sin desplegar**: aislamiento por empresa (F-08), alertas por empresa, Informes F1/F2, Cumplimiento v4 (`compliance.css`), capa de permisos en trámite del mapa (`LV-379`), adjuntos en la ficha de mantención (`LV-382`), navegación lateral nueva (`LV-381`, F0–F5), msgpack 1.2.4 y gunicorn 26.

**Qué lleva el despliegue:** **sin migración** (ninguna en el rango); **con estáticos** (`collectstatic`) y **con `uv sync`** (cambian `msgpack` y `gunicorn` en `uv.lock`). Se dicta con `bash scripts/deploy.sh --dry-run` y luego `bash scripts/deploy.sh`; no se da por desplegado sin el hash final igual a `origin/main`.

**Pendiente — del usuario**
- Desplegar la tanda y revisar con recarga forzada: navegación (tema oscuro incluido), Cumplimiento v4 y la capa de permisos en trámite del mapa (nadie los ha visto en pantalla).
- Cargar por la interfaz las 5 mantenciones de los RPA (tras desplegar los adjuntos); antes, confirmar contra el certificado DGAC la serie de CC717.
- No crear una segunda `OperationalTenant` hasta tener desplegadas las fases de aislamiento; si se crea, correr `seed_alert_rules --tenant`.

**Pendiente — del código:** prueba de aislamiento de `cost_center_filter` con usuario; chip `sites_without_permit` del panel; contraste 1.83:1 de la capa «vigentes» del mapa; SIGO por modalidades (`LV-278`, bloque B espera las capturas del portal); `T1.4` espera visto bueno; orden por columna (`LV-280`).

## ✅ 2026-10-26 — tanda del 21 al 23 de octubre y emisión con corte anticipado **desplegadas** (`32dce41`)

`p340` corre **`32dce41`**. Se desplegó en dos pasadas, leídas de la salida pegada: (1) `d42c0f1` (la tanda tiempo/AIP/permiso/credencial/baja/visual v3 de la entrada de abajo, ya fusionada el 23) y (2) `32dce41`: **emisión del informe mensual con corte anticipado** (`LV-375`) y **todos los centros de costo visibles** en la tabla de permisos de Cumplimiento (`LV-374`). Cada pasada con respaldo previo (`restorable.`), `git pull` + `migrate` (`reporting.0006_lv375_early_cutoff_permission`, solo el permiso), reinicio (`active`, hash leído), `health: 200` y `bootstrap_roles`. Los estáticos se copiaron en la primera pasada (la segunda no llevó). `WEATHER_USER_AGENT` ya está definido en la VM y el clima funciona con MET Norway.

**Emisión con corte anticipado (`LV-375`):** permiso propio `reporting.issue_early_reportrun`, **solo Administrator** (y el superusuario). Botón «Emitir con corte anticipado» en `Informe mensual RPA` con `?period=AAAA-MM` solo si el mes está abierto; motivo obligatorio (10 a 300 caracteres, auditado y no impreso); la **portada no cambia**; el pie dice «Revisión 0 · Corte anticipado dd-mm-aaaa · Página N de M» y las notas de cobertura «estado al corte anticipado». **El 1 de noviembre el timer emite solo la revisión de cierre**, que reemplaza a la anticipada (la anticipada pasa a `superseded` conservando quién la aprobó; la narrativa viaja): confirmar con `generate_monthly_report --dry-run` ese día. La regla general no cambia: el botón normal y el timer siguen rechazando un mes abierto (`LV-233`). Verificado de forma independiente: flujo completo, PDF A4 (5 páginas, pie en una línea), agosto cerrado idéntico byte a byte, y el cierre simulado al 1 de noviembre.

**Seguimiento — fusionado sin desplegar: nada.** Queda por **fusionar y desplegar en una segunda tanda** (ramas locales o PR abiertos):
- **`LV-372` aislamiento por empresa completo (F-08):** rama `codex/tenant-listas-transiciones` (sobre `codex/tenant-geo-panel`); suite completa en verde (6715 pasaron, 6 saltadas) pero es un cambio **amplio** (listas, fichas, acciones, formularios, bandeja, búsqueda, calendario, tableros, informe de cumplimiento); sin migración ni estáticos. Pendientes de esa fila: `snapshot_compliance`, `AuditEvent` sin empresa, el admin de Django, la reversión de importación de centros de costo. El informe mensual DGAC y `report_notice` quedan **globales por diseño** (`ReportRun` sin empresa): `view_reportrun` y `change_reportrun` solo a roles de toda la organización.
- **`LV-373` marca de la hora actual, cambio de día y fecha en los 7 días del clima:** PR #172 abierto; lleva estáticos.
- **Informes F1 y F2** (`LV-355`): ramas `codex/informes-f1-export` y `codex/informes-f2-cabecera-a4` (la F0 ya está en `main` dentro de `LV-375`); nombres de archivo con fecha, una sola tubería de exportación, cabecera única y A4; lleva estáticos (una regla de `identity.css`).
- **Rediseño de Cumplimiento v4** (tabla «Permisos de vuelo por centro de costo» y tarjetas de estado): diseño de Opus en curso; ver `LV-376`.

**Para la próxima vez:** `pip-audit` hizo fallar el CI cuatro veces por vulnerabilidades nuevas en dependencias (`certifi`, `pillow`, `djangorestframework`, `pypdf`, `filelock`): conviene mirar `uv run pip-audit` al empezar la jornada.

**No verificado a ojo (el navegador integrado no compone):** el aspecto de la capa del AIP y los límites administrativos en el mapa, la pantalla de revisión del AIP, el formulario del permiso con el mini-mapa, el chip y el banner de «Ex colaborador», la cifra «Aeronaves con seguro JAC al día» del Resumen ejecutivo (usa un criterio distinto al del panel: **revisarla antes de aprobar**), y el tema claro de varias pantallas.

**Pendiente — del usuario:** una credencial de ejemplo anonimizada fuera del repo para fijar las etiquetas del lector; quién revisa cada enmienda del AIP y el umbral de discrepancia en metros (`AIRSPACE_CROSSCHECK_THRESHOLD_M`); si `pdfplumber` entra como dependencia; las respuestas de la DGAC y del revisor sobre punto centro y radio en áreas no circulares (la hoja SIGO **no se tocó** a la espera de eso); el orden de «Qué atender primero» (`PRIORITY_ORDER`); decisiones de Informes (`docs/dev/informes-optimizacion.md` §7); licencias (`docs/dev/licencias-y-terminos.md`).

## ✅ 2026-10-23 — tanda «tiempo sin Open-Meteo, AIP-Chile, permiso, credencial, baja y visual v3» fusionada (desplegada el 2026-10-26 en `d42c0f1`; ver la entrada de arriba)

Todo lo de abajo está en `main` con el CI verde; **nada se ha desplegado** desde `c4c6b85` (la tanda Entorno + Espacio aéreo + Cumplimiento, ya en producción). Son ~180 archivos.

**Qué entró**
- **El tiempo sin Open-Meteo** (`LV-364/365/366`): sol local NOAA (`apps/core/solar.py`), proveedor **MET Norway** (`WEATHER_PROVIDER=met_norway` por omisión; `open_meteo` queda como alternativa de pago/propia) y búsqueda de ciudades en las 346 comunas del BCN sin red. **MET no trae en Chile ráfagas, probabilidad de lluvia ni visibilidad**: la tarjeta dice «No disponible en esta fuente» y no emite esos eventos.
- **AIP-Chile (ENR 5.1) como fuente primaria del espacio aéreo** (`LV-361`, fases 1 a 5): campos de fuente y revisión, parser (`aip_parser.py`), comando `import_aip_enr5` (borrador, nada se publica solo), cruce con el mapa de Google, **pantalla de revisión humana** (`/administracion/espacio-aereo/`, permiso `airspace.review_airspacesnapshot`) y la capa del AIP aprobado en el mapa con insignias de fuente. Sin AIP publicado, el mapa es byte a byte el de antes.
- **Mapa:** arreglo del fallo en producción (`LV-363`: un `MultiGeometry` real servía geometría vacía y mataba el dibujo) y mejora visual con límites administrativos de comunas/regiones y búsqueda (`LV-367` fases 5 a 7).
- **Visual v3** (`LV-367` fases 1 a 4): Entorno en tarjetas, Centelleo como infografía, Cumplimiento simple y colapsable.
- **Permiso** (`LV-368`): cierre de **tres brechas reales de aislamiento por empresa** (selector de plan, vincular/desvincular y API de planes) más una cuarta (`GeoPlanSplitIntoRequests`/importación); ficha más liviana («Qué falta», secciones, menú «⋯»); lo geoespacial dentro del formulario (mini-mapa, selector de plan, importar KMZ); credencial del operador **leída desde el PDF** con confirmación campo por campo.
- **Baja del colaborador** (`LV-369`): «Registrar salida de la empresa» (fecha, motivo y nota opcionales; no borra nada), insignia «Ex colaborador», alertas resueltas, histórico conservado, informe mensual al corte exacto; **el catastro y los informes son solo lo activo**.
- **Asistente** (`LV-362`): cliente NVIDIA endurecido (cadena de modelos, 429, cupo); **sigue apagado en producción**. **Seguridad menor** (`LV-370`): el receptor de informes CSP ya no da 500 con un cuerpo de forma inesperada. **Dependencias:** `certifi`, `pillow`, `djangorestframework` y `pypdf` actualizadas por `pip-audit`.

**Seguimiento — fusionado sin desplegar: todo lo anterior.**
- **LLEVA MIGRACIONES (4):** `airspace.0002_aip_source_and_review_fields`, `0003_crosscheck_snapshot_and_measured`, `0004_review_airspacesnapshot_permission` y `registry.0042_operator_left_company`.
- **LLEVA ESTÁTICOS:** sí (`airspace-map.js`, `airspace.css`, `airspace-review.css`, `airspace-review-map.js`, `geo/mini-map.js`, `permission-plan-picker.js`, `geo-mini-map.css`, `identity.css`, `icons-ui.svg`, entre otros) → `collectstatic` obligatorio.
- **LLEVA `uv sync --no-dev`** (cambia `uv.lock`) y `.mo` (versionado; no hay `compilemessages`).
- **Después del `migrate`, en la VM:** `manage.py bootstrap_roles` (el permiso nuevo `airspace.review_airspacesnapshot` lo recibe solo Administrator).
- **ANTES de desplegar, en `/etc/aerocontrol.env`:** `WEATHER_USER_AGENT` (app y contacto, p. ej. `AeroControl/1.0 <correo corporativo>`; **sin él la tarjeta del tiempo queda «no disponible»**) y comprobar que la VM sale a `api.met.no`. No va en el repo.
- Importar el AIP en la VM (opcional, después del despliegue): `import_aip_enr5` necesita `pdfplumber`, que **no es dependencia del proyecto** (`uv run --with pdfplumber python manage.py import_aip_enr5 --dry-run` y luego sin `--dry-run`); crea un **borrador**: nada se ve hasta aprobarlo en la pantalla de revisión.

**No verificado a ojo (el navegador integrado no compone y las capturas salieron recortadas):** el aspecto de la franja y Cumplimiento en tema claro y a 375 px, el mapa con la capa AIP y los límites administrativos (rendimiento del canvas y compresión del JSON en `p340`), la pantalla de revisión del AIP, la ficha del permiso entera en claro, el formulario con el mini-mapa, el chip y el banner de «Ex colaborador», el reemplazo de plan al editar un permiso. Nada contra MET desde `p340`. Una mirada humana, con recarga forzada, antes o justo después de desplegar.

**Pendiente — del usuario**
- `WEATHER_USER_AGENT` (arriba) y la salida a `api.met.no`.
- **Una credencial de ejemplo anonimizada, fuera del repo**, para fijar las etiquetas exactas del lector de credenciales (hoy son las del diseño).
- **Quién revisa y aprueba cada enmienda del AIP**, el **umbral de discrepancia en metros** (`AIRSPACE_CROSSCHECK_THRESHOLD_M`; sin él el cruce muestra la distancia sin juzgar) y si `pdfplumber` entra como dependencia.
- El orden de «Qué atender primero» en Cumplimiento (`PRIORITY_ORDER`, `apps/dashboard/compliance_section.py`) y la razón escrita de las escalas 30/60 días de los permisos.
- OCR para credenciales fotografiadas (hoy solo PDF con texto); licencias (`docs/dev/licencias-y-terminos.md`): Esri/OSM para los fondos de mapa, GEOCOM, NVIDIA; decisiones de Informes (`docs/dev/informes-optimizacion.md` §7).

**Pendiente — del código:** `GeoPlanListView`/`GeoPlanDetailView` y el resto de vistas de `geo` no acotan por empresa (F-08 parcial, hoy una sola empresa); `dashboard()` y `upcoming_expirations` tampoco; la franja del panel «zonas ≤N km» sigue contando solo la foto de Google; el cruce AIP/Google se calcula al importar; `gunicorn` 23 → 26 (compatibilidad); logo duplicado `assets/aerocontrol-mark.svg` (se deja); la capa «regiones» de BCN; localidades (INE/OSM); fases F0 a F5 de Informes (`LV-355`).

## ✅ 2026-10-21 — tanda «Entorno + Espacio aéreo + Cumplimiento» **desplegada** (`c4c6b85`)

`p340` corre **`c4c6b85`**, desplegado el 2026-10-21 en bloques (leído de la salida pegada): estado (`## main...origin/main`, `738a317`), respaldo (`aero_ops_20261021_084027.sqlite3`, `restorable.`), `git pull` (`738a317..c4c6b85`) + `migrate` (`airspace.0001_create_airspace_snapshot_and_feature`, OK), `collectstatic` (7 copiados, 243 sin cambio), reinicio (`active`, hash `c4c6b85`), `health: 200`, `bootstrap_roles` (cinco roles y el grupo Dirección) e `import_airspace_zones --url` (dry-run: «Would add 572»; real: **«Added 572, changed 0, archived 0»**, 31 avisos de calidad de la fuente: 9 aeródromos sin OACI y nombres duplicados). Sin `uv sync` (el diff no tocó `pyproject.toml` ni `uv.lock`).

**Seguimiento — fusionado sin desplegar: nada.** Queda por revisar a mano en producción, con recarga forzada: la sección «Entorno» (menú, pestañas Tiempo, Centelleo GNSS y Espacio aéreo), la franja «Entorno hoy» del panel, la escena del cielo (siete fases y los dos temas), el mapa con los 572 elementos reales (rendimiento, íconos, FIR, teclado) y la sección «Cumplimiento» al final del panel (también a 375 px). El tiempo salió **encendido por omisión**: comprobar que `p340` llega a `api.open-meteo.com` y que la tarjeta no muestra el estado de error.

Detalle de la tanda (ya desplegada):

**Qué entró**
- **Sección «Entorno»** (`LV-358`, E1 a E3): pestañas Tiempo y Centelleo GNSS por ruta (`/environment/`), cabecera común (una sola ciudad, hora de Chile, amanecer/puesta y un solo «Referencial»), franja «Entorno hoy» en el panel por htmx (reemplaza las dos tarjetas), banda del centelleo sobre las 24 h del tiempo y celda de espacio aéreo. El tiempo viene **encendido por omisión** (`LV-353`) y el centelleo desde la puesta de sol (`LV-354`); la escena animada del cielo está en la pestaña Tiempo (`LV-356`).
- **Espacio aéreo y aeródromos** (`LV-357`, fases 1 a 3): app `apps/airspace` (catálogo importado del mapa «ZONAS SENSIBLES» que entrega la DGAC; los datos viven en la base, no en git), comando `import_airspace_zones`, y la pestaña `/environment/airspace/` con mapa, buscador, capas propias («Mis faenas», «Permisos vigentes»), medición y ficha. Referencial: confirmar con AIP/NOTAM. **Incluye un arreglo de seguridad** (rótulos de Leaflet como nodos, no HTML).
- **Cumplimiento en el panel** (`LV-359`, fases 1 a 4): sección al final cargada por htmx (anillos, mapa de calor a 90 días, alertas por antigüedad, tabla de permisos por faena ordenable —se mudó del panel—, historial de revisión y guía de lectura).
- **Propuesta de Informes** (`LV-355`, solo documentación en `docs/dev/informes-optimizacion.md`; sin código).

**Seguimiento — fusionado sin desplegar: todo lo anterior.**
- **LLEVA MIGRACIÓN:** `airspace.0001_create_airspace_snapshot_and_feature` (única; las otras apps no cambian).
- **LLEVA ESTÁTICOS:** sí (`identity.css`, `airspace.css`, `airspace-map.js`, `airspace-search.js`, `sky-preview.js`, `weather-card.js`, `icons.svg`) → `collectstatic` obligatorio.
- **LLEVA `.mo`** (versionado; no hace falta `compilemessages`).
- **Después del `migrate`, en la VM:** `manage.py bootstrap_roles` (da `view_airspacefeature` al rol Operations) y `manage.py import_airspace_zones --url` **leyendo la salida** (agregado/cambiado/archivado y avisos de calidad; ≈572 elementos). Sin esa carga la pestaña muestra el estado vacío con la guía.
- **Ojo con `WEATHER_ENABLED`:** ahora es `True` por omisión, así que al desplegar la tarjeta del tiempo **se enciende** y `p340` consultará `api.open-meteo.com` (riesgo de licencia aceptado por la persona, ver `docs/dev/tiempo.md`). Verificar que la VM sale a Internet y que `/etc/aerocontrol.env` no fije `WEATHER_ENABLED=False` si no se quiere.
- Usar `scripts/deploy.sh --dry-run` primero; plan con `deploy_plan.ps1 -From <hash de la VM>`.

**No verificado en navegador (el navegador integrado no compone):** la apariencia de la escena del cielo (siete fases, claro y oscuro), la franja, la banda del centelleo, el mapa con datos reales (rendimiento con ~572 elementos, íconos de avión, FIR, teclado y lector de pantalla), la sección de Cumplimiento (el disparo real de `revealed` al desplazarse, `<meter>`, chips, tema oscuro y móvil). Hace falta una mirada humana antes o justo después de desplegar.

**Pendiente — del usuario**
- Confirmar quién mantiene el mapa y su licencia (se asumió oficial de la DGAC por su confirmación del 2026-10-20) y, si el AIP-Chile (ENR 5.1, `aipchile.dgac.gob.cl`) publica las zonas de forma estructurada, usarlo como origen.
- Validar el texto de la guía de Cumplimiento sobre las escalas 30/60 días de permisos («renovar un permiso implica una solicitud a la DGAC, que demora más»).
- Informes (`LV-355`): decidir lo de la sección 7 de `docs/dev/informes-optimizacion.md` (menú, si gráficos y cambios entran al papel DGAC, PDF en servidor, sello, inglés) antes de implementar F0 en adelante.
- Los pendientes de la entrada de abajo siguen vigentes (GitHub Support, rotar SSH/Tailscale, NVIDIA, licencia de Open-Meteo, lectura de nombres sueltos).

**Pendiente — del código:** `dashboard()` no acota por tenant (`permit_status_by_cost_center(today)` sin `user`; hoy hay un solo tenant) y `upcoming_expirations` tampoco; «pronóstico en este punto» del mapa; capa de planes/solicitudes en «Permisos vigentes»; mover los archivos de geometría de `apps/geo` a `apps/airspace`; cadenas huérfanas de la tarjeta GNSS retirada en el `.po`; mover `Próximas mantenciones` (queda sola en media fila en el panel); reforzar con una prueba el dibujo del relleno con patrón del mapa; las fases F0 a F5 de Informes.

## ✅ 2026-10-20 — historial reescrito y publicado, VM resincronizada y tanda de cierre **desplegada** (`738a317`)

`p340` corre **`738a317`** (leído de la salida pegada, junto con `active` y `health` 200; el primer chequeo dio 000 por la carrera del arranque, el siguiente 200). Se desplegó por bloques tras respaldar la base (`aero_ops_20261020_075452.sqlite3`, `restorable.`): `fetch --force` + `checkout -B main origin/main` + `reflog expire` + `gc --prune=now` (la VM ya no conserva el historial viejo), `uv sync --no-dev`, `migrate` (`assistant.0002_assistantusage_vote`, `weather.0001_user_weather_location`), `collectstatic` (3 copiados) y reinicio.

**Historial de git reescrito y publicado el 2026-10-20** (`LV-349`): `git filter-repo` sobre todo el historial (valores reales → ficticios, autores → noreply de GitHub), `main` en `738a317` y los 6 tags con SHAs nuevos; el remoto tiene solo `main`. **Todos los hashes anteriores cambiaron.** La copia local se limpió (ramas, worktrees, stash y `gc`; 999 commits, todos del historial nuevo). Respaldos con los datos originales en `D:\respaldos` (fuera de cualquier repo; la persona decide cuándo borrarlos). Las `refs/pull/*` de GitHub no se pueden reescribir: **los SHAs viejos siguen accesibles por URL hasta que GitHub Support los purgue** (texto listo en `scratchpad\rewrite\SUPPORT_GITHUB_FINAL_ES.txt` y `_EN.txt`).

**Todo lo nuevo viene APAGADO en producción:** el asistente (`AI_ASSISTANT_ENABLED` y `AI_ASSISTANT_ALLOW_PRODUCTION`), la tarjeta del tiempo (`WEATHER_ENABLED`) y el botón de copiar (`AI_ASSISTANT_ALLOW_COPY`). Lo único visible: el expediente operativo ya no muestra «Revisión meteorológica» (`LV-344`, paso 1).

**Seguimiento — fusionado sin desplegar:** sólo este `HANDOFF` (documentación).

**No verificado en navegador:** tarjeta del tiempo, panel del asistente abierto, voto y copia, menú «⋯» y fondos de módulo en tema claro (el navegador integrado no compone animaciones ni cambia el tema), y que el expediente ya no muestre el renglón meteorológico en producción (comprobación visual de la persona, con recarga forzada).

**Pendiente — del usuario**
- Enviar a GitHub Support el texto de purga (completar el contacto), reactivar la protección de `main` si se desactivó para el empuje, y rotar el acceso SSH de la VM y revisar los accesos de Tailscale (el usuario y el host estuvieron publicados).
- Asistente en producción: la llave y la licencia de NVIDIA (confirmar los cinco puntos de `docs/dev/asistente-ia.md`), luego activar `AI_ASSISTANT_ENABLED` y `AI_ASSISTANT_ALLOW_PRODUCTION`, `assistant_probar --ping` y `--eval`.
- Tiempo: la licencia comercial de Open-Meteo (plan de pago o servidor propio) antes de encender `WEATHER_ENABLED` en producción; confirmar que `p340` sale a Internet; elegir la ciudad por omisión.
- Pie de los informes: queda con los datos genéricos del repositorio (decidido).
- Una lectura humana rápida de `MASTER_PLAN.md` y `handoff-archive.md` por si quedó un nombre de persona suelto (la detección de nombres de la reescritura fue heurística).

**Pendiente — del código:** paso 2 de `LV-344` (retirar la revisión meteorológica del plan geoespacial y del panel; condición de cierre en la fila), ola J (movimiento con propósito), menú «⋯» en las demás listas, reglas nuevas de ruff (533), chips de SIGO/mantenciones sin filtro de faena, alertas y bandeja en la ola de legibilidad, informes con `.page-header` propio, densidad por tabla, y el escaneo de nombres sueltos en la historia (heurístico).

## ✅ 2026-10-16 — rediseño de barra y panel, asistente con tope, Django 6.1.2, **desplegados** (`a807eb8`)

`p340` corre **`a807eb8`**, desplegado el 2026-10-16 en cuatro bloques (estado → entorno → `git pull` + `uv sync` → `collectstatic` + reinicio;
135 estáticos copiados, servicio `active`, hash leído de la salida pegada). **Sin migración** (la última sigue siendo `compliance/0027`).

**Seguimiento — fusionado sin desplegar: sólo documentación** (`LV-311` skill `pendientes-github`, `LV-314` recorte de skills; no afectan a producción) y `LV-327` (`scripts/deploy.sh`, sin migración ni estáticos; **sin probar aún en la VM**: el primer uso conviene con `--dry-run`).

Entró: `LV-307` (portada de dos paneles, tarjetas con barra, tipografía Archivo), `LV-308` (asistente: tope por usuario y hora, mensajes de límite/llave),
`LV-309` (barra lateral: un grupo abierto, activo con luz, nombres al enfocar), `LV-310` («Requiere atención», «Próximas mantenciones» en vez de la dona,
estados por texto), `LV-312` (cabecera con fondo aeronáutico propio y chips con acción) y `LV-313` (Django 6.1.2).

**Pendiente — del usuario**
- **`REPORT_CONTACT_ADDRESS` y `REPORT_CONTACT_WEB`** no están en `/etc/aerocontrol.env` (se quitaron el 2026-10-16 para no imprimir marcadores): los informes salen con los textos de ejemplo hasta que se fijen los reales.
- Revisar en producción con recarga forzada: portada, barra, panel (con y sin faena elegida) y la ficha de un informe impreso.
- Decisiones de skills: `lecciones.md`, `rumbo-1.0.md`, `despliegue-p340.md` y `AGENTS.md` l.236 (ver PR de `LV-314`).
- Ramas respaldadas en el remoto, a revisar: `codex/skill-aerocontrol`, `codex/t1-4-auditoria-visible`. Dependabot #93, #29 y #23 pedidos a recrear.
- Siguen los del 2026-10-13: limpiar o no el historial de git, probar el asistente en el demo con la llave propia, PDF real de la DGAC.
## 2026-10-13 — identidad visual, asistente con IA (prototipo), privacidad y estándar de trabajo (desplegados en `59e5ac6`)

`p340` corre **`59e5ac6`**, desplegado el 2026-10-13 por tandas (`ac173f3` → `dd66b63` → `b4f2372` → `59e5ac6`; cada
una con `git pull`, reinicio y `git log` = hash de `main`, leído de la salida pegada). Las dos de en medio llevaron
`collectstatic` (13 y 7 archivos); ninguna lleva migración (la última sigue siendo `compliance/0027`, del 2026-10-08).
El plan lo calcula `deploy_plan.ps1 -From <hash de la VM>`, y **el primer paso es leer el hash de la VM**: otra sesión ya
desplegó entre medias una vez.

**Seguimiento — fusionado sin desplegar: nada.**

Entró: `LV-298` («Registro de operaciones» con los rótulos del portal), `LV-299` (subir la autorización de la DGAC saca
las fechas del PDF), `LV-300` (la habilitación escrita en la ficha del operador cumple por **serie**), `LV-301` (la lista
de permisos abre con los últimos generados), `LV-302` a `LV-304` (**identidad visual**: capa global `identity.css`,
ilustraciones de AeroAcademy en estados vacíos y portada, dibujo de la aeronave por serie con hélices que giran, panel
lateral), `LV-305` (**asistente de consulta con IA, prototipo sólo demo**: en producción no existe), `LV-306` (datos
personales reales fuera del repositorio público) y el PR #86 (estándar de trabajo: `CLAUDE.md`, skills `orquestar` y
`revision-privacidad`, y el **escáner de privacidad** `tools/kit/privacy_scan.py` en el CI **y** en `scripts/verify.ps1`).

**Comprobado en producción tras el despliegue (2026-10-13):** `/assistant/` → **404** (el asistente no existe allí, como debe) y
`/health/` → **200**.

**Hecho en producción sin código (2026-10-08):** instalados los timers `letters`, `watchdog` y `verifybak` (15 timers
`aerocontrol-*`) y **apagada la regla** «Permisos: renovación vencida de plazo (T-15 · Gerencia)» (`enabled=False`); sus 3
alertas ya estaban cerradas desde el 2026-10-07.

**No verificado en producción:**
- La lectura del «Rango de fecha autorizado» de un PDF **real** de la DGAC (el patrón sale de una captura; si no lo lee, la
  aprobación sigue pidiendo las fechas a mano).
- «Registro de operaciones» con una operación real y una aeronave (en el demo ningún permiso las tiene; el alta la cubren las
  pruebas, no se vio en pantalla).
- La identidad visual **en pantalla ancha**: se revisó en un panel angosto (la portada y la ruta del panel sólo aparecen ≥ 768 y
  ≥ 1100 px).
- **El asistente contra el servicio real de NVIDIA:** las pruebas usan un cliente falso y no hubo llave en la sesión.
- El hemisferio de Punto Centro contra el portal, y si se corrió `scripts/activar-sync-baterias.sh` (de otra sesión).

**Pendiente — del usuario**
- **Decidir si se limpia el historial de git** (`LV-306`): los cinco RUT y los correos reales **siguen en commits anteriores**
  del repositorio público; borrarlos del código no los saca de ahí. Reescribir historia compartida no se hace sin su orden.
- **Probar el asistente con su llave del Developer Program** (`docs/dev/asistente-ia.md`; la llave sólo en su terminal, nunca en el
  chat ni en el repo). Ese acceso es sólo para prototipos: **producción exige licencia o alojar el modelo**.
- **Fotos de equipos con derecho de uso** en `static/img/equipment/<serie>.webp` (hoy hay dibujos propios; no se usan imágenes de
  buscadores ni de DJI).
- **Captura de Punto Centro del portal real** (lat/lon visibles), para decidir si la casilla «Hemisferio» se quita o se queda.
- **`T1.4` paso 3**: encender `AUDIT_FAIL_CLOSED=True`, **sólo tras una semana con la marca de fallos de auditoría en cero** y
  midiendo antes con `scale_readiness`.
- **Correo** (de lado a pedido del usuario): `EMAIL_HOST` y `SITE_BASE_URL`; sin eso ningún aviso sale.
- Dejados como están a pedido del usuario: responsable en 11 de 15 faenas, `CC716`, `LV-150` y `LV-228`.
- Decisiones de contenido del rediseño: un pie del panel lateral con usuario y resumen vivo, y los seis ítems retirados del menú
  (`docs/ux-ui-plan.md` §1); fase siguiente (fichas de detalle de documentos y solicitudes SIGO, formularios, informes impresos).
- Si un permiso aprobado debe contar como vigente desde la aprobación y no desde su fecha de inicio: cambia una cifra firmada y
  **no** se decidió (`LV-258`, `LV-296`).

**Pendiente — del código, sin decisión nueva**: ninguno. Lo que queda en `MASTER_PLAN.md` (`T1.1`, `T1.2`, `T1.5`, `T3.5`,
`X.4`, `X.5`, `LV-233`, `LV-245`) espera una decisión, es un refactor grande o depende de AeroLink, y el proyecto está en pausa
de estabilización.

## ✅ 2026-10-07 — modalidades SIGO, orden por columna, colores, prevuelo, auditoría, **desplegados** (`186dffb`)

`p340` corre **`186dffb`**, desplegado el 2026-10-07 por tandas (`97e2f35` → `120f5c8` → `ea480af` →
`b02d84e` → `23e7b48` → `186dffb`; cada una con `git pull`, reinicio y `git log` = hash de `main`, leído
de la salida pegada). Tres migraciones, cada una con respaldo `verify_backup` = *restorable* antes:
`operations/0030` (`area_modality`, `vertices`), `operations/0031` (`approx_flight_minutes`) y
`operations/0032` (el chequeo prevuelo sin vuelo). Entró: `LV-277` (el centro sigue a la circunferencia y
el arrastre vuelve a guardarse), `LV-278` bloques A y B (Punto Centro, Corredor, Triangular,
Cuadricular; la hoja sigue el portal), `LV-279` (números cerrados), `LV-280` (orden por columna),
`LV-281` y `LV-284` (panel: «Esperando» en naranja; menú sin «¿Puedo volar?» ni «Vuelos»), `LV-282`
(color por capa), `LV-283`, `LV-286` (meteorológica informativa), `LV-287` (el permiso no pasa del
seguro), `LV-288` (el orden se conserva al filtrar, vacíos al final, «Estado» por lo que se ve),
`LV-238` (el chequeo prevuelo antes de volar), `T1.4` pasos 1 y 2 (el fallo de auditoría se ve, y la
auditoría atómica **apagada por omisión**) y `LV-289` (la skill `/terminar-bloques`).

**Seguimiento — fusionado sin desplegar: nada.** (Regla desde 2026-10-07: se fusiona bloque tras bloque y
se despliega **una vez** al final; ver `AGENTS.md` «Despliegue por tandas». Cuando algo quede fusionado
sin desplegar, va **aquí**, con qué lleva migración y qué lleva estáticos; los comandos justos los escribe
`.claude/skills/terminar-bloques/scripts/deploy_plan.ps1 -From <hash de la VM>`.)

⚠️ **Ojo con `LV-287`:** los permisos solicitados ya guardados que pasen del seguro de sus aeronaves no se
rompen, pero fallarán al editarlos hasta corregir la fecha.

**No verificado en producción** (se comprobó con pruebas y en el demo, no en `p340`): el arrastre con el
ratón real del editor y el clic sobre el selector de color; la hoja de SIGO contra el portal real; el
rojo/naranja de «Esperando» a ojo; el chequeo prevuelo antes del vuelo (pantallas y adopción) y la
pantalla «Cambio no guardado», que sólo aparece con `AUDIT_FAIL_CLOSED` encendido. Y `LV-273` sigue sin
ejercitarse allí (aún no hay solicitudes de vuelo reales: ahora, al separar un plan, se crean con
modalidad).

**Pendiente — del usuario**
- **`T1.4` paso 3**: **encender `AUDIT_FAIL_CLOSED=True`** en `/etc/aerocontrol.env` (decidido
  fail-closed el 2026-10-07; el paso atómico ya está en el código, apagado), **sólo tras una semana
  con la marca de fallos de auditoría en cero** y midiendo antes con `scale_readiness`.
- **Correo** (de lado a pedido del usuario): `EMAIL_HOST` y `SITE_BASE_URL`; sin eso ningún aviso sale.
- **Timers** `letters`, `watchdog` y `verifybak`: el bloque está en `docs/scheduled-operations.md`.
- **Apagar la regla** «Permisos: renovación vencida de plazo (T-15 · Gerencia)».
- **Responsable** en 11 de 15 faenas; **`CC716`** (contrato cerrado con el permiso `JEJ-2026-003` vivo
  hasta el 28-10); **`LV-150`** (decisión vencida el 2026-09-30); **`LV-228`** (cuatro operadores sin
  faena: Rubén Herrero Mena, Nadia Rubio Mena, Julián Patricio Aranda Muñiz y Daniel Vera Vera).
- Los textos de ayuda de los «?» del portal de SIGO, sólo si se quieren copiar a la app.

**Pendiente — del código, sin decisión nueva**: ninguno. Lo que queda en `MASTER_PLAN.md` (`T1.1`,
`T1.2`, `T1.5`, `T3.5`, `X.4`, `X.5`, `LV-231`, `LV-238`, `LV-233`, `LV-245`) espera una decisión, es un
refactor grande o depende de AeroLink, y el proyecto está en pausa de estabilización.

## ✅ 2026-10-06 — insignias, historial de permisos y solicitudes, CI y skills, **desplegados** (`05f5e2c`)

`p340` corre **`05f5e2c`**, desplegado el 2026-10-06 (`git pull` `66bc664..05f5e2c`, reinicio,
`git log` = `05f5e2c`, `systemctl is-active aerocontrol` = `active`). Entró: `LV-268` (guardián de
permisos), `LV-269` (insignias ámbar con niveles de severidad), `LV-270` y `LV-273` (historial de
permisos y de solicitudes, atómico), `LV-271` (el CI vuelve a poder estar verde), `LV-272` (las
cuatro skills de flujo) y el plan de `T1.3`/`T1.4`. **Comprobado en producción**: el historial de un
permiso real pasó de 3 a 4 filas dentro de la transacción y volvió a 3 al deshacerla. `LV-273` no se
pudo ejercitar allí: todavía no hay solicitudes de vuelo en producción (la cubren sus 8 pruebas).

## ✅ 2026-10-05 — PDF, confirmación única, revisión previa, regla de faenas y alertas, **desplegados** (`66bc664`)

`p340` corre **`66bc664`**, desplegado el 2026-10-05 (`git pull` `c1ed293..66bc664`,
reinicio, `git log` = `66bc664`). Lo que entró:

| Fila | Qué |
|---|---|
| deps | `pypdf` 6.19.0 y `urllib3` 2.8.0 (avisos de `pip-audit`). |
| `LV-263` | Botón **«Descargar PDF»** en el informe mensual y en el Dato Ejecutivo; impreso, 5 páginas y 1. |
| `LV-264` | Los botones con confirmación preguntaban **dos veces**; ahora una. |
| `LV-265` | Bloque **«Revisar antes de emitir»** en el informe (sólo pantalla). |
| `LV-266` | Regla única: una faena **cerrada o sin operación no entra en los registros**; el resumen de vencimientos deja de escribirle a las cerradas. |
| `LV-267` | **Alertas.** El resumen cae en Dirección si la faena no tiene responsable; los avisos a Dirección **ya no se pierden si un miembro no tiene correo** (ocho comandos); `check_client_letters` escribe a Dirección lo que escala y queda registrado. |

⚠️ **Dos despliegues de esta jornada "parecieron" correr sin el `git pull`**
(`collectstatic` copió 0 archivos y el `git log` seguía en el hash viejo). La
prueba de que llegó es siempre el hash final de `git log --oneline -1`.

### Falta, y es del usuario (sin código)

- **`EMAIL_HOST` y credenciales** en `/etc/aerocontrol.env`: hoy **ningún correo
  sale** (cuatro trabajos terminan «NO ENVIADO (correo sin configurar)»).
- **Instalar los timers `letters`, `watchdog` y `verifybak`**: el bloque está en
  `docs/scheduled-operations.md`. El vigilante no corre desde el 2026-08-17.
- **Apagar la regla «Permisos: renovación vencida de plazo (T-15 · Gerencia)»**
  (`LV-232` la mandó retirar; sigue activa con 3 alertas).
- **Poner responsable** a las faenas sin destinatario (11 de 15 el 2026-10-05).
- **`CC716`**: contrato cerrado con el permiso `JEJ-2026-003` vivo hasta el 28-10;
  reabrir el contrato o cerrar el permiso.
- Una contraseña quedó tecleada como comando en la terminal de `p340` el
  2026-10-05; el historial se borró con `history -c && history -w`.

## Historia

Las entradas anteriores (diseño del plan de mejora, incidentes, despliegues pasados, ramas resueltas) están en [docs/dev/handoff-archive.md](docs/dev/handoff-archive.md). **Cada despliegue deja una entrada nueva al principio de este archivo**; cuando ya no describa lo que corre en `p340` ni algo pendiente, se mueve al archivo.

## Punteros

| Para | Ir a |
|---|---|
| Trabajo pendiente y orden | `MASTER_PLAN.md` → "Rumbo a 1.0" |
| Contrato de trabajo + gotchas verificados | `AGENTS.md` |
| Cómo se resuelve una alerta (operación) | `docs/compliance-setup.md` |
| Diseño de las cláusulas ISO abiertas | `docs/dev/iso-r7-design-plan.md` |
| Contrato con AeroLink | `docs/dev/adr-0002-coexistencia-aerolink.md` |
| Plan de integración con AeroLink | `docs/dev/plan-integracion-aerolink.md` |
| Runbook de la VM | `docs/dev/ubuntu-vm-deploy.md` |
| Trabajos programados | `docs/scheduled-operations.md` |
| Qué cambió y cuándo | `CHANGELOG.md`, `git log` |
| Skill del proyecto (retomar sin leer 5000 líneas) | `.claude/skills/aerocontrol/` |
| Historia de este archivo | `docs/dev/handoff-archive.md` |
