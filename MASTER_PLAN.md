# MASTER_PLAN — AeroControl

> **Fuente única de verdad del trabajo pendiente.** Consolida la auditoría técnica ([AUDIT_CLAUDE.md](AUDIT_CLAUDE.md)) y el plan de producto que el usuario aportó (`PLAN_CLAUDE_CODE.md`, integrado el 2026-07-24 como los BLOQUE 0-4 de la sección "Bloques de producto" más abajo) en un único tablero ejecutable con seguimiento de estado.
> **Creado:** 2026-07-24 · **Rama base de referencia:** `main` (25 commits por detrás de `codex/impeccable-ui-audit`).
> **Regla de oro:** este proyecto está en **pausa de estabilización**. No se incorpora DJI Cloud API (T6.7) ni funcionalidad fuera de lo listado aquí. Los BLOQUE 1-4 de producto sí están autorizados a avanzar sin esperar el cierre completo de FASE 1-3 (solo con las dependencias puntuales que cada tarea declara, p. ej. B1.1→T3.1). Un bloque no empieza hasta que sus dependencias declaradas estén ✅.

---

## Cómo usar este documento

Es el **tablero de bloques**. `BACKLOG.md` queda como registro histórico de lo entregado; este archivo manda para lo que viene.

**Leyenda de estado:**
`⬜ Pendiente` · `🔄 En progreso` · `✅ Hecho` · `⛔ Bloqueado` (esperando una dependencia) · `⏸ Diferido` (YAGNI, no ahora) · `↪ Consolidado` (fusionado en otro bloque, ver referencia)

**Ciclo por tarea (disciplina anti «prompt gigante»):**

1. Tomar la **siguiente tarea no bloqueada** de mayor prioridad del tablero.
2. Rama pequeña `codex/<area>` (una intención por rama; ver `AGENTS.md` — no usar `feat/...`).
3. (Opcional para cambios grandes) crear un change en `openspec/changes/<id>/` con `proposal.md` + `tasks.md`.
4. Implementar. Ejecutar el gate: `pwsh scripts/verify.ps1` **debe** pasar (ver T0.3 — hoy no falla; arréglese primero).
5. Revisión (Claude Code) contra el criterio de aceptación de la tarea.
6. Marcar la casilla aquí (`⬜`→`✅`), actualizar `BACKLOG.md`/`CHANGELOG.md` si corresponde, commit con Conventional Commits, PR.

**Reparto de roles:** Claude Code diseña/revisa (arquitectura, specs, criterio de aceptación, segunda opinión); Codex implementa tarea-a-tarea. Ver §"Reglas de trabajo con agentes".

**Trazabilidad:** cada tarea referencia su evidencia en `AUDIT_CLAUDE.md` (sección o ID de hallazgo F-xx) y los archivos concretos.

---

## Rama de trabajo

`codex/stabilization-blocks-0-6` — contiene la auditoría, los bloques 0/1/2/4-parcial/6.1-6.2, y el **merge de la línea paralela** de `codex/impeccable-ui-audit` (commit `29d9d43`: traducciones de permisos y asignaciones, filtros de estado y «necesita revisión», docs de respaldo, chequeo de calidad de datos). 259 tests verdes, cobertura 88.45%.

Aún **no mergeada a `main`**. Ver TL.6.

### Dónde retomar

La ruta obligatoria del plan externo está **completa**, y también los dos
bloques grandes de producto que le siguieron: **BLOQUE GEO** (MVP GEO-0..GEO-10
+ el quick-win GEO-0b) y **BLOQUE OPS** (OPS-0..OPS-8) están cerrados. Lo que
queda ya no es ruta automática: cada ítem exige o una **decisión de negocio** o
una **instrucción explícita**. Orden recomendado de lo pendiente:

**Orden vigente acordado con el usuario (actualizado 2026-07-30):**

1. **Ronda de revisión en vivo (LV-1..LV-10)** — ✅ cerrada salvo LV-6 (Gantt,
   en standby). Ver la sección "Revisión en vivo 2026-07-30" abajo.
2. **BLOQUE 4** (B4.3/B4.4 habilitaciones + compatibilidad) — ✅ completo.
3. **GEO V2** — **siguiente foco**. El usuario quiere revisarlo a fondo (está
   en operación y le interesa) antes de decidir los ítems diferidos (GEO-12b
   edición de ExtendedData, GEO-13b StyleMap/XSD, GEO-14 hooks DJI). Arrancar
   con una **revisión del estado actual + propuesta de diseño** de lo que
   quede por hacer, no implementar a ciegas.
4. **Deuda de arquitectura** — después de GEO V2: T3.2 (tenancy, el bloqueador
   real, XL) y el resto de FASE 1/4 y R.10/T5.1.
5. **Cargar más datos reales / activar cumplimiento** — decisión de negocio del
   usuario, en paralelo cuando quiera (guía en docs/compliance-setup.md).

*(Orden anterior 2026-07-29: GEO V2 y/o bloques diferidos con propuesta de
diseño primero; carga de datos al final. Se conserva la disciplina de "diseño
antes de implementar" para todo lo diferido.)*

**Cerrado el 2026-07-29 (bloque de seguridad V.10-V.12 completo):** GEO-0b
(auditoría trazable + handler de error del Kanban), V.11/T5.9 (vendorización +
SRI, orígenes a `'self'`), V.10 (JS inline extraído a `static/js/` + CSP
enforcing por entorno + `report-uri` con endpoint) y V.12 (sesión que expira al
cerrar navegador + tope 12h + deslizante, cambio de contraseña en la app).
También **TL.7** (los 5 PRs de Dependabot: crispy stack, ruff, checkout/setup-uv)
y el runbook de despliegue en VM ([docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md)).

> **Decisión registrada (V.10):** se **descartó añadir `django-csp`** (que el
> plan nombraba) y se endureció el middleware CSP hecho a mano. Razón: tras
> V.11 (todo `'self'`) y la extracción del JS inline, no hay `<script>` inline
> → no se necesitan nonces, que es lo que `django-csp` aportaría. La
> dependencia habría sido churn (reescribir la política a su formato 4.x,
> cambiar middleware) sin beneficio, contra el "local-first" del repo. El
> único `'unsafe-inline'` restante es `style-src`, para atributos de estilo y
> el `<style>` del login — riesgo bajo, no justifica nonces de estilo.

La revisión V.1-V.39 está **completa** salvo V.3 (⛔ T3.2). La tanda E se
ejecutó el 2026-07-25 con el alcance que eligió el
usuario: archivar/restaurar desde la UI con confirmación de dependientes en
centros de costo, aviso del digest para CC archivados con dependientes,
estados vacíos con CTA, tarjeta de cumplimiento en el dashboard, regresos
reales en vez de history.back(), y el dedupe responsive.

*(Cerrado antes: T2.3/T2.4 `c5d22dd`/`3611d06`, TIME_ZONE America/Santiago
`b24fbea`, R.10 tokens `8bdda97`, TL.6/TL.11 con tags y poda ejecutados.)*

**Release `v0.3.0-alpha`** (2026-07-27): cierra todo lo anterior más la
revisión V.1-V.39 (seguridad, estabilidad, desempeño, tanda E de UX). El tag
apunta al commit que cierra esta sección del `CHANGELOG.md`, no a `ff9d6db`.

Más adelante, y con más peso: **T3.2** (clave de tenancy) es el bloqueador real
de la centralización y de DJI, y es barato ahora frente a hacerlo con datos
acumulados.

### Estado de la base de datos real (2026-07-24)

La base de trabajo (`DB_PATH` en `.env`) estaba **14 migraciones atrás**: el
campo `responsible_operator` y la tabla `JobRun` no existían, así que ni el
resumen de vencimientos ni el informe ejecutivo ni el registro de tareas
programadas podían funcionar en la instalación real, aunque el código estuviera
completo. Migrada el 2026-07-24 con copia previa del `.sqlite3`; datos intactos
(11 centros de costo, 41 operadores, 14 aeronaves). `bootstrap_roles` aplicado:
los cinco roles más el grupo *Dirección*.

**Nota para futuras sesiones:** el comando `backup` no sirve como red de
seguridad *antes* de migrar, porque registra su ejecución en `JobRun`. Si esa
tabla falta, copia el archivo `.sqlite3` a mano.

Pendientes que requieren una decisión de negocio, no del agente:

- Asignar **Operador responsable** en los 11 centros de costo
  (`/registry/costcenter/<id>/edit/`). Hoy los 11 están sin asignar; los 41
  operadores tienen correo, así que solo falta decidir quién.
- Agregar usuarios al grupo *Dirección*. Hoy existe **un solo usuario** (`root`)
  en todo el sistema, así que el informe ejecutivo llegaría solo a esa cuenta.
- No hay documentos ni reglas de alerta cargadas (0/0): el resumen diario no
  tiene nada que enviar hasta que exista documentación con vencimientos. El
  **catálogo de tipos de documento ya está sembrado** (`seed_document_types`,
  2026-07-30, ver abajo) — falta cargar documentos reales y crear las reglas.

### Puesta en producción real: VM `p340` (2026-07-29/30)

La app pasó de "corriendo en local" a **desplegada y operando** en una VM
Ubuntu (`p340`, accesible por Tailscale, runbook en
[docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md)):

- **Datos reales cargados**: los 11 CC / 41 operadores / 14 aeronaves de la
  base de trabajo se exportaron e importaron a la VM (la VM había arrancado
  como instalación nueva, vacía).
- **Login endurecido con `django-axes`** (T2.5, `fea3f3c`) antes de exponer la
  app a internet.
- **Acceso público vía Tailscale Funnel** (`https://p340.tailccd107.ts.net`,
  procedimiento en [docs/dev/funnel-public-access.md](docs/dev/funnel-public-access.md))
  para permitir acceso a colaboradores sin Tailscale propio, mediante cuentas
  individuales (no compartidas) creadas en `/admin/`.
- **Operación programada con systemd timers** (no cron):
  `generate_alerts` 06:00, `send_alert_digest` 07:00, `backup` 22:00 — ver
  [docs/scheduled-operations.md](scheduled-operations.md). Primer backup
  verificado.
- **Guía de activación del monitoreo de cumplimiento**:
  [docs/compliance-setup.md](docs/compliance-setup.md) (qué se puede vigilar,
  catálogo de tipos sugerido, reglas mínimas, orden de pasos).
- **Catálogo de tipos de documento sembrado** en la VM (`seed_document_types`,
  6 tipos, uno marcado `is_insurance` para LV-4 abajo).
- El fix de estáticos con SRI (`config/static_storage.py`, que vivía sin
  versionar solo en la VM) quedó versionado (`4e02396`).

### Revisión en vivo del usuario sobre la app desplegada (2026-07-30)

Con datos reales y la app públicamente accesible, empezó una ronda de
feedback de producto mirando la app funcionando (no solo el código). Ver
sección **"Revisión en vivo 2026-07-30"** más abajo en el tablero: **LV-1 a
LV-5 y LV-7 cerrados** (`6b9a9b7`) — catálogo de documentos sembrado con ayuda
de estado vacío, título autogenerado, campo de notas, columna de vencimiento
de seguro en Aeronaves, indicador de progreso al importar KMZ, y el enlace de
Kanban oculto del sidebar por decisión del usuario. **LV-6 (vista Gantt del
Kanban) queda en standby** hasta que se retome con una propuesta de diseño —
no implementar sin ese paso.

### Inventario de ramas (TL.6, cruzado el 2026-07-24)

**Orden obligatorio:** primero `git push origin main`, después la poda. Varias
ramas contienen commits que hoy solo existen en el `main` **local**; borrarlas
antes del push los deja inalcanzables en el remoto.

Redundantes, contenido preservado en `origin/main` o en su rama gemela:
`agent/aerocontrol-stabilization`, `codex/stabilization-foundation`,
`codex/integracion-estabilizacion`, `codex/chapter1-data`,
`codex/production-settings` (duplicado de `-clean`; `CONN_MAX_AGE` y
`SECURE_PROXY_SSL_HEADER` verificados en main), `codex/anonymized-snapshot`
(idéntica byte a byte a `-clean`).

Redundantes **solo después** del push de `main`: `codex/impeccable-ui-audit`
(línea paralela cerrada), `codex/backend-storage`,
`codex/production-settings-clean`.

Conservar — trabajo real no fusionado:

- `codex/anonymized-snapshot-clean` — export/import anonimizado, no está en
  main. Es la mitad del ítem **B-06** de `backend-follow-up.md`.
- `codex/supabase-cli-operations` — respaldo vía Supabase CLI. La otra mitad de
  B-06: `BACKLOG.md` sigue pidiendo probar Supabase con datos anonimizados, así
  que "local-first" no invalida esta rama.
- `codex/backend-remote-plan` — `backend-plan.md` de 120 líneas frente a las 73
  de `docs/dev/backend-plan.md` en main (la ruta cambió con TL.12, que es lo que
  hace parecer que ya está fusionada). Borrarla perdería 47 líneas de plan.
- `dependabot/*` (5) — son TL.7; borrarlas solo hace que se recreen. Dos están
  11 commits atrás y necesitarán rebase.

Ramas locales: borradas las cinco ya fusionadas, incluidas
`codex/ui-modernization` y `codex/documentacion-y-onboarding` (su único commit
`e3e3e9d` resultó estar en `main` textualmente idéntico en los tres archivos).
Quedan `main` y `codex/stabilization-blocks-0-6`.

### Anatomía de R.10 / T5.1 (medido el 2026-07-25)

`static/css/app.css`, 1052 líneas, tiene **dos sistemas de tokens completos**,
no un residuo:

| | Sin prefijo | `--ac-*` |
| --- | --- | --- |
| Definición | `:root` línea 655 | `:root` línea 897 |
| Reglas oscuras | líneas 412-654, 52 selectores | líneas 897-944, 20 selectores |
| Usos `var()` | 69 | **142** |

Los `--bs-*` no son una tercera generación: son variables de Bootstrap que el
proyecto sobrescribe, y se quedan.

**Por qué es la causa raíz de R.7:** 10 selectores están definidos en las dos
generaciones (`body`, `.sidebar`, `.sidebar a`, `.sidebar a:hover`,
`.sidebar a.active`, `.form-control`, `.form-select`,
`.form-control::placeholder`, `.table`, `.table-hover tbody tr:hover`). Misma
especificidad, así que gana la que va después: la de `--ac-*`. Son **18
declaraciones muertas** en la primera generación. Arreglar un color en
`--surface` o `--text-primary` no se ve en esos selectores, y no hay nada que
avise.

**Recomendación:** migrar a `--ac-*` y retirar los 10 tokens sin prefijo
(`--border`, `--light`, `--navy`, `--sidebar-width`, `--surface`,
`--surface-raised`, `--text-muted`, `--text-primary`, `--text-secondary`,
`--turquoise`). Gana por uso (142 vs 69) y por ser la generación que hoy
manda de hecho.

**No es una limpieza mecánica.** Los dos sistemas tienen *valores distintos*
para el mismo rol (p. ej. la superficie oscura), así que unificar cambia el
aspecto de algo sí o sí. Requiere revisión visual en el navegador, y 10 lugares
de `templates/` usan `var(--…)` directamente. Por eso quedó sin ejecutar cuando
se cerró T2.3/T2.4: el análisis está hecho, la decisión de paleta es del usuario.

### Revisión 2026-07-25 (V.*) — seguridad, estabilidad, desempeño y UX

Tres auditorías en paralelo sobre lo que AUDIT_CLAUDE.md no cubría o dejó
abierto. Ejecutadas por tandas: A seguridad (`03b4dbb`), B estabilidad
(`6d54237`), C desempeño (`b4a128f`), D quick wins de UX (`2f8fa42`).
La tanda E (UX mayor) requiere decisiones de alcance del usuario.

**Seguridad**

| ID | Estado | P | Hallazgo | Tanda |
|---|---|---|---|---|
| V.1 | ✅ | P1 | `WList` sin scope: `?export=csv` devolvía toda la tabla de tareas entre tenants (`workboard/views.py:47`) | A |
| V.2 | ✅ | P1 | `TaskEditView` sin `user_can_edit_board` y form que ofrecía todos los tableros: un viewer editaba, un editor secuestraba tareas a otro tablero | A |
| V.3 | ⛔ | P1 | F-05: `Document`/descarga sin ruta a tenant — **Document no tiene campo tenant**; bloqueado por T3.2, exige diseñar `content_object → tenant` | — |
| V.4 | ✅ | P1 | `/api-token/` sin throttle: `ObtainAuthToken` fija `throttle_classes=()` y esquivaba el default global. Ahora anon 10/min | A |
| V.5 | ✅ | P2 | `JobRun` nacía con `result="ok"` antes de ejecutar: un proceso muerto quedaba como éxito eterno. Estado `running` + migración | B |
| V.6 | ✅ | P2 | La ruta de error de `record_job_run` escribía dentro de la transacción condenada y enmascaraba la excepción real | B |
| V.7 | ✅ | P2 | `generate_alerts`: alerta y tarea en dos escrituras; un corte dejaba la alerta huérfana que la dedupe contaba como duplicado para siempre | B |
| V.8 | ✅ | P2 | `Alert.resolve()`/`reopen()` con dos `save()` sin transacción: alerta resuelta con tarea abierta | B |
| V.9 | ✅ | P2 | API PATCH sin `full_clean`: fecha malformada → 500; título de 10k chars persistía en SQLite y reventaría en PostgreSQL | reg. |
| V.10 | ✅ | P2 | CSP real. **V.11:** orígenes a `'self'` (sin CDN). **JS inline extraído** a `static/js/` (`theme-init`/`app`/`dashboard`/`calendar`/`kanban`); handlers inline (`onclick`/`onchange`/`onsubmit`) y los 4 `javascript:history.back()` reemplazados por mejora progresiva `data-*`; vars por `data-*`/`json_script`. **Enforcing:** corregido el bug por el que `CSP_REPORT_ONLY=False` borraba la cabecera — ahora emite `Content-Security-Policy` (enforcing) o `-Report-Only` según entorno, siempre una de las dos; `build_csp()` centraliza la política + `report-uri /csp-report/` con endpoint `CspReportView` (público, CSRF-exempt, solo loguea, cuerpo capado). Verificado en navegador **en modo enforcing** (`CSP_REPORT_ONLY=False`, demo :8012): Chart.js/htmx/Bootstrap cargan, chart renderiza, toggle de tema funciona, **cero violaciones de consola**. Default sigue Report-Only. | — |
| V.11 | ✅ | P2 | Bootstrap 5.3.3, htmx **2.0.10** (fijado; era el rango flotante `htmx.org@2.x` en unpkg), Chart.js 4.4.7, FullCalendar 6.1.15 y SortableJS 1.15.6 vendorizados en `static/vendor/` con SRI sha384 (patrón GEO-7). Es T5.9. Verificado en el navegador: CSP-gated Bootstrap CSS carga sin error de consola; los 6 archivos sirven 200 con bytes exactos. De paso encogí los orígenes del CSP a `script-src 'self'` / `font-src 'self'` (ya no hay CDN), adelanto de la parte "alinear orígenes" de V.10 | — |
| V.12 | ✅ | P2 | Sesión endurecida para dispositivos compartidos en terreno (decisión del usuario 2026-07-29): `SESSION_EXPIRE_AT_BROWSER_CLOSE=True` (cookie muere al cerrar navegador) + `SESSION_COOKIE_AGE=12h` (tope server-side pase lo que pase) + `SESSION_SAVE_EVERY_REQUEST=True` (expiración deslizante por actividad); los tres configurables por entorno. Cambio de contraseña dentro de la app (`PasswordChangeView`/`PasswordChangeDoneView` en `/accounts/password_change/`), enlazado en la barra de usuario, para no depender de `/admin/`. Verificado en navegador: la página renderiza traducida con los 3 campos y el enlace en el navbar. 4 tests | — |
| V.13 | ✅ | P2 | `StageCreate` explícito sombreaba al generado y perdió la validación de tablero; ídem checklist create/toggle | A |
| V.14 | ✅ | P3 | Escritura a storage dentro de `atomic`: el rollback dejaba ficheros huérfanos. Limpieza al fallar la transacción | B |
| V.15 | ✅ | P3 | Badge de alertas global sin `view_alert` (mismo contrato que T2.3) | A |

**Desempeño** (todo ✅ en `b4a128f`, salvo V.22 en `6d54237`)

| ID | Hallazgo |
|---|---|
| V.16 | Informe: `content_object` por alerta sin límite (500+ queries a 2 años) → lote por content_type, tope 200, y el filtro `cost_center` que se aceptaba y se ignoraba ahora filtra |
| V.17 | Buckets de vencimiento iterando documentos en Python por centro → un `aggregate` (límites verificados contra `bucket_for`) |
| V.18 | `checklist_completed` rompía el prefetch: un COUNT por tarjeta en cada render del tablero → cuenta las filas prefetcheadas |
| V.19 | `build_stage_data` re-consultaba por etapa (~18 queries fijas) → una query agrupada; test que fija el render en ≤6 queries |
| V.20 | Dashboard usaba `stage.tasks.count` en plantilla: un COUNT por etapa que además contaba archivadas y contradecía al gráfico de al lado |
| V.21 | Vencimientos del dashboard sin piso ni tope: listaba todo lo vencido histórico en cada login → [hoy, +30d], 10 filas, conteo real en el mosaico |
| V.22 | SQLite sin WAL ni timeout: el middleware de auditoría **ya estaba perdiendo eventos** en silencio con cada lock → WAL + busy_timeout 20s, verificado en la base real |
| V.23 | Índices de fecha ausentes en permisos/vuelos/mantenciones/asignaciones/habilitaciones + `__year/__month` (sin índice en SQLite) → `__range` |
| V.24 | Pares GenericFK sin indexar en `Document`, `Alert`, `KanbanTask.source` (Django solo indexa la mitad FK) |
| V.25 | `generate_alerts`: un EXISTS por candidato → set en una query; reglas de estado sin cota → acotadas a 1 año (sus alertas quedan abiertas, no se pierde nada) |
| V.26 | Feed del calendario aceptaba rangos arbitrarios (`?start=2020&end=2035` = 7 tablas en un JSON) → clamp 92 días |
| V.27 | Export CSV sin `select_related` ni streaming (~3 queries/fila, todo en RAM) → joins + `iterator()` + `StreamingHttpResponse` |

**UX**

| ID | Estado | Hallazgo | Tanda |
|---|---|---|---|
| V.28 | ✅ | Ver/Editar con 404 en 4 listas; tipos de documento y reglas de alerta **no se podían corregir nunca** desde la UI → flags de existencia + `ComplianceUpdate` con rutas | D |
| V.29 | ✅ | Centro de administración oculto tras `is_staff` mientras la página filtra por `view_*`: el encargado de cumplimiento no tenía cómo llegar a su propia configuración | D |
| V.30 | ✅ | No existe archivar/restaurar desde la UI (solo Django Admin); el filtro "Archivado" nunca devuelve nada útil | E |
| V.31 | ✅ | Archivar un centro de costo lo saca en silencio del digest y del informe; `notification_email` notifica a operadores archivados | E |
| V.32 | ✅ | Mensajes de transición `_(variable)` invisibles a makemessages (siempre inglés) + validaciones de `Assignment` en castellano en el código | D |
| V.33 | ✅ | Resolver/Deshacer perdían filtros y página; importadores aplicaban sin confirmación y el revert transaccional no estaba enlazado en ninguna parte | D |
| V.34 | ✅ | El arrastre del Kanban se apagaba en silencio con 3 de los 5 filtros: el JS conocía 5, el servidor 2, y el aviso mentía | D |
| V.35 | ✅ | Badge de alertas: "0" rojo permanente, sin `aria-live`, sin nombre accesible, y `base.html` duplicaba el marcado del parcial | D |
| V.36 | ✅ | Estados vacíos sin CTA ni distinción "sin datos" vs "filtro sin resultados"; con 0 documentos la pantalla clave es una tabla muda | E |
| V.37 | ✅ | El onboarding del dashboard exige todo-o-nada y ya no puede dispararse; el hueco real (cumplimiento en 0) se lee como "sin novedad" | E |
| V.38 | ✅ | `javascript:history.back()` como único regreso (muere sin historial y con CSP enforcing); el detalle genérico no ofrece Editar | E |
| V.39 | ✅ | Dos bloques `@media (max-width:768px)` en conflicto (la trampa de R.10 en responsive) + errores de validación de modales HTMX sin foco ni anuncio | E |

Verificado LIMPIO por los auditores (no re-auditar): storage sin path
traversal, CSRF, pipeline de subida, autorización de lectura de la API DRF,
feed del calendario sin N+1 (~15-20 queries constantes), `GlobalSearchView`,
`digest.py`, transiciones de estado con `atomic`, hardening de `prod.py`.

### Áreas de vuelo en KMZ — decidido el 2026-07-25, **SUPERADO el 2026-07-27**

**Archivar sí, interpretar no.** Decisión del usuario. Las cartas de permiso y
los KMZ se guardan como `Document` colgando del permiso de vuelo, con su
versionado, sus alertas de vencimiento y su sitio en el informe. El KMZ y el KML
están en la lista blanca de subida con su firma (`2fbe152`). **Esto sigue siendo
verdad y es la base del nuevo bloque.**

**Lo que cambió (2026-07-27):** el usuario decidió superar el "interpretar no"
con un alcance acotado — un **editor liviano** (no un GIS): importar, visualizar,
editar geometrías/atributos, versionar, aprobar y re-exportar. El diseño evita
PostGIS (sigue local-first con SQLite: el KML se interpreta en Python y el blob
canónico vive en un `JSONField`) y evita el análisis espacial serio (solapamientos,
punto-en-polígono), que queda para más adelante. Ver **BLOQUE GEO** abajo y
[docs/dev/geo-editor-plan.md](docs/dev/geo-editor-plan.md).

### Deuda de `openspec/specs/` (TL.8, pendiente)

Los `spec.md` archivados **no se pueden promover tal cual**: describen lo que se
propuso, y varias afirmaciones ya son falsas. Muestra de la deriva encontrada al
revisarlos:

- `phase2-ops-maint` sitúa el calendario en `/operations/calendar/`; la URL real
  es `/calendar/`.
- `phase2-ops-maint` cierra con "All views require login", que era cierto y hoy
  se queda corto: desde T2.3 exigen además el `view_*` del modelo.
- `phase1-document-mgmt` describe `generate_alerts` comprobando entidades
  cableadas (`Qualification.expiry_date`, `Document.expiry_date`,
  `FlightPermission.status`); el BLOQUE 4 lo reemplazó por el registro validado
  de `watchables`.
- `phase1-document-mgmt` F7 propone "add `django-filters` or manual Q-object
  search": una decisión de implementación, no un requisito.
- `phase3-workboard` describe `/workboard/` sin mencionar `view_kanbantask`.

Promoverlos requiere verificar cada afirmación contra el código y las 269
pruebas, no copiar archivos. Un `specs/` con afirmaciones falsas es peor que no
tenerlo: es exactamente el problema que ya tuvimos con `docs/SECURITY.md`, que
daba por cerrada la "Autorización de lectura/exportación" mientras F-06 seguía
abierto (hoy sí es cierto, cerrado en `3611d06`).

## Estado actual (actualizado 2026-07-24 — FASE 0 + higiene de Bloque 0 cerradas)

- **FASE 0 completa** en `codex/impeccable-ui-audit`: T0.1-T0.7 hechas y commiteadas. El dashboard vuelve a renderizar, `verify.ps1` falla de verdad ante un paso roto, hay un test que compila las 43 plantillas, cobertura con piso real (83%+), mantenimiento ya se puede cerrar desde la UI.
- **BLOQUE 0 del plan externo, prácticamente cerrado:** `docs/` reordenado (producto vs `docs/dev/`), rutas de ejemplo genéricas, índices de `Alert`/`Document`/`KanbanTask`, log estructurado de reglas de alerta inválidas, `AGENTS.md` ampliado con DoD/contrato de lectura/precedencia documental. **Solo queda TL.11** (tag `v0.1.0-alpha` + `CHANGELOG.md`).
- **Verificación tras el cierre de FASE 0 + higiene:** `pytest` **173/173 verdes** · cobertura real **~84%** (umbral `fail_under=83`) · `ruff check` limpio · `manage.py check --deploy` limpio · `makemigrations --check` limpio.
- **Nota de entorno:** en el sandbox de esta sesión, `ruff format --check` devuelve código de salida 2 con "Acceso denegado" pese a reportar el chequeo correcto — es un artefacto de este entorno (relación de confianza de dominio rota, confirmado con `icacls`/`whoami`), no un bug del repo ni de `verify.ps1`. Si reaparece en tu máquina, es señal de revisar permisos de `.ruff_cache`/`.pytest_cache`, no de tocar el script.
- **Sin P0 de seguridad.** Los IDOR (F-03–F-06) son gaps reales pero mitigados hoy por `tenant=NULL` universal; se cierran antes de centralizar el servidor (FASE 2).
- **T3.1 completo** (`6066271`): `Document`/`Alert`/`AlertRule`/historias protegidas de cascada.
- **BLOQUE 1 (Alertas⇄Kanban) — backend completo y probado** (`6c737fb`, `1b8691b`, `3833d85`, `66ee5b9`): `AlertRule` puede apuntar a un tablero/etapa, `generate_alerts` crea la tarea vinculada con prioridad por urgencia y responsable derivado, resolver la alerta (o reemplazar el documento) cierra la tarea, y `init_dgac_board` siembra el tablero de cumplimiento. **Solo quedan B1.4/B1.5 (UI), que requieren revisión visual en el navegador** — este es el punto de revisión en vivo.
- **Ruta de ejecución obligatoria** (revisión `PLAN_CLAUDE_CODE_1.md`): Bloque 0 → 1 → 2 → 4-parcial → 6.1/6.2. Diferidos: Bloques 3, 5 (salvo `JobRun`), 6.3 y los dos ítems de diseño del Bloque 4.
- **Siguiente:** cerrar B1.4/B1.5 (UI, en cuanto haya panel de navegador) y arrancar **BLOQUE 2** (empezando por `JobRun`, B2.0). FASE 1 (partir `core`, XL) puede esperar — no bloquea la ruta de producto.

---

## Tablero de bloques

### FASE 0 — Estabilización inmediata `⛔ desbloquea todo`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T0.1 | ✅ | P0 | Corregir el bloque `extrahead` duplicado (restaura la app) | XS | — |
| T0.2 | ✅ | P1 | Renderizar `completion_form`: permitir cerrar mantenimientos | S | — |
| T0.3 | ✅ | P1 | `verify.ps1` debe fallar ante error (comprobar `$LASTEXITCODE`) | XS | — |
| T0.4 | ✅ | P1 | Umbral de cobertura en CI (`--cov-fail-under` + ratchet) | S | T0.3 |
| T0.5 | ✅ | P2 | Test que compile las 43 plantillas (habría atrapado T0.1) | S | T0.3 |
| T0.6 | ✅ | P2 | Corregir `openspec/config.yaml` y sincronizar `docs/dev/03-Roadmap.md` | XS | — |
| T0.7 | ✅ | P2 | `ruff format .` sobre los 35 archivos + `verify.ps1` verde | XS | T0.3 |

### FASE 1 — Arquitectura y deuda crítica `⛔ requiere FASE 0`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T1.1 | ⬜ | P1 | Partir `core`: infra pura + `apps/tenancy`; mover calendario/búsqueda a `dashboard` | XL | FASE 0 |
| T1.2 | ⬜ | P1 | Refactor `UnifiedCalendarEventsView` (231 líneas) → proveedores de eventos por app | L | T1.1 |
| T1.3 | ⬜ | P2 | Eliminar señales `pre_save`; `transition_to(status, actor, notes)` en el modelo | M | T1.1 |
| T1.4 | ⬜ | P2 | Auditoría atómica con la mutación; no tragar el fallo de escritura | M | T1.3 |
| T1.5 | ⬜ | P3 | `selectors.py` por app (lecturas/scoping/agregaciones) | L | T1.1 |

### FASE 2 — Seguridad y permisos `⛔ requiere FASE 1`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T2.1 | ⬜ | P1 | Cerrar IDOR workboard: acceso a tablero en checklist/stage; `get_queryset` scoped en List (F-03, F-04) | M | T1.1 |
| T2.2 | ✅ | P1 | **`TenantScopedQuerysetMixin` — aislamiento por objeto (F-03/F-06/F-05).** `core.views.TenantScopedQuerysetMixin` + `core.tenancy.scope_queryset_to_tenant(tenant_path)` cierran el IDOR por objeto en **todas** las superficies: registry raíces (detalle/edición/archivar/restaurar) y derivadas (asignaciones/habilitaciones por `cost_center__/operator__tenant_id`), **documentos** (detalle/descarga/reemplazo/borrado, FK directo), **AlertRule** (edición), **permisos** (`cost_center__tenant_id`), **registros de vuelo** y **mantenimiento** (`aircraft__tenant_id`, incl. completar). Otro tenant → **404**, dueño → 200. No-op hoy (un tenant). 6 tests `TestObjectLevelIsolation`. **Pendiente menor:** transiciones de estado genéricas (`StatusTransitionView`: aprobar/denegar permiso, iniciar mantención). | M | — |
| T2.3 | ✅ | P1 | `has_perm` en `/calendar/`, Kanban HTML y feed de eventos (F-06) — `CalendarAccessMixin` por fuente de evento, desplegables por `view_*` del modelo que listan, `?types=` acotado a lo permitido (`3611d06`) | S | T1.1 |
| T2.4 | ✅ | P2 | Rol `Viewer` con `view_*` explícitos (no `startswith`). En la base real recibía **35** permisos, incluidos `authtoken.view_token`, `auth.view_user`, `sessions.view_session` y `core.view_auditevent`; ahora 20 (`c5d22dd`) | S | — |
| T2.5 | ✅ | P2 | **[nuevo]** `TIME_ZONE` pasa a `America/Santiago` (decisión del usuario, 2026-07-25) y configurable por entorno. Todo `date.today()` de producción reemplazado por `timezone.localdate()` en `generate_alerts`, `send_alert_digest`, `digest.py`, `dashboard/views.py` y `compliance/models.py`, más las fixtures de prueba que comparaban contra la fecha del SO. Verificado: las dos nociones de "hoy" ahora coinciden | S | — |
| T2.5 | ✅ | P2 | `django-csp`/SRI ya resueltos (V.10-V.11/T5.9: CSP enforcing hecho a mano — ver decisión de descarte de `django-csp` arriba —, SRI en las 5 dependencias vendorizadas). **Cerrado 2026-07-30:** `django-axes` (F-17/F-18) — bloqueo de fuerza bruta por usuario, 5 intentos/15 min, activo en prod tras exponer la app con Tailscale Funnel (`fea3f3c`) | M | — |

### FASE 3 — Integridad de datos `⛔ requiere FASE 1 · CAMBIAR AHORA`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T3.1 | ✅ | P1 | `on_delete=CASCADE → PROTECT` en Document/Alert/historias (F-07). Respaldo desnormalizado descartado deliberadamente (ver commit `6066271`) | S | — |
| T3.2 | ✅ | P1 | Tenancy (F-08) **COMPLETO 2026-07-31** (Fases 0-4). **ADR-0001** (Opción A, por fases — [docs/dev/adr-0001-tenancy.md](docs/dev/adr-0001-tenancy.md)). **Fase 0 completa 2026-07-31**: `get_default_tenant` (default del FK, sin churn); `tenant NOT NULL` en `CostCenter`/`Aircraft`/`Operator` (0a, migr. 0018/0019) y FK propio en `Document`+`AlertRule` (0b, `compliance` 0010; catálogos globales por decisión del usuario; los demás agregados derivan del padre). Todo registro scopeable ya resuelve un tenant. **Fase 1 hecha**: `visible_tenant_ids(user)` centraliza la resolución (reemplaza 3 copias inline) + fallback al default (corrige el bug de "no-superuser sin membership no veía nada") + test de aislamiento. **Fase 4 (red inicial) hecha**: tests de aislamiento cross-tenant para las vistas que ya scopean (asignaciones + feed del calendario) — `apps/core/test_tenancy.py`. Descubrimiento: las listas de registry (CC/Operator/Aircraft) hoy **no scopean por tenant** → es parte de Fase 2. **Fase 2 hecha**: OR-sobre-3-FKs → ruta canónica (`cost_center__tenant` en permisos/asignaciones del calendario y lista de Assignment; documentos del calendario vía `Document.tenant`); listas de registry (CC/Operator/Aircraft) ahora scopean vía `RegistryList.scope_by_tenant`; matriz de aislamiento ampliada a esas listas. **Fase 3 hecha**: `UniqueConstraint(tenant, code)` en CostCenter y `(tenant, employee_id)` en Operator (migr. 0020); permiso DGAC y matrícula siguen globales (identificadores de autoridad), catálogos también. **T3.2 cerrado.** Opcional aparte (F-03/F-06, no parte de T3.2): scoping por objeto en vistas de detalle (IDOR), irrelevante con un solo tenant. Nota: T3.2 no dependió de T1.1 (se hizo sin partir `core`). | XL | — |
| T3.3 | ✅ | P1 | `UniqueConstraint` compuestos con tenant (F-10). **Hecho en T3.2 Fase 3** (verificado 2026-08-03): `CostCenter (tenant, code)` y `Operator (tenant, employee_id)` son únicos por tenant; cubierto por `test_tenancy.py::TestTenantUniqueConstraints`. (Aircraft.registration sigue único global, correcto: las matrículas son nacionales.) | L | T3.2 |
| T3.4 | ⏸ | P2 | Migrar estados a `TextChoices` (no cambia el esquema). **Diferido 2026-08-03**: inventariado (~89 sitios con literales en 16 campos/13 modelos, mayor churn en `KanbanStage.status_type` ~17) — churn de estilo sin valor funcional frente al paquete LV-29..32. | M | — |
| T3.5 | ⬜ | P3 | Índices compuestos `is_active`+fecha/estado | S | — |

### FASE 4 — Testing `⛔ requiere FASE 0; parcial tras FASE 3`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T4.1 | ⬜ | P1 | `conftest.py` con fixtures `two_tenant_world`, `role_user()` | M | FASE 0 |
| T4.2 | 🔄 | P1 | Matriz de aislamiento cross-tenant por vista. **En gran parte hecho en T3.2** (verificado 2026-08-03): `test_tenancy.py` cubre `visible_tenant_ids`, listas (CC/operador/aeronave), feed del calendario, y ahora **detalle/edición/archivar por objeto (F-03/F-06)**. Pendiente: extender a documentos/permisos/mantenimiento como matriz formal + `conftest` (T4.1). | L | T4.1, T3.2 |
| T4.3 | ✅ | P1 | Tests de `generate_alerts`, `maintenance`, `dashboard`. **El "hoy 0%" era obsoleto** (2026-07-24). Cerrado 2026-07-30: `dashboard` **100%** (test_ops8 + LV-8e), `maintenance` **100%** (lista+filtros, form create GET/POST, completar-ya-completado, `is_incomplete` en completado), `generate_alerts` + `digest` **100%** (regla que vigila un campo `status`, `digest_item_count`). 6 tests nuevos. | L | T4.1 |
| T4.4 | ✅ | P2 | Neutralización de fórmulas en reportes workboard. El CSV y el XLSX volcaban `task_row()` (título/etiquetas/responsable, texto libre) sin neutralizar → *formula injection* al abrir en Excel. Ahora aplican `core.exports.neutralize` por celda (cerrado 2026-07-30). El DOCX no ejecuta fórmulas, no requiere. 2 tests (CSV y XLSX con título `=…`, verificando el prefijo `'`). | M | — |
| T4.5 | ⬜ | P3 | Sustituir ~14 tests de bajo valor por los P0 de arriba | S | T4.1 |

### FASE 5 — UX y flujos operacionales `requiere FASE 0`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T5.1 | ✅ | P2 | Unificar `app.css` en un solo set de tokens. **Verificado hecho 2026-07-31**: hay un único `:root` (el de `--ac-*`), cero definiciones y cero usos de tokens sin prefijo, sin referencias colgantes; el `:root` viejo fue removido (lo documenta el comentario de cabecera del CSS). `--stage-color` y `--login-*` son sets locales/scoped legítimos, no una segunda generación. | M | — |
| T5.2 | ✅ | P1 | **Enlazar habilitaciones, búsqueda global e importadores (U1, F-14).** Habilitaciones ya estaba en el sidebar; **búsqueda global** ahora accesible desde una caja en el navbar (existía pero era inalcanzable); **importadores** ahora con botón "Importar" en las listas de centros de costo/aeronaves/operadores (bloque `list_actions` en `generic/list.html`, más contextual que saturar el sidebar). 1 test. | S | — |
| T5.3 | ✅ | P1 | **Búsqueda global que lleva al detalle (U2).** `GlobalSearchView.SEARCH_SOURCES` ahora mapea cada fuente a su URL de detalle: los resultados de CostCenter/Aircraft/Operator abren la ficha del objeto en vez de la lista. Kanban (standby) y Document quedan en su lista (no tienen ficha por objeto). 1 test. | S | — |
| T5.4 | ✅ | P1 | **Dashboard accionable + vencimientos reales (U3, U4).** Los tiles de Aeronaves/Operadores/Alertas ahora son enlaces a sus listas. El panel "Próximos vencimientos" dejó de ser solo habilitaciones: `dashboard.views.upcoming_expirations()` unifica **habilitaciones + documentos + permisos de vuelo** en la ventana de 30 días, cada uno con enlace a su ficha (habilitación→operador, documento→ficha de documento, permiso→ficha). Filtro por CC en habilitaciones/permisos; documentos van por relación genérica (sin CC directo). 1 test. | M | — |
| T5.5 | ✅ | P1 | **Formulario de vuelo reducido + prellenado desde el permiso (U5).** La ficha del permiso ("+ Add record") ahora prellena el permiso (`?permission=`); y `FlightRecordForm` **acota** los selectores de piloto y aeronave al roster de ese permiso en vez del padrón completo (mismo patrón que `KanbanTaskForm`), así el usuario solo ve opciones válidas. 2 tests. | M | — |
| T5.6 | ✅ | P2 | **Paginación HTMX + búsqueda en vivo alineadas (F-13).** Eran dos problemas, ambos resueltos: (a) los controles de paginación quedaban **stale** al buscar/paginar en vivo → ahora se actualizan out-of-band (`#pagination-container`, `hx-swap-oob`, guard `is_htmx` para no duplicarlos en página completa); (b) las 5 listas con columnas propias (CC, operador, aeronave, habilitaciones, asignaciones) devolvían el `_table_body.html` genérico en HTMX, colapsando sus columnas → ahora cada una tiene su parcial de filas (`registry/_*_rows.html`) y su `htmx_template_name`. De paso, dos `"Sin asignar"` hardcodeados → `{% translate "Unassigned" %}`. Verificado a nivel de respuesta (columnas custom presentes en HTMX; un solo `#pagination-container` en página completa). 4 tests. | M | — |
| T5.7 | ⬜ | P2 | Exportación visible en todas las listas (U6) | S | — |
| T5.8 | ⬜ | P2 | Limpiar fugas de i18n; accesibilidad (`scope`, labels) | M | — |
| T5.9 | ✅ | P2 | Vendorizar assets locales (Bootstrap/HTMX/Chart.js/FullCalendar/Sortable) + SRI. Hecho como V.11 (`static/vendor/`, sha384, orígenes CDN eliminados del CSP). Leaflet/Geoman ya venían de GEO-7/8 | M | T2.5 |

### FASE 5R — Legibilidad y consistencia visual (feedback de revisión en vivo 2026-07-24)

> Observado por el usuario mirando la app corriendo. Las capturas mostraron que la causa
> raíz de "las alertas/tarjetas no se entienden" es la falta de `__str__` en varios modelos
> (auditoría A19): la UI imprime `Qualification object (uuid)`, `AlertRule object (...)`,
> `Alert object (...)`. Prioridad alta porque afecta la comprensión básica de la app.

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| R.1 | ✅ | P1 | `__str__` en `Qualification`, `Alert`, `AlertRule`, `KanbanTask`, `KanbanStage`, `MaintenanceRecord`, `FlightRecord` (`8062425`) | S | — |
| R.2 | ✅ | P1 | Lista de alertas legible: entidad en vez de UUID, nombre de regla, badge de vencimiento/atraso, `th scope` (`8062425`) | S | R.1 |
| R.3 | ✅ | P1 | Tarjetas Kanban legibles + comando `refresh_alert_task_titles` para los títulos ya guardados con el repr viejo (`8062425`) | S | R.1 |
| R.4 | ✅ | P2 | Badges de etapa `.status-*` (no existían en el CSS) + `.is-overdue` con icono; badge redundante quitado de la tarjeta del tablero (`4b8e150`) | S | — |
| R.5 | ✅ | P2 | Calendario: eventos a 2 líneas + tooltip con etiqueta completa, etapa fuera del título, colores de fallback para modo oscuro (`4b8e150`) | M | — |
| R.6 | ✅ | P2 | Sidebar contraído muestra el conteo de alertas como dot-badge sobre la campana (medido 18×17px; antes `display:none`) (`4b8e150`) | S | — |
| R.7 | ✅ | P2 | Contraste: `.sidebar-label` de **3.79 → 8.06:1** (cumple AA); paleta de gráficos por tema (**1.16 → 5.03:1**) (`4b8e150`) | M | — |
| R.8 | ✅ | P3 | Icono de "Vuelos" cambiado a bitácora (antes casi idéntico al de Aeronaves) (`4b8e150`) | XS | — |
| R.9 | ✅ | P2 | Grupos del sidebar con línea separadora y más espaciado (`4b8e150`) | S | — |
| R.10 | ✅ | P3 | Unificar `app.css` (= T5.1). **Verificado hecho 2026-07-31**: un solo `:root` `--ac-*`, sin la generación sin prefijo. La "Anatomía de R.10" más abajo describe el estado *previo* (dos generaciones); ya no aplica. | M | — |

**Verificado en vivo** (servidor de demo, mediciones de contraste reales, no a ojo). Hallazgos extra encontrados durante la revisión y corregidos: paleta de gráficos invisible en modo oscuro, etiquetas de gráficos con valores crudos (`active` → `Activo`), agregaciones del dashboard contando registros archivados (A5), y ~19 cadenas sin traducir.

**Nota de causa raíz:** R.7 tardó dos intentos porque `[data-theme="dark"] .sidebar-label` ganaba por especificidad sobre la regla de tokens más nueva. Mientras `app.css` conserve dos generaciones superpuestas (R.10/T5.1), este tipo de corrección seguirá necesitando editar el override antiguo además del nuevo.

### Revisión en vivo 2026-07-30 — issues de formularios/UX `🔄 EN CAPTURA`

> Feedback del usuario mirando la app **ya desplegada** (VM `p340`, acceso
> público por Funnel, datos reales). Se va poblando a medida que el usuario sube
> issues/recomendaciones; cada uno se vuelve tarea aquí **antes** de tocar
> código. Mismo espíritu que FASE 5R.

**Formulario de carga de documentos** (`apps/compliance/forms.py::DocumentForm`,
modal "Documentos"):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-1 | ✅ | P2 | **"Tipo de documento" confuso / vacío.** Comando `seed_document_types` (idempotente, 6 tipos de [docs/compliance-setup.md](docs/compliance-setup.md), uno marcado `is_insurance`) + `DocumentForm` avisa en el `help_text` del campo y en un banner del modal ("Aún no hay tipos… Crear uno") con enlace a `documenttype-create` cuando el catálogo está vacío. | `apps/compliance/management/commands/seed_document_types.py` |
| LV-2 | ✅ | P2 | **Título libre → estandarizado.** Opción A implementada: `title` ahora opcional; si se deja en blanco, `DocumentForm.clean()` lo genera como `{tipo} · {registro} · {fecha de emisión}` (editable si el usuario prefiere escribir el suyo). | `apps/compliance/forms.py::DocumentForm._autogenerate_title` |
| LV-3 | ✅ | P3 | **Sección de comentarios.** Campo `notes` (ya en `BaseModel`) agregado a `DocumentForm.Meta.fields` y renderizado en el modal; reutiliza el msgid "Notes"/"Notas" ya existente. | — |

**Opciones para LV-2 (estandarizar el título):**
- **A (recomendada):** **autogenerar** el título desde tipo + entidad + fecha de emisión (p. ej. "Credencial DGAC · J. Pérez · 2026-03"); campo prellenado y editable. Consistente sin fricción.
- **B:** título **opcional**; si se deja vacío, se autogenera como en A.
- **C:** dejarlo libre con texto de ayuda y convención sugerida (el más débil; no garantiza consistencia).

**Lista de aeronaves** (`apps/registry` lista de `Aircraft`):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-4 | ✅ | P2 | **Vencimiento del seguro en la lista de aeronaves.** Opción A implementada: `DocumentType.is_insurance` (flag, migración `0009`); `AircraftList.get_queryset()` resuelve en una consulta el documento de seguro vigente que vence antes por aeronave (sin N+1) y lo expone como columna con badge (`Overdue`/`Due` + fecha, mismo patrón que `alert_list.html`). | `apps/registry/views.py::AircraftList`, `templates/registry/aircraft_list.html` |

*Alertas:* el vencimiento del seguro **ya queda cubierto** por la regla
`compliance.document / expiry_date` (LV/compliance-setup); lo nuevo de LV-4 es
**surfacing en la lista + marca visual**, no un motor de alertas aparte.
Generalizable: la misma columna+badge sirve para aeronavegabilidad y otros
documentos clave de la aeronave.

**Importación KMZ/KML** (`apps/geo` import form, `templates/geo/*import*`):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-5 | ✅ | P3 | **Sin indicador de progreso al importar KMZ.** `<form data-loading-label="…">` genérico (progressive enhancement en `static/js/app.js`, sin JS = sin feedback pero el envío sigue funcionando): deshabilita el botón, cambia su texto y muestra una barra de progreso indeterminada (Bootstrap) mientras la request POST síncrona corre. Reusable en cualquier otro formulario lento. | `static/js/app.js`, `templates/geo/plan_import.html` |

**Vista de calendario del Kanban** (`templates/workboard` "Plan de acción" — pestañas Tablero/Lista/Calendario):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-6 | ⬜ | P2 | **"Vista de calendario" del Kanban es redundante con `/calendar/`** (el calendario global ya unifica permisos/mantenimiento/tareas). Reemplazarla por una **vista Gantt** de las tareas del tablero (línea de tiempo por etapa/fecha de vencimiento). Requiere **propuesta de diseño antes de implementar** (biblioteca a usar — FullCalendar ya vendorizado con SRI soporta un plugin de línea de tiempo/resource-timeline, evaluar vs. una implementación liviana propia; qué datos mostrar: rango planned↔due_date por tarea, agrupado por etapa o por responsable). | **Decisión de diseño pendiente** — no implementar aún |
| LV-7 | ✅ | P2 | **Ocultar "Plan de acción" (Kanban) del sidebar** hasta que LV-6 (Gantt) esté resuelto — decisión del usuario 2026-07-30: "lo podemos hacer crecer en un futuro pero lo dejamos para luego". La sección "Seguimiento" solo tenía ese único enlace, así que se comentó junto con su rótulo (no queda un encabezado vacío); la ruta y la vista `kanban` siguen activas, solo el enlace de navegación se ocultó (`templates/base.html`). | Reversible: retirar el `{% comment %}` cuando se resuelva LV-6 |

**Registro de mantenimiento** (`apps/maintenance`, formulario "Nuevo: Registro de mantenimiento"):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-8a | ✅ | P2 | **Tipo "Por definir"** (`to_be_defined`) agregado a `MaintenanceRecord.TYPES`, listado primero (estado "inbox" antes de planificar). | 2026-07-30 |
| LV-8b | ✅ | P2 | **`scheduled_date` y `performed_by` opcionales** (`null/blank`, migración `0006`). Al *completar* siguen exigiéndose (`MaintenanceCompletionForm`), solo se relajan al crear/por-definir. | — |
| LV-8c | ✅ | P3 | **Campo `cost` eliminado** del modelo/form/detalle/completar (migración `0006`). Confirmado que no se usaba en `reports.py`. | — |
| LV-8d | ✅ | P1 | **i18n**: "Maintenance type" y labels del form de mantenimiento explicitados y traducidos; guard de traducciones verde. | — |
| LV-8e | ✅ | P2 | **Datos faltantes surfaced** (opción B elegida por el usuario): tarjeta "Mantenciones por definir" en el dashboard (solo si >0, con enlace) y `MaintenanceRecord.is_incomplete`. Se descartó crear un objeto Alert para no distorsionar el motor (solo vencimientos). | — |
| LV-8f | ✅ | P3 | **Cruce con reporte**: `build_compliance_report` incluye `incomplete_maintenance` (scopeado por CC) y `report.html` lo muestra. | — |

**Listas genéricas con columnas pobres** (`templates/generic/_table_body.html`, usada por `OperatorList`, `CostCenterList` y otras):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-9 | ✅ | P2 | **Listas enriquecidas** (opción "tabla enriquecida" elegida por el usuario). **Operadores** (`operator_list.html`): Nombre · RUT · Credencial DGAC · Centro de costo · Habilitación (badge vigente/vencida vía B4.3) — anotado en una consulta (`current_quals`/`expired_quals`). **Centros de costo** (`costcenter_list.html`): Código · Nombre · Admin. de contrato · Nº operadores · Nº aeronaves — conteos anotados. `OperatorList`/`CostCenterList` ahora son clases explícitas que sobreescriben las genéricas. "Docs por vencer" en la lista de CC se omitió a propósito (cálculo GFK caro por fila; vive en el reporte y en la ficha del CC). | 2026-07-30 |

**Formulario de centro de costo** (`apps/registry` `CostCenterForm`):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-10a | ✅ | P2 | **Prefijo "CC" fijo en el código** (opción A elegida: se almacena `CC738`). `CostCenterForm.clean_code()` normaliza cualquier entrada a `CC`+número (quita un `CC` que el usuario haya tecleado, exige el número); migración de datos `0015` prefija los 11 códigos existentes (idempotente y reversible). Es la fuente de verdad en lista, `__str__`, exports y búsqueda. | 2026-07-30 |
| LV-10b | ✅ | P3 | **Renombrar el label "Responsable"** del formulario a **"Nombre de Administrador de contrato"** (campo `responsible`, texto libre). | Solo label del form (cerrado con B4.3, `6-…`) |

**Inconsistencia FK vs asignaciones** (ficha de centro de costo — Equipo/Flota):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-11 | ✅ | P2 | **La lista de CC contaba aeronaves (por el FK) pero las pestañas Equipo/Flota salían vacías.** No era bug de plantilla: los datos importados pusieron `Operator/Aircraft.cost_center` (FK, la denormalización de OPS-1) pero **nunca se crearon las filas `OperatorAssignment`/`AircraftAssignment`** que la ficha OPS-2 (Equipo/Flota/Historial/timelines) usa como fuente de verdad. En la VM: 13 aeronaves + 2 operadores con FK, 0 asignaciones. Fix: comando idempotente `backfill_resource_assignments` que crea una asignación activa por recurso con FK sin asignación (reejecutable tras cualquier importación masiva tipo `chapter1_import`). Corre con modelos reales; el FK ya coincide, así que la señal no fabrica historial falso. | Cmd `apps/registry/management/commands/backfill_resource_assignments.py` |
| LV-11b | ⬜ | P3 | **[nota]** `chapter1_import` (y cualquier import que setee el FK directo) debería crear las asignaciones en el mismo paso, para no depender del backfill. Mejora futura. | — |

**Poblar habilitaciones reales desde `Operator.authorizations`** (texto libre):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-12a | ✅ | P2 | **`Qualification.issue_date` opcional** (`null/blank`, migración `0016`). | 2026-07-30 |
| LV-12b | ✅ | P2 | **Comando `seed_operator_qualifications`**: parsea `Operator.authorizations` y lo estandariza al catálogo `QualificationType` por `model_keywords`, creando una `Qualification` por modelo reconocido (varias por operador), sin fecha de emisión ni vencimiento. Idempotente. **Reporta los operadores cuyo texto no matcheó ningún tipo** para ampliar el catálogo. | Cmd |
| LV-12c | ✅ | P3 | **Historial vía audit trail** (decisión del usuario): toda edición/creación/borrado de `Qualification` ya queda en `AuditEvent`, visible y filtrable en Centro de administración → Auditoría. No se agregó modelo dedicado. | — |

**Panel lateral (sidebar)** (`templates/base.html`):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-13a | ✅ | P2 | **Sidebar reagrupado por flujo operativo** (opción elegida por el usuario): DATOS MAESTROS (CC · Aeronaves · Operadores · **Habilitaciones**) · PLANIFICACIÓN (asignaciones op/aeronave · movimientos · geoespacial) · OPERACIONES · MANTENIMIENTO · CUMPLIMIENTO · ADMIN. Habilitaciones movida a Datos maestros; la **"Planificación de recursos"** (modelo `Assignment` legado, reemplazado por las asignaciones por-recurso) **retirada del nav** (ruta intacta). | `templates/base.html` |
| LV-13b | ✅ | P3 | **Icono de "Habilitaciones"** cambiado de estrella a una medalla/insignia (skill). | — |

**Lista de habilitaciones repite el operador** (`qualification-list`):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-14 | ✅ | P2 | **Lista de Habilitaciones agrupada por operador.** `QualificationList` ahora es operator-centric: una fila por operador con sus `QualificationType` como chips en una columna "Equipos habilitados" (cada chip abre el editar de esa habilitación; rojo si vencida). Búsqueda/`is_active` filtran las habilitaciones subyacentes; el export CSV sigue exportando las habilitaciones individuales. `qualification_list.html`. 3 tests. | 2026-07-30 |

| LV-15 | ✅ | P3 | **Color por tipo en los chips de "Equipos habilitados" (LV-14).** `QualificationType.chip_class` deriva un color estable del `code` (hash `crc32` determinista, sin migración) hacia una paleta de pares Bootstrap *subtle* theme-aware (`primary/success/info/warning/secondary/dark`); `bg-danger` queda reservado para vencidas. `qualification_list.html` usa la propiedad. 2 tests (render coloreado + vencida sigue roja; propiedad estable/en-paleta/nunca danger). Pedido 2026-07-30, reiterado 2026-07-31. | `apps/registry/models.py::QualificationType.chip_class`, `qualification_list.html` |

**Formulario de centro de costo — simplificar** (`CostCenterForm`, lista de CC):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-16 | ✅ | P2 | **Form de CC simplificado** (2026-07-30). "Nombre" fuera del `CostCenterForm`; `CostCenter.name` opcional (`blank=True`, migración `0017`) y `__str__` cae al código cuando está vacío; los nombres existentes se conservan (ModelForm no toca campos ausentes). Campo **"Notas"** agregado al final del form (`notes` de `BaseModel`) y **columna "Notas"** al final de la lista de CC. 4 tests. | — |

**Asignaciones de operador — pedidos 2026-07-31** (`OperatorAssignment*`):

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-17 | ✅ | P2 | **Fechas de inicio/término fuera de la asignación de operador.** `OperatorAssignmentForm` deja solo operador + CC + estado + propósito; `start_date` (obligatorio en el modelo) se autollena con hoy en `__init__` (antes de validar, porque `_overlapping` lee `start_date`). Sin migración, lógica de solape intacta. 2 tests. | `apps/registry/forms.py::OperatorAssignmentForm` |
| LV-18 | ✅ | P2 | **Asignación masiva de operadores a un CC.** Nueva vista `OperatorBulkAssign` (`FormView` + `HtmxFormMixin`) que toma el "+ Nuevo" de la lista de asignaciones: multi-selección de operadores + CC + estado + propósito. Servicio `services.bulk_assign_operators` mueve con semántica *un operador = un CC* (cierra la asignación previa, abre la nueva `start_date=hoy`, integra el `signal`: denormalización + `ResourceMovementLog` "reassigned"); operador ya en el CC destino se omite. 5 tests (servicio + vista HTMX 204). Aclarado 2026-07-31 (el pedido era agilizar, no un bloqueo). | `apps/registry/services.py`, `views.py::OperatorBulkAssign`, `forms.py::OperatorBulkAssignForm` |
| LV-16b | ✅ | P3 | **Historial de la decisión del nombre.** 2026-07-31: al pedir "CC110 Casa Matriz" el usuario primero eligió mantener LV-16 (nombre por `/admin`), pero al chocar con que **el `name` de la lista quedaba congelado** (no editable) pidió priorizar poder editarlo → ver LV-19 (nombre reincorporado al form). | Superseded por LV-19 |
| LV-19 | ✅ | P2 | **Nombre de CC editable desde el formulario.** El `name` (columna NOMBRE de la lista, p. ej. "Levantamientos digital") lo mostraba la lista pero LV-16 lo había sacado del `CostCenterForm`, dejándolo **congelado** — no se podía crear ni corregir sin `/admin`. Reincorporado como campo **opcional** (`CostCenter.name` ya era `blank=True`, sin migración), con help text. Ahora Casa Matriz y cualquier CC se nombran desde "+ Nuevo"/Editar. 3 tests LV-16 actualizados. (El campo `responsible` "Nombre de administrador de contrato" siempre estuvo y era editable; la confusión era con ese.) | `apps/registry/forms.py::CostCenterForm` |

**Fichas, documentos y estética — pedidos 2026-08-03:**

| ID | Est. | Prio | Tarea | Nota |
|---|:--:|:--:|---|---|
| LV-20 | ✅ | P1 | **Guardar de aeronave "no funciona".** Era `Aircraft.clean()` rechazando ubicación ≠ "En faena" con una faena aún seleccionada; el 422 re-renderizaba sin mostrar el error, parecía botón muerto. `AircraftForm.clean()` ahora limpia `current_site` en silencio cuando la ubicación no es "on_site" (el guard del modelo se mantiene para escrituras no-form). 1 test. | `apps/registry/forms.py::AircraftForm` |
| LV-27 | ✅ | P1 | **Documentos e histórico en las fichas.** Sección "Documentos" reutilizable (`compliance/attachments.py::attached_documents_context` + `compliance/_documents_section.html`) en las fichas de **aeronave** y **operador** (patrón OPS-5 del permiso), con subida prellenada (`?entity_type=&object_id=`). `CostCenter` ahora es `DOCUMENTABLE_MODELS` → su tab Documentos deja de estar estructuralmente vacío y tiene botón de subir. Ficha del **permiso**: nueva sección "Planes geoespaciales" (`permission.geo_plans`) — carta + KMZ juntos. El histórico de credenciales = versionado por *replace* (ya existía). 3 tests. | `apps/registry/views.py`, `apps/compliance/attachments.py`, `permission_detail.html` |
| LV-28 | ✅ | P1 | **Repositorio de documentos de la empresa.** `core.operationaltenant` es `DOCUMENTABLE_MODELS`; nueva página `CompanyDocumentsView` (`/compliance/company-documents/`) lista los documentos del tenant (AOC, procedimientos, formularios) con descarga/reemplazo y subida prellenada; ítem en el sidebar (Cumplimiento) + botón en el dashboard. El AOC con vencimiento queda vigilado por la regla existente. 1 test. | `apps/compliance/views.py::CompanyDocumentsView`, `company_documents.html` |
| LV-21 | ✅ | P2 | **Título real en los modales** (era "Formulario" genérico). El `#generic-modal-title` vive fuera de `#modal-content`; ahora `_form_content.html` lo actualiza out-of-band con el `title` de la vista ("Editar aeronave", "Nuevo permiso de vuelo"). | `templates/generic/_form_content.html` |
| LV-22 | ✅ | P2 | **Etiquetas en inglés en la UI en español.** `FlightPermissionForm`/`FlightRecordForm` no definían `labels` → los auto-labels ("Permission number", "Valid from"…) caían fuera del catálogo. Agregados labels explícitos + entradas ES. | `apps/operations/forms.py` |
| LV-23 | ⬜ | P3 | **[diferido, requiere navegador]** Roster de operadores/flota como lista interminable de checkboxes → grid multi-columna con scroll acotado (CSS). La estructura exacta que renderiza crispy hay que verla en navegador para acertar el selector. | `app.css` + form del permiso |
| LV-24 | ✅ | P3 | **Hecho en la pasada de diseño en vivo 2026-08-03** (commits `8b51bc2`, `e1cf5a7`): sistema de pastillas legible en oscuro y claro (relleno tintado + contorno + peso), contraste de botones/cabeceras en oscuro, etiquetas menos opacas. Ver LV-D1/D2/D9 abajo. | `app.css` |
| LV-D1..D9 | ✅ | P2 | **Pasada de diseño de la revisión en vivo (2026-08-03).** D1 pastillas legibles oscuro/claro · D2 contraste botones/cabeceras · D3 buscador "Buscar en AeroControl" · D4 franja compacta de cumplimiento · D5 panel reordenado (KPIs número protagonista, vencimientos arriba, gráficos vacíos ocultos, sin duplicado "Tareas por etapa") · D6 calendario sin mes repetido · D7 columnas de listas compactas (CC=código+tooltip, una acción/fila) · D8 lista general Documentos fuera del menú · D9 grilla pareja de KPIs + pastillas menos opacas. **+ fix real: `.mo` recompilado** (textos ES salían en inglés en prod). Commits `8b51bc2`/`42720f6`/`a585b23`/`e1cf5a7`. Deploy diferido. | `app.css`, plantillas, `.mo` |
| LV-33 | ✅ | P1 | **Hecho 2026-08-03** (feedback usuario). Fallback en `CostCenterDetail`: si no hay `OperatorAssignment`/`AircraftAssignment`, las pestañas Operadores/Flota listan por `cost_center` (instancias en memoria, misma interfaz del template) → ya no salen vacías tras un import directo. En prod, además correr `backfill_resource_assignments` (acción del usuario, idempotente). Test. | `registry/views.py` CostCenterDetail |
| LV-34 | ✅ | P1 | **Hecho 2026-08-03** (feedback del usuario): `responsible_type` (Administrador/Operador/Contacto externo) en `CostCenterForm` con `field_order`; muestra solo el campo del tipo (JS delegado en `app.js`, modal+página), valida y limpia los otros, initial derivado al editar. 4 tests. (Toggle visual a confirmar en prod; el pane del demo no compone captura.) | `CostCenterForm`, `app.js` |
| LV-35 | ✅ | P2 | **Hecho 2026-08-03** (feedback del usuario): `AeroModelForm` inicia los `Textarea` en 3 filas (no el bloque gigante), redimensionables. Consistente en todas las fichas. Auto-grow con JS queda opcional a futuro. | `apps/core/forms.py` |
| LV-36 | ✅ | P3 | **Hecho 2026-08-04** (alcance acordado con el usuario: **secciones agrupadas**, no pestañas — el form son solo 8 campos). Partial compartido `_costcenter_form_fields.html` con 3 `<fieldset>` (Identificación / Responsable / Notas), renderizado campo a campo con `as_crispy_field` para conservar los `div_id_*` (el toggle de responsable LV-34 sigue vivo). Cubre las dos vías: página completa (`costcenter_form.html`, Editar desde el detalle) y modal HTMX (`_costcenter_form_content.html`, Editar desde la lista); ambos `template_name`/`htmx_template_name` reapuntados en `views.py`. Nuevo msgid `"Identification"→"Identificación"` + `.mo` recompilado. **De paso: fix real** — el `.po` tenía una entrada obsoleta `#~ "Flight date"` que duplicaba la activa y hacía **fallar `compilemessages`** (habría roto el paso del deploy consolidado); eliminada. 122 tests de registry verdes; ambas vías verificadas en browser (3 secciones, toggle LV-34, fragmento modal con `hx-post`/OOB title). | `templates/registry/`, `apps/registry/views.py`, `django.po`/`.mo` |
| LV-37 | ✅ | P3 | **Hecho 2026-08-03** (feedback del usuario): la pestaña "Equipo" del CC pasa a **"Operadores"** (confundía con equipamiento/drones; "Equipos habilitados" = drones se mantiene). | `costcenter_detail.html` |
| LV-38 | ✅ | P1 | **Hecho 2026-08-03** (feedback usuario; concreta **LV-23**): operadores/flota (CheckboxSelectMultiple) en **grilla multi-columna con scroll acotado** (CSS sobre `#div_id_operators/aircraft_fleet fieldset > div`, `column-width:210px`, `max-height:15rem`), verificado por computed. Mantiene selección múltiple. (Búsqueda dentro de la grilla y layout 2-col del resto quedan como mejora futura.) | `app.css` |
| LV-39 | ✅ | P1 | **Hecho 2026-08-03** (feedback usuario): `status` al inicio del `FlightPermissionForm`; `permission_number` opcional (modelo null/blank, migración `operations 0011`; unique con múltiples NULL) salvo `status=approved` (validación en `clean`); `__str__` robusto sin folio. 3 tests. | `FlightPermission`, `FlightPermissionForm` |
| LV-40 | ✅ | P1 | **Hecho 2026-08-03** (feedback usuario): `DocumentCreate.get_success_url` vuelve a la ficha de la entidad (CC/aeronave/operador/permiso→detail#tab-documents; empresa→company-documents; registros op.→operational-records) en vez de la lista general (fuera del menú, LV-D8); `app.js` activa la pestaña por hash. Test + guardias verdes. | `compliance/views.py`, `app.js` |
| LV-41 | ✅ | P1 | **Hecho 2026-08-04** (regresión de **LV-D6**, captura del usuario): el comentario `{# ... #}` que reemplazó el título del calendario quedó **multilínea** (Django solo soporta `{# #}` en una línea) → se renderizaba literal sobre la barra del calendario. Convertido a bloque `{% comment %}…{% endcomment %}` (multilínea válido). Grep confirma que no hay otros `{# #}` multilínea en las plantillas. | `templates/core/calendar.html` |
| LV-42 | ✅ | P2 | **Hecho 2026-08-04** (captura del usuario, panel "Próximos vencimientos" en oscuro): las pastillas `bg-secondary-subtle`/`bg-dark-subtle` se **fundían con la tarjeta** (medido en browser: fondo 1.38:1, borde 2.2:1 vs card `#161f2d`; el texto ya iba 9:1). Subido relleno y aclarado borde en oscuro → **borde 3.64:1** (supera el mínimo 3:1 para bordes de UI), texto sigue ~8:1. Solo se tocaron los grises neutros; las variantes con color (primary/success/…) leen por tono y quedan igual. Verificado por computed + screenshot. | `static/css/app.css` |
| LV-43 | ✅ | P3 | **Hecho 2026-08-04** (elección del usuario, timers de cumplimiento): los comandos LV-29 `notify_expiring_credentials` y LV-30 `check_monthly_records` ya existían pero no estaban cableados al scheduler de Windows. Añadidos a `schedule_tasks.ps1`: `MonthlyRecords` como trabajo diario estándar (`-MonthlyRecordsAt`, default 23:30; el comando se autolimita al último día del mes) y `CredentialNotice` como **opcional** (gate `-WithCredentialNotice` + `-CredentialNoticeAt` 07:30; `-Unregister` siempre lo quita). Doc `scheduled-operations.md` (Windows) actualizado; systemd/cron ya lo cubrían. Sintaxis del `.ps1` validada; ambos comandos verificados en `--dry-run` (0 ítems con datos locales, ejecutan y registran `JobRun`). **Activado en la VM `p340` el 2026-08-04** (systemd, no el `.ps1` de Windows): `aerocontrol-monthly.timer` + `aerocontrol-credentials.timer`, confirmados con `systemctl list-timers`. | `scripts/schedule_tasks.ps1`, `docs/scheduled-operations.md` |
| LV-44 | ✅ | P3 | **Hecho 2026-08-04** (encontrado en la verificación visual post-deploy de LV-36/34): la ficha de detalle del CC mostraba **"RESPONSIBLE CONTACT NAME"/"RESPONSIBLE CONTACT EMAIL" en inglés**, únicos campos sin traducir en una página toda en español. Causa: `CostCenter.responsible_contact_name/email` no tenían `verbose_name` explícito → Django deriva "Responsible contact name", msgid ausente del catálogo (el form sí traduce, con label propio "External contact name/email", ya en el `.po`). Fix: `verbose_name=_("external contact name"/"external contact email")` en el modelo — mismo pipeline `translate_field_label` que ya usa el form, reutiliza los msgids existentes sin tocar el `.po`/`.mo`. Migración `registry 0022` (solo `AlterField`, sin cambio de esquema). 222 tests (registry+compliance) verdes; verificado en browser: ahora dice "NOMBRE DEL CONTACTO EXTERNO"/"CORREO DEL CONTACTO EXTERNO". | `apps/registry/models.py`, migración `0022` |
| LV-45 | ✅ | P1 | **Hecho 2026-08-04** (reportado por el usuario: "el botón crear tarea no funciona"): reproducido en el demo — el botón manual "Crear tarea" de cada fila en `/compliance/alert/` fallaba con "No hay ningún tablero Kanban disponible para alojar la tarea de seguimiento". Causa raíz: el comando `init_dgac_board` (que siembra el tablero "Cumplimiento DGAC") **nunca se corrió** — ni en el demo ni en el runbook de deploy de la VM (Parte D solo hacía migrate/bootstrap_roles/collectstatic/createsuperuser). El botón manual es independiente del flag automático `create_kanban_task` de cada regla (que sí queda apagado a propósito por `seed_alert_rules`), así que necesita el tablero igual. Fix: corrido `init_dgac_board` en el demo (verificado en browser: "Tarea de seguimiento creada.", tablero visible en `/workboard/`); doc `compliance-setup.md` aclarado (correr `init_dgac_board` desde el día 1, no solo si se activa la creación automática); añadido a `docs/dev/ubuntu-vm-deploy.md` Parte D para que no falte en futuros setups. **Corrido en la VM `p340` el 2026-08-04** por el usuario ("Created board 'Cumplimiento DGAC' with 6 stages and 5 labels.") — el botón funciona también en producción. | `docs/compliance-setup.md`, `docs/dev/ubuntu-vm-deploy.md` |
| LV-46 | ✅ | P1 | **Hecho 2026-08-04** (pedido del usuario: marcar una aeronave que "se cayó" y aún no fue enviada a mantenimiento, cruzado con alerta): nuevo estado `Aircraft.status="damaged"` ("Mal estado", badge rojo en la lista, distinto de "Mantenimiento" ámbar). Botón de un clic **"Reportar accidente / daño"** en la ficha (junto a "Enviar a mantenimiento" de LV-26, con confirmación) — sin formulario que llenar primero, porque un reporte de accidente no debería esperar a elegir fecha/responsable. La acción (`AircraftReportIncident`) pone el estado en `damaged` **y** crea de inmediato un `MaintenanceRecord` (`emergency`/`pending`), lo que dispara la regla de alerta **ya existente** "Mantenciones abiertas" (LV-26) sin necesitar una regla nueva — se investigó y se descartó ligar una regla nueva directamente a `registry.aircraft`/`status` porque el motor genérico de alertas por status trata cualquier valor fuera de {completed, denied, non_compliant} como abierto, lo que habría generado una alerta para *cada* aeronave "Activa". Migración `registry 0023` (solo `choices`, sin cambio de esquema). 234 tests (registry+maintenance+compliance) verdes; verificado end-to-end en el demo: estado→"Mal estado", badge rojo en lista, registro "Emergencia·Pendiente" en la ficha, y tras `generate_alerts` la alerta aparece en `/compliance/alert/` con "Crear tarea"/"Resolver" funcionando. | `apps/registry/models.py`, `apps/maintenance/views.py`, `apps/maintenance/urls.py`, `templates/registry/_aircraft_rows.html`, `templates/registry/aircraft_detail.html`, migración `0023` |
| LV-47 | ✅ | P1 | **Hecho 2026-08-04** (reportado por el usuario: "botón siguiente anterior no funciona" en `/calendar/`): el calendario tenía **tres** navegadores de mes superpuestos y desconectados entre sí — los "← Anterior / Siguiente →" del `.page-header` (los de la captura) usaban links `?month=`, pero **FullCalendar los ignora por completo** (se re-inicializa siempre en el mes actual vía JS, no lee ese parámetro) — click cambiaba la URL pero el calendario visible no se movía nunca. Además había una copia idéntica en `.legacy-calendar-header`, pensada como respaldo si JS falla, pero **permanentemente oculta por CSS** (`display:none !important`), o sea que ni siquiera servía de respaldo real. Fix: quitados los botones muertos del `.page-header` (FullCalendar ya tiene su propia navegación funcional junto a "Hoy"); unidos `.legacy-calendar-header` + `.calendar-fallback` bajo un solo wrapper `.calendar-noscript` que `calendar.js` oculta en un solo paso **cuando FullCalendar realmente carga** — así el respaldo sin JS ahora sí tiene título+navegación funcionando en el escenario real para el que existe (falla de JS/CDN), en vez de quedar permanentemente oculto por CSS. 2 tests de calendario verdes; verificado en browser inyectando el `calendar.js` fresco (el `<script src>` cacheado de la sesión de pruebas no reflejaba la edición, un artefacto de caché del navegador de prueba, no del producto) — confirma que el wrapper se oculta correctamente y ya no quedan botones duplicados en el texto de la página. | `templates/core/calendar.html`, `static/js/calendar.js`, `static/css/app.css` |
| LV-25 | ✅ | P3 | **Hecho (Bloque C, 2026-08-03)**: VLOS/Paracaídas como `ChoiceField` en `AircraftForm` con opciones derivadas de la columna + defaults, y **normalización suave** (el valor guardado de cada fila siempre está en las opciones → editar no rechaza). Sin migración. — (orig.) VLOS/Paracaídas como texto libre → `ChoiceField`. Los datos actuales tienen valores libres ("VLOS", "NO"); pasar a choices exige normalizar o un choice "otro" para no rechazar registros existentes al editar. | `AircraftForm` |
| LV-29 | ✅ | P1 | **Vigencias DGAC como campos** (Bloque A implementado 2026-08-03; **deploy pendiente al cierre del batch LV-29..32, tras revisión del usuario** — trae migración `registry 0021`). Falta que el usuario **entregue la transcripción de las capturas SIGO** para poblar `load_dgac_vigencias` (hoy corre con `--file` CSV; fixture embebido vacío). (plan aprobado 2026-08-03, datos SIGO en capturas). `Operator.credential_expiry` + `Aircraft.insurance_expiry` (DateField null/blank, migración): columna en listas (badge Overdue/Due patrón LV-4 — **el campo reemplaza la anotación por documentos de LV-4**, `insurance_is_overdue` pasa a property, actualizar tests), `WATCHABLE_MODELS` += `registry.operator`/`registry.aircraft`, 2 reglas opcionales nuevas en `seed_alert_rules` (test 5→7), 2 fuentes nuevas en el feed del calendario (patrón qualification, `core/views.py:~594`), `upcoming_expirations()` del dashboard, campos en forms. Comando `load_dgac_vigencias` (fixture transcrito de las capturas: aeronave por matrícula↔N° inscripción, operador por credencial/nombre; idempotente, `--dry-run`, usuario verifica). Comando `notify_expiring_credentials` (email a cada operador con sus vencimientos ≤30d). | `registry/models.py`, `compliance/watchables.py`, `seed_alert_rules`, calendario |
| LV-30 | ✅ | P1 | **Registros operacionales + cumplimiento mensual** (Bloque B implementado 2026-08-03; **deploy pendiente al cierre del batch, trae migración `compliance 0011`**). (módulo nuevo; decisiones: ligados al CC con fecha, revisor único Dirección). (1) `DocumentType.is_operational_record` (migración) + 3 tipos sembrados: Bitácora REG-015, Checklist LVE-003, Inspección LVE-002 (test 6→9). (2) Página `/compliance/operational-records/` (patrón `CompanyDocumentsView`): docs con flag colgados de un CC, filtros CC+mes+tipo, subida prellenada, sidebar Cumplimiento. (3) Modelo `MonthlyComplianceReview` (cost_center, period=día 1, status pending/completed/non_compliant, reviewed_by, notes; unique cost_center+period) — regla por `status` = alerta viva mientras pending, se resuelve con `resolve_open_alerts_for` al marcar. (4) Comando `check_monthly_records` (diario vía timer, actúa solo el último día del mes 28/29/30/31): vuelos del mes vs registros por CC → crea reviews pending + email al revisor (destinatarios de `send_executive_report`). (5) Página `/compliance/monthly-review/` con acciones Cumple/No cumple + export CSV; tarjeta en dashboard "Registros del mes X/Y". Docs en compliance-setup.md (+ timer en scheduled-operations). | compliance (modelo+2 vistas+2 comandos), dashboard |
| LV-31 | 🔶 | P2 | **PARCIAL (Bloque C funcional, 2026-08-03)**: hechos (2) columnas reales en asignaciones de operador y aeronave (plantillas propias + parcial de filas + `htmx_template_name`) y (5) colapso de permisos multi-día en el calendario ("→ hasta DD-MM", un marcador en el inicio). **Diferido a revisión con capturas del usuario** (pasada estética): (1) reorden del panel, (3) contraste/tipografía de chips, (4) paleta global de badges/botones = LV-24, (5-resto) LV-23 grid de checkboxes. Ver [[aerocontrol-lv29-32-batch]]. — **Pasada ejecutiva/visual** (con capturas reales): (1) panel reordenado a acción (KPIs + tarjeta cumplimiento + vencimientos, gráficos después; el chart Kanban solo se mueve — standby); (2) lista de asignaciones de operador con columnas reales (Operador/CC/Estado/Propósito/Desde, parcial de filas patrón T5.6b) + espejo en asignaciones de aeronave; (3) chips de habilitaciones con más contraste/tipografía y columnas mejor repartidas; (4) paleta global de badges/botones (`bg-info` cian → subtle; sólidos → subtle salvo rojo peligro); (5) calendario: colapsar permisos multi-día ("→ hasta DD-MM"), sumar vencimientos de LV-29, revisar redundancia; LV-23 (grid checkboxes) entra aquí; (6) LV-25 VLOS/Paracaídas a ChoiceField con normalización suave. | `app.css`, plantillas de listas/panel/calendario |
| LV-32 | 🔶 | P2 | **PARCIAL — gran parte hecha en la pasada de diseño en vivo 2026-08-03** (LV-D1..D9): sistema de tablas (filas parejas, cabeceras con contraste, densidad/compactado por lista), KPIs ejecutivos (número protagonista + grilla pareja), franja de cumplimiento, pastillas legibles. Queda iterar detalles finos con más capturas del usuario. — **Modernización UX/UI general (propuesta de diseño)**: design pass sobre tokens `--ac-*` (sin JS nuevo, CSP intacto) — sistema de tablas (separación de filas, cabeceras con más contraste, densidad por tipo de lista, numéricos a la derecha, primera columna ancla), escala de espaciado/jerarquía uniforme (eyebrows en todas las páginas de módulo), acento por módulo en headers, KPIs ejecutivos (número protagonista + icono). Entregable: commit de propuesta (tokens+tablas+panel) → evaluación del usuario con capturas → iterar por LV-N. | `static/css/app.css` + plantillas |
| LV-26 | ✅ | P1 | **Seguimiento del estado de la aeronave + alerta de mantenimiento** ("el M300 debe ir a mantenimiento"). Ficha de aeronave: sección **"Mantenimiento y estado"** con las mantenciones abiertas (pending/in_progress) y botón **"Enviar a mantenimiento"** (crea `MaintenanceRecord` prellenado, modal). Nueva **regla de alerta "Mantenciones abiertas"** (`maintenance.maintenancerecord`/`status`, en `seed_alert_rules --with-optional`): `generate_alerts` ya vigila campos `status` (excluye `completed`), así que una mantención abierta queda como **alerta viva** en Alertas/dashboard. Al **completar**, `MaintenanceComplete` llama `compliance.alerts.resolve_open_alerts_for` → cierra la alerta sin paso manual. 3 tests. | `apps/maintenance/views.py`, `apps/compliance/alerts.py`, `aircraft_detail.html`, `seed_alert_rules.py` |

### FASE 6 — Nuevas funcionalidades `⏸ requiere FASE 0-3 cerradas`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T6.1 | ↪ | P2 | ~~Alertas programadas + notificación email~~ → consolidado y detallado en **BLOQUE 2** (más abajo) | M | FASE 3 |
| T6.2 | ↪ | P2 | ~~Checklists pre-vuelo cableando `source_object`~~ → consolidado en **BLOQUE 1** (más abajo, `source_object → Alert`, extensible a `FlightPermission`) | M | FASE 3 |
| T6.3 | ⏸ | P3 | Vista previa de adjuntos (U10) | S | — |
| T6.4 | ↪ | P3 | ~~Panel de auditoría en la UI~~ → consolidado en **BLOQUE 5** (B5.4, vista de auditoría de solo lectura) | M | T1.1 |
| T6.5 | ⏸ | P2 | Mantenimiento por horas/ciclos (campos nuevos) | L | FASE 3 |
| T6.6 | ⏸ | P3 | Gestión de baterías (modelo nuevo) | L | FASE 3 |
| T6.7 | ⏸ | P1 | **DJI Cloud API / telemetría** — diseñar SOLO tras estabilizar tenancy y constraints | XL | FASE 3 |

---

## Bloques de producto (plan externo integrado 2026-07-24)

> Origen: `PLAN_CLAUDE_CODE.md` y su revisión `PLAN_CLAUDE_CODE_1.md`, aportados por
> el usuario. Se integran aquí como bloques de funcionalidad concreta, con la misma
> disciplina de una rama por bloque (`codex/<bloque>`, no `feat/...` — ver `AGENTS.md`)
> y sin mezclar bloques en un PR. **B1 depende de T3.1** (proteger `Alert`/`AlertRule`
> de `CASCADE` — ya hecho).

### Ruta de ejecución (ORDEN OBLIGATORIO — no seguir el orden numérico)

Un bloque por sesión/PR, en esta secuencia (revisión `PLAN_CLAUDE_CODE_1.md`):

1. **BLOQUE 0** — higiene ✅ (falta solo el tag `v0.1.0-alpha`, TL.11).
2. **BLOQUE 1** — Alertas ⇄ Kanban ✅ (backend + UI, revisada en vivo).
3. **BLOQUE 2** — notificaciones y programación ✅ (incluye `JobRun`, adelantado del Bloque 5).
4. **BLOQUE 4** ✅ **COMPLETO** — B4.1 (validación de `AlertRule`), B4.2 (duplicados de operadores), **B4.3/B4.4 cerrados 2026-07-30** (habilitaciones DGAC estructuradas + aviso de compatibilidad operador–aeronave, con diseño aprobado por el usuario).
5. **BLOQUE 6.1 y 6.2** ✅ — Reporte documental determinista + informe ejecutivo por correo.

> **Ruta completa.** Los cinco pasos en alcance están cerrados. Conforme al plan, aquí se **detiene** la ejecución automática: lo que queda requiere instrucción explícita.

**Bloques DIFERIDOS (no ejecutar sin instrucción explícita):** BLOQUE 3 (UX Kanban, en standby además por decisión del usuario 2026-07-30 — ver LV-7), BLOQUE 5 (centro de administración, salvo `JobRun` ya adelantado), BLOQUE 6.3 (asistente IA).

### BLOQUE 1 — Integración Alertas ⇄ Kanban `rama codex/alertas-kanban`

`KanbanTask.source_object` (GFK) ya existe y solo se serializa en la API hoy; este bloque lo usa como vínculo real.

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B1.1 | ✅ | P2 | `AlertRule`: `create_kanban_task`, `target_board` (FK PROTECT), `target_stage` (FK PROTECT) + validación en `clean()` | M | T3.1 |
| B1.2 | ✅ | P2 | `generate_alerts` crea `KanbanTask` con `source_object=Alert`; título/descripción/`due_date`; prioridad por urgencia | M | B1.1 |
| B1.3 | ✅ | P2 | Derivar `assigned_to` (solo cuando la entidad vigilada es/expone un `Operator`; cost-center descartado por ser texto libre) | S | B1.2 |
| B1.4 | ✅ | P3 | Botón "Crear tarea" en alertas sin tarea: un clic, con fallback al tablero DGAC (decisión tomada: sin selector de tablero); permiso `add_kanbantask` + 403 test | S | B1.2 |
| B1.5 | ✅ | P3 | Origen visible en `_task_detail.html` con enlace a la lista de alertas filtrada (decisión: sin página de detalle de alerta por ahora) | XS | B1.2 |
| B1.6 | ✅ | P2 | `Alert.resolve()` mueve la tarea vinculada a la etapa `completed`, registrando `AuditEvent` (metadata) | S | B1.2 |
| B1.7 | ✅ | P2 | `Document.resolve_related_alerts()` al reemplazar un documento, con pruebas | M | — |
| B1.8 | ✅ | P2 | Idempotencia: `generate_alerts` dos veces no duplica tareas | S | B1.2 |
| B1.9 | ✅ | P3 | Comando `init_dgac_board` (tablero + etapas + etiquetas), `get_or_create`, idempotente | S | B1.1 |

**Aceptación del bloque:** pruebas de creación desde regla, creación manual, derivación de responsable, prioridad por urgencia, resolución automática, idempotencia y permisos 403; strings ES/EN; migraciones limpias; `verify.ps1` verde.

### BLOQUE 2 — Notificaciones y programación `rama codex/notificaciones` `✅ COMPLETO`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B2.0 | ✅ | P2 | Modelo `JobRun` + `apps.core.jobs.record_job_run` (registra ok/error y re-lanza); conectado a `generate_alerts`, `backup` y `send_alert_digest`; admin read-only (`f7e22d8`) | M | — |
| B2.1 | ✅ | P2 | `EMAIL_*`/`DEFAULT_FROM_EMAIL`/`SITE_BASE_URL` por entorno; consola por defecto si no hay `EMAIL_HOST` (`0b6eb75`) | S | — |
| B2.2 | ✅ | P2 | `send_alert_digest` con buckets vencidos/7/15/30, `--dry-run`, y aviso+continuación si un CC no tiene destinatario (`0b6eb75`) | M | B2.1 |
| B2.3 | ✅ | P3 | Plantillas de correo texto plano + HTML, traducidas (`0b6eb75`) | S | B2.2 |
| B2.4 | ✅ | P3 | `schedule_tasks.ps1` + `run-scheduled-job.ps1` (carga `.env`, propaga exit code) y `docs/scheduled-operations.md` con equivalente cron (`d88e000`) | S | B2.2 |
| B2.5 | ✅ | P3 | Log JSON por envío (destinatario, conteo, resultado); nunca el cuerpo (`0b6eb75`) | XS | B2.2 |

**Aceptación del bloque: cumplida.** 8 pruebas con `locmem` (destinatario, agrupación por urgencia, `--dry-run`, CC sin destinatario, CC sin vencimientos, `JobRun`), sin secretos en el repo, README + `docs/scheduled-operations.md` actualizados. Verificado además con datos reales de la demo: el correo sale en español con las secciones "Vencidos (1)" y "Vence en 7 días (1)".

**Decisión de diseño registrada:** se añadió `CostCenter.responsible_operator` (FK). El campo `responsible` es texto libre y sus valores importados ("J. Perez") no coinciden con ningún operador, así que emparejar por nombre no habría entregado ningún correo y podría acertarle a la persona equivocada. El texto se conserva como registro histórico (auditoría D17).

### BLOQUE 3 — Mejoras UX del Kanban `rama codex/kanban-ux` `⏸ DIFERIDO (no ejecutar sin instrucción)`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B3.1 | ⬜ | P2 | Agrupación por centro de costo/operador en el tablero (o alternativa más barata: agrupación en vista Lista + filtro rápido) | M | — |
| B3.2 | ⬜ | P2 | Vista "Mi trabajo": tareas asignadas al operador vinculado al usuario, en tablero y lista | S | — |
| B3.3 | ⬜ | P2 | Degradado de urgencia en tarjetas (≤30/≤15/≤7 días/vencida), accesible (no solo color) | S | — |
| B3.4 | ⬜ | P3 | Contadores por columna (total y vencidas) | XS | — |
| B3.5 | ⬜ | P3 | `wip_limit` opcional en `KanbanStage`; aviso visual al superarse, sin bloquear el drop | S | — |

**Aceptación del bloque:** pruebas de filtros/agrupación y render de urgencia; revisión de accesibilidad (teclado, contraste); ES/EN.

### BLOQUE 4 — Robustez de reglas y deuda de datos `rama codex/reglas-datos` `✅ COMPLETO (parte en alcance)`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B4.1 | ✅ | P2 | Registro `apps/compliance/watchables.py`: `entity_type`/`field_to_watch` validados en `clean()` y como choices en el form; `generate_alerts` deja la coincidencia difusa; migración 0006 normaliza y archiva las inválidas con nota (`c965644`) | M | — |
| B4.2 | ✅ | P2 | `find_duplicate_operators`: reporte con diferencias campo a campo y conteo de referencias; `--apply --group` fusiona (recorre FKs dinámicamente + GFK de Document/Alert), archiva con nota y registra `AuditEvent` (`cd0e197`) | M | — |
| B4.3 | ✅ | P2 | **Habilitaciones DGAC** (2026-07-30, aprobado por el usuario). `Qualification` reutilizado y estructurado: nuevo catálogo `QualificationType` (name/code/`model_keywords` para B4.4) con `qualification_type` convertido de texto libre a FK (migración `0014`, tabla vacía → swap limpio); CRUD del catálogo (list/create/update) enlazado desde el centro de administración; `registry.qualification` agregado a `DOCUMENTABLE_MODELS` (evidencia por `Document`); comando `seed_qualification_types` (7 familias de la flota real); las alertas de vencimiento ya existían (`registry.qualification`/`expiry_date`). `digest.py` y el calendario corregidos para el FK + `select_related`. | M | — |
| B4.4 | ✅ | P2 | **Compatibilidad operador–aeronave** (2026-07-30). `operator_aircraft_compatibility_gaps()` en `apps/registry/selectors.py`: compara las palabras clave de las habilitaciones vigentes del operador (`QualificationType.model_keywords`) contra `Aircraft.model` de cada aeronave del permiso. `FlightPermissionCreate.form_valid()` corre el chequeo tras guardar el M2M y muestra un **aviso no bloqueante** (`messages.warning`) por operador con las aeronaves sin cobertura — el permiso se guarda igual. 7 tests (selector + vista, con/sin vencimiento, sin palabras clave configuradas). | M | B4.3 ✅ |

**Aceptación del bloque (parte en alcance): cumplida.** B4.1 con 10 pruebas y migración verificada sobre la base de demo (normalizó un valor heredado y archivó una regla rota con nota); B4.2 con 12 pruebas, incluida la fusión de referencias por GFK, y verificada de punta a punta en la demo. B4.3/B4.4 siguen diferidos esperando aprobación de diseño.

**Decisión registrada (B4.2):** el registro que sobrevive a una fusión se elige por **cantidad de referencias** primero, no por campos rellenos. Probando con datos realistas, contar campos elegía un duplicado con poco uso que solo tenía un teléfono extra, en vez del registro que era responsable del centro de costo y tenía tarea asignada. La fusión es de un grupo por ejecución y hay que nombrarlo: no existe modo masivo.

### BLOQUE 5 — Centro de administración operativo `rama codex/admin-center` `🔄 PARCIAL — panel de situación (B5.1/B5.2/B5.4) hecho 2026-07-29`

Convertir `AdministrationCenterView` + `administration.html` en panel de situación, no solo menú.

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B5.1 | ✅ | P2 | Badges por métrica: alertas sin resolver, documentos que vencen ≤30 días, reglas activas, usuarios sin rol (un agregado por métrica, cada uno gateado por su `view_*`). (`bc17481`) | M | — |
| B5.2 | ✅ | P2 | Sección "Salud y operación": último respaldo (nombre+fecha+`sha256` del manifiesto en `BACKUPS_DIR`, `backups_dir()` compartido), última ejecución de cada `JobRun` con resultado + aviso >48 h para los diarios, estado de `/health/` (db + storage) reusado server-side. (`bc17481`) | M | B2.0 |
| B5.3 | ⏸ | P2 | **DIFERIDO** Acciones rápidas (POST + confirmación + permiso + `AuditEvent`): correr `generate_alerts`, digest `--dry-run`, respaldo. Solo acciones seguras/rápidas (nada que envíe correo real desde un botón); documentar el límite de ejecutar en el request | M | B2.0 |
| B5.4 | ✅ | P2 | Vista de auditoría de solo lectura (`AuditEventListView`, `core.view_auditevent`, filtrable por usuario/modelo/fecha, paginada, enlazada desde el centro). (`bc17481`) | M | — |
| B5.5 | ✅ | P3 | **Panel de usuarios y roles (solo lectura)** — `UserRoleListView` en `/administracion/usuarios/`, gateado por `auth.view_user`, lista usuarios con sus grupos/roles (+ badge superusuario), estado activo/inactivo, enlace al admin técnico; item read-only en la sección "Organización" del centro de administración. 2 tests (lista + 403 sin permiso). Cerrado 2026-07-30. | S | — |

### BLOQUE 6 — Reportes ejecutivos y asistente `rama codex/reportes-ejecutivos` (6.1/6.2 en la ruta; 6.3 diferido)

Depende de los Bloques 1 y 2.

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B6.1 | ✅ | P2 | Nivel 1 — reporte en pantalla + CSV/XLSX/DOCX + comando `compliance_report`; KPIs en `reports.py` compartidos con el correo; filtros persistidos en URL; neutralización de fórmulas vía `apps/core/exports.py` (`65d5bc2`) | L | Bloque 1 |
| B6.2 | ✅ | P2 | Nivel 2 — `send_executive_report --period week|month [--to] [--dry-run]` con comparación vs período anterior, XLSX adjunto, destinatarios por grupo *Dirección*, `JobRun` + log; tarea semanal en `schedule_tasks.ps1` y cron documentado (`65d5bc2`) | L | B6.1, B2.0, B2.1 |
| B6.3 | ⏸ | P3 | **DIFERIDO** Nivel 3 — asistente IA (`apps/assistant`): envía SOLO KPIs agregados/códigos (nunca nombres/archivos/datos crudos) a la API de Anthropic; API key solo por `.env`; degradable si no hay red; salida marcada "borrador" con aprobación humana; `AuditEvent` por generación. Proponer diseño antes de implementar | L | Aprobación del usuario |

**Aceptación (6.1/6.2): cumplida.** 18 pruebas: KPIs por urgencia con datos de prueba, aislamiento entre centros de costo, promedio alerta→resolución, neutralización de fórmulas, permisos 403 en la vista y en los tres exportes, escritura del XLSX, comparación entre períodos con `locmem` y `--dry-run`. Verificado en el navegador y por correo con los datos de la demo.

**Decisión registrada (B6.2):** cada KPI comparado declara si "menos es mejor", para que la redacción no contradiga el número (menos documentos vencidos es una mejora; menos vigentes, no). Sin destinatarios el comando falla con mensaje claro en vez de enviar a nadie en silencio.

### BLOQUE 6.3 — Asistente IA `⏸ DIFERIDO (requiere aprobación de diseño)`

No implementado por decisión del plan. Cuando se retome: app `apps/assistant` que envíe **solo KPIs agregados y códigos** (nunca nombres, archivos ni datos crudos), API key solo por `.env`, degradable si no hay red, salida marcada como borrador con aprobación humana, y `AuditEvent` por generación.

### BLOQUE GEO (7) — Editor geoespacial KMZ/KML `rama codex/geo-*` `⬜ PROPUESTA APROBADA — espera "go" de GEO-0`

Editor liviano de planificación RPA/UAS: importar KMZ/KML, interpretar la
estructura (carpetas/puntos/líneas/polígonos), editar, versionar de forma
inmutable, aprobar por rol y re-exportar KML/KMZ válido. Diseño completo en
[docs/dev/geo-editor-plan.md](docs/dev/geo-editor-plan.md). Supera la decisión
"archivar sí, interpretar no" (ver arriba). **Decisiones tomadas:** Leaflet +
Leaflet-Geoman (no MapLibre); `cost_center` obligatorio + `flight_permission`
opcional; OSM + Esri sin API keys; JSON canónico por versión (no GeoJSON, no
PostGIS); lxml endurecido. **No arranca sin "go" explícito del usuario.**

MVP = GEO-0..GEO-10 (hito *visor*: 0-7; hito *editor*: 8-10). V2 = GEO-11..GEO-14.

| ID | Est. | Tarea | Dep. | MVP |
|---|:--:|---|:--:|:--:|
| GEO-0 | ✅ | Fundaciones: app `apps/geo`, lxml a dep directa, `FILE_UPLOAD_MAX_MEMORY_SIZE`/`DATA_UPLOAD_MAX_MEMORY_SIZE` explícitos, enmienda a `docs/frontend-boundary.md` (islas JS admisibles), `static/vendor/` con política de SRI. **El binario de Leaflet/Geoman se difiere a GEO-7** (no se pueden bajar bytes exactos con SRI en este entorno). (`91fc8e1`) | — | ✔ |
| GEO-0b | ✅ | Quick-wins ortogonales: `set_audit_context` en `DocumentReplace` (`document_replaced` + `replaced_document_id`), `DocumentDelete`/`FlightRecordDelete` (`archived`) y `StatusTransitionView` (`status_changed`/`status_transition_rejected` con `from`/`to`, beneficia las 11 subclases de transición); handler `htmx:responseError` en el drag del Kanban que refresca el tablero y anuncia el rechazo por live-region (antes un 403/400 dejaba la tarjeta mal colocada sin aviso). 6 tests. | — | opc. |
| GEO-1 | ✅ | Modelos (`GeoPlan`/`GeoPlanVersion` append-only/`GeoPlanHistory`) + migración + `approve_geoplan` en `bootstrap_roles` + mapping en `signals.py` + admin. 9 tests (unicidad, cerrojos, historia, permisos por rol). (`7663727`) | GEO-0 | ✔ |
| GEO-2 | ✅ | Parser KML/KMZ endurecido (`apps/geo/kml/`) + canónico AeroKML JSON. 19 tests: corpus feliz + maliciosos (DOCTYPE, no-XML, no-ZIP, traversal, 200+ entradas, bomba de compresión, coordenada fuera de rango) + caps. (`95811d7`) | GEO-0 | ✔ |
| GEO-3 | ✅ | Generador `build.py` + **round-trip** (igualdad semántica con C14N, punto fijo, supervivencia de elementos no soportados). `pretty_print` desactivado a propósito para no romper la fidelidad byte a byte de los fragmentos crudos. 4 tests. (`fd2c638`) | GEO-2 | ✔ |
| GEO-4 | ✅ | Import (form + firmas/antivirus + parseo → `Document` `GEO_SOURCE` + `GeoPlan` + V1, atómico con `uploaded_file_cleanup`) + lista/detalle shell + enlace en el sidebar. 5 tests (403 add/view, import ok, rollback ante malicioso). Verificado en el navegador. **`ViewModelPermissions` a core se difiere a GEO-5** (lo necesita la API). (`4cf66e4`) | GEO-1, GEO-2 | ✔ |
| GEO-5 | ✅ | API lectura (meta, versiones, content con `ETag`/304 `If-None-Match`) + OpenAPI manual extendido. `ViewModelPermissions` promovido a `apps/core/api.py` (diferido de GEO-4) y reusado en workboard. Todo acotado a `geo.view_geoplan` (la versión se alcanza vía su plan). 11 tests (401/403, meta, lista sin content, canónico+ETag, 304, 404). (`fa04975`) | GEO-1 | ✔ |
| GEO-6 | ✅ | API commit + restore. Commit: `plan_locked` (autoritativa) → `If-Unmodified-Since` → `base_version` → `validate_document(reparse_raw)` → dedupe `no_change` → INSERT atómico con derivados recalculados en servidor + audit. `GeoPlanVersion.clean()` capa 2. Throttle scoped `geo-commit` 30/min. Endurecido `assert_wellformed_fragment` (rechaza DOCTYPE en fragmentos de commit) y corregido el contexto de auditoría perdido por el wrapper `Request` de DRF (workboard tiene el mismo bug latente, marcado aparte). 21 tests. OpenAPI extendido. (`5221068`) | GEO-5, GEO-3 | ✔ |
| GEO-7 | ✅ | Isla JS fase 1 (solo lectura): Leaflet 1.9.4 vendorizado con SRI + `.gitattributes -text` (cierra la pieza diferida de GEO-0/V.11), `GEO_TILE_PROVIDERS` (OSM + Esri, sin API keys) + CSP img-src, isla ES module (`static/js/geo/`) montada por `json_script`, render por folder, panel show/hide con conteos, mediciones (haversina/shoelace) y popups XSS-safe (`textContent`). Contraste dark-mode del layer-switcher corregido. Verificado en el navegador (demo :8011): mapa, tiles, features, toggle, popups. 2 tests de contexto de la vista. (`2d91482`) | GEO-4, GEO-5 | ✔ |
| GEO-8 | ✅ | Isla JS fase 2: Geoman 2.20.0 vendorizado con SRI (solo en páginas editables), edición punto/línea/polígono/rect + mover/vértices/borrar sincronizada al canónico por `uid`, inspector editable (name/description, `textContent`), undo/redo (pila de `structuredClone` capada a 50 + dirty), guardar vía `<dialog>` → commit API GEO-6 con CSRF, manejo 409 `conflict`/`plan_locked`/400/429 con banner y rescate local, `beforeunload`. Editable = `change_geoplan` **y** `is_editable`. Verificado en navegador (demo): Geoman con SRI, lógica de la isla contra Leaflet real, round-trip de commit 201. 3 tests de gating. (`c414eed`) | GEO-7, GEO-6 | ✔ |
| GEO-9 | ✅ | Workflow: 6 `StatusTransitionView` (draft→editing→in_review→approved\|rejected, rejected→editing, approved→editing con permiso `approve`) + botones en el shell por estado/permiso + historial vía señal `GeoPlanHistory`. El editor ya carga read-only en aprobados (GEO-8). 5 tests (403 por permiso, approve≠change, reopen, transición inválida sin cambio, historial). (`45bd74d`) | GEO-4 | ✔ |
| GEO-10 | ✅ | Export POST `/export/` (KML vía `build.py`; KMZ zip con `doc.kml` + copia byte a byte de `kmz_resources` del original, con guards) acotado a `view_geoplan` + throttle `geo-export` 10/min + audit; UI de export KML/KMZ y botones de restore por versión en el panel. OpenAPI extendido. 6 tests (401/403, KML, KMZ es zip con doc.kml, versión por defecto, formato inválido, 404). (`45bd74d`) | GEO-6, GEO-3 | ✔ |
| GEO-11 | ✅ | Capas avanzado: árbol anidado con visibilidad por nodo, **drag&drop** (mover entre folders/reordenar), **duplicar** (clon con uids nuevos) y **explotar MultiGeometry** (split por vértice diferido). Todo cliente (`doc.js` mutadores puros + `panel.js` `buildTree` + `main.js` capas por uid + `edit.js` inserción folder-aware); servidor sin cambios (el commit re-valida el árbol). Verificado en navegador (demo): duplicar 8→9, explotar "Torres", undo por gesto 10→9→8, commit 201. Test server de labels. (`bba7eb8`). Diseño: [docs/dev/geo-v2-plan.md](docs/dev/geo-v2-plan.md) | GEO-8 | V2 |
| GEO-12a | ✅ | **Diff visual entre versiones** (por `uid`, 100% cliente): selector A↔B en la cabecera del mapa (visible también a viewers), `diff.js` puro compara ambos canónicos del content API, el target se pinta por estado (verde=agregado, ámbar=cambiado/movido, gris=igual) + fantasmas rojos de los eliminados + leyenda con conteos; el toolbar de Geoman se suspende en modo diff. Sin cambio de servidor (solo `versions` + labels en `map_config`). Verificado en navegador: v2↔v3 reporta "Agregado=1", salir restaura el árbol. (`6e3e669`) | GEO-10 | V2 |
| GEO-12b | ⬜ | **[DIFERIDO]** Edición de `ExtendedData` (pares `Data` simples). Toca el round-trip: regenerar `raw_xml` desde `pairs` + `_iter_raw_fragments` + test. Requiere decisión aparte | GEO-10 | V2 |
| GEO-13a | ✅ | **Iconos embebidos servidos**: endpoint `GET .../resource/?name=` (`view_geoplan`, whitelist contra `kmz_resources`, guards de `kmz.py`, content-type seguro + `nosniff`); la isla renderiza `L.marker` con el icono real del KMZ (same-origin, iconos http externos ignorados por CSP). Sin cambio de round-trip. 3 tests. (`9983027`) | GEO-10 | V2 |
| GEO-13b | ⬜ | **[DIFERIDO]** StyleMap highlight editable + validación XSD: alto riesgo de round-trip / bajo ROI para un editor liviano. No recomendado por ahora | GEO-10 | V2 |
| GEO-14 | ⬜ | **[DIFERIDO]** Hooks DJI: interfaz `MissionExporter` + comparación planificado-vs-ejecutado. Depende de archivos WPML/telemetría reales de la flota para diseñarse | GEO-10 | V2 |

**No bloquea T3.2** (tenancy): el scoping entra por `cost_center` como el resto y la migración futura lo cubre. GEO-0 absorbe parte de T5.9 (vendorización+SRI) y prepara V.10 (CSP).

### BLOQUE OPS (8) — Seguimiento de contratos, recursos y permisos `rama codex/ops-*` `✅ CERRADO 2026-07-27 — OPS-0..OPS-8 completos`

Cerrar la brecha entre el modelo actual y cómo opera de verdad una empresa RPAS
bajo DGAC: asignaciones ancladas al centro de costo (= contrato) con **log de
movimientos** inmutable, ubicación física de aeronaves, permisos de vuelo espejo
de la autorización DGAC (rango de vigencia, varios operadores y aeronaves,
ubicación estructurada), ficha del contrato por pestañas e historiales separados
por entidad. Diseño completo en
[docs/dev/ops-contract-tracking-plan.md](docs/dev/ops-contract-tracking-plan.md).
Nace del feedback de producto del equipo (2026-07-27), contrastado con la
autorización DGAC N°5808 y la plataforma SIGO. **Decisiones tomadas:**
asignaciones separadas por recurso (operador→CC, aeronave→CC); permiso espejo
DGAC; log append-only patrón `AuditEvent`; la asignación vigente es la fuente de
verdad y `Operator/Aircraft.cost_center` quedan como denormalización. **No
arranca la implementación sin "go" explícito del usuario.**

| ID | Est. | Tarea | Dep. |
|---|:--:|---|:--:|
| OPS-0 | ✅ | Propuesta técnica + investigación de competidores (Aloft/DroneLogbook/Airdata) + tablero. (`docs/dev/ops-contract-tracking-plan.md`) | — |
| OPS-1 | ✅ | `OperatorAssignment`/`AircraftAssignment` (base común, validación de solape en `clean()`), `ResourceMovementLog` append-only, señal en `apps/registry/signals.py` que mantiene `Operator/Aircraft.cost_center` y escribe el log (assigned/reassigned/released), migración de datos idempotente y no destructiva desde `Assignment` (**el viejo modelo y el calendario siguen intactos a propósito** — el corte del calendario al nuevo modelo no es parte de este alcance, queda para cuando se aborde OPS-6), roles y admin (log read-only). CRUD completo (list/detail/create/update/archive/restore) + vista de solo lectura del log filtrable por tipo de recurso + enlaces de navegación. 15 tests (solape, denormalización, tipos de movimiento, `changed_by_user`, aeronave, append-only, permisos 403 de las vistas nuevas, solape rechazado vía formulario, filtro del log). (`564b6a9`, `45b59f5`) | OPS-0 |
| OPS-2 | ✅ | Ficha del contrato: `CostCenterDetail` con pestañas (Resumen/Equipo/Flota/Permisos/Documentos/Historial, cada una separada — corrige el defecto de SIGO de mezclarlas), cada pestaña acotada por su propio permiso (mismo patrón `CALENDAR_EVENT_PERMISSIONS` del calendario: falta el permiso → desaparece la pestaña, no la página). Badge de credencial vencida en Equipo, badge de condición en Flota. 11 tests (403, gating por pestaña, contenido). (`e42cdfc`) | OPS-1 |
| OPS-3 | ✅ | Ubicación física de aeronaves (`current_location`/`current_site`, eje separado de `status`) + validación en `clean()` + señal `pre_save` que escribe `location_changed` en el log (from/to solo mientras `on_site`, así aparece gratis en el Historial de OPS-2) + badges en la lista y en la pestaña Flota. Migración de datos: todo el parque existente parte en `headquarters`. 10 tests. (`67765db`) | OPS-1 |
| OPS-4 | ✅ | `FlightPermission` espejo DGAC: `operators`/`aircraft_fleet` M2M, `valid_from`/`valid_until` con validación de rango, `cost_center` sigue FK única. Migración aditiva + backfill a mano (0009/0010). Arreglado en el camino: `merge_operators` no soportaba relaciones M2M inversas, `CsvExportMixin` perdía columnas M2M en silencio, ambos calendarios (grilla mensual y feed JSON) y un bug preexistente en `OCreate.get_success_url()` que nadie había detectado (ningún test posteaba una creación exitosa hasta ahora). 17 tests nuevos/actualizados. **Pendiente:** ubicación estructurada (región/comuna/coordenadas) — diferida a propósito, igual que el pase visual de OPS-8. (`d82fb8d`) | OPS-0 |
| OPS-5 | ✅ | Adjuntos en el permiso: `FlightPermission` ya estaba en `DOCUMENTABLE_MODELS` (el pipeline genérico de `Document` ya lo soportaba) — el hueco era solo de UI. Sección de documentos en el detalle (acotada por `view_document`) + link de carga pre-llenado (`DocumentCreate.get_initial()`, mismo patrón que `FlightRecordCreate`). 4 tests. (`6f53a3e`) | OPS-4 |
| OPS-6 | ✅ | Timeline propio en la ficha de Operador y de Aeronave (reemplaza la vista genérica, mismo patrón que `CostCenterDetail` de OPS-2). La aeronave combina reasignaciones (OPS-1) y cambios de ubicación (OPS-3) en una sola consulta — ambos escriben al mismo `ResourceMovementLog`. Extraída la lógica de resolución de etiquetas a `apps/registry/selectors.py` (evita una 4ª copia) y la tabla de campos a un partial compartido. Permiso (`PermissionHistory`) y Contrato (`CostCenterDetail`) ya tenían el suyo. 4 tests. (`73cc51f`) | OPS-1..4 |
| OPS-7 | ✅ | `GeoPlanPermissionLink`: log append-only de cuándo cambia `GeoPlan.flight_permission` y a qué permiso (señal `pre_save` dedicada, no se sobrecarga `GeoPlanHistory` que es solo transiciones de estado). Visible sin permiso propio en el detalle del plan (misma página ya gateada por `view_geoplan`). 6 tests. (`ab63803`) | OPS-4, GEO-1 |
| OPS-8 | ✅ | Filtro global `?cost_center=` aplicado a cada métrica con ruta directa o de un salto a `CostCenter` (aeronaves, operadores, vencimientos, permisos, mantenimiento, vuelos mensuales); id inválido o archivado se ignora en silencio. Deliberadamente **no** filtrado: Kanban (escala por tenant/acceso al tablero, eje distinto) y alertas (genéricas, requiere resolución por tipo de entidad aparte). Pase visual (preferencias del usuario: tipografía system-ui nativa — ya vigente, sin cambio — y más densidad): gutters/márgenes/paddings reducidos en el dashboard + limpieza de una regla `.summary-card` muerta que forzaba texto blanco (hazard de "dos generaciones de tokens" ya documentado). 5 tests. (`ada6a79`, `0eda5a4`) | OPS-2 |

**Migración de datos es el riesgo principal** (14 aeronaves y 41 operadores reales cargados): migraciones idempotentes, backup previo, pruebas sobre copia de `aero_ops.sqlite3`. Toca la deuda F-08 (tenancy) sin ampliarla.

### FASE L — Limpieza y orden del repositorio `puede correr en paralelo a FASE 0`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| TL.1 | ✅ | P2 | Corregir `openspec/config.yaml` (metadatos falsos) | XS | — |
| TL.2 | ✅ | P2 | `BACKLOG.md` → registro histórico que apunta a este plan | XS | — |
| TL.3 | ✅ | P3 | Eliminar artefactos temporales sueltos (`.tmp-*.sqlite3`, `.tmp-check-logs/`) | XS | — |
| TL.4 | ✅ | P2 | Sacar `.agents/skills/impeccable/` del repo (aprobado por el usuario) | S | — |
| TL.5 | ✅ | P3 | Borrar `.atl/skill-registry.md` y `prompts/` (aprobado por el usuario) | XS | — |
| TL.6 | 🔄 | P2 | Merge a `main` preparado (fast-forward, verificado); falta el `push`. Poda de ramas inventariada más abajo ("Inventario de ramas"), pendiente de ejecución por el usuario | M | FASE 0 |
| TL.7 | ✅ | P3 | Los 5 PRs de Dependabot aplicados **directo sobre el main actual**, no fusionando las ramas (nacían de un main muy viejo; su diff tocaba todo el árbol). pip: crispy-bootstrap5 2025.6→2026.3 + django-crispy-forms 2.4→2.6 (`d8d5b7c`, acoplados), ruff 0.12.0→0.15.22 (`3b1e83a`, un reformateo estilístico). Actions: checkout v4→v7 + setup-uv v6→v7 (`4b45a33`). `uv lock` resolvió sin conflicto con Django 6.0; verify.ps1 verde en cada bump. Los PRs se auto-cierran al llegar las versiones a `origin` | S | T0.3 |
| TL.8 | 🔄 | P2 | Consolidar `openspec/`. **Hecho:** los 5 changes al 100% movidos a `openspec/changes/archive/`, así que `changes/` solo contiene trabajo vivo (`ui-modernization`, con su tarea de PR cerrada por el merge); `config.yaml` sincronizado (124→269 tests, umbral de cobertura real). **Pendiente:** `openspec/specs/`, que no es un movimiento de archivos — ver "Deuda de `openspec/specs/`" | M | — |
| TL.9 | ✅ | P2 | Ampliar `AGENTS.md`: DoD por tipo de cambio, contrato de lectura, reglas de commit, precedencia documental | S | — |
| TL.10 | ✅ | P3 | `.github/pull_request_template.md` con casillas derivadas del DoD real de `AGENTS.md` (no genéricas), sección de riesgo y "lo que queda fuera" | XS | — |
| TL.11 | 🔄 | P3 | `CHANGELOG.md` cerrado: la sección `[Unreleased]` pasó a `[0.2.0-alpha] - 2026-07-24`. **Corrección:** `[0.1.0-alpha]` ya describía `main` en el merge del PR #9, así que ese tag apunta a `9eb40ee`, no al trabajo de estabilización. Quedan los dos comandos de tag, que ejecuta el usuario (del plan externo, Bloque 0) | S | TL.6 |
| TL.12 | ✅ | P2 | Reordenar `docs/`: producto en raíz, notas internas en `docs/dev/` (plan externo, Bloque 0) | S | — |
| TL.13 | ✅ | P3 | Rutas de ejemplo genéricas en README/.env.example/ARCHITECTURE.md/chapter1-import.md (plan externo, Bloque 0) | XS | — |
| TL.14 | ✅ | P2 | Índices `Alert(is_resolved,is_active)`, `Document(expiry_date,is_current_version)`, `KanbanTask(board,stage,order)` (plan externo, Bloque 0) | S | — |
| TL.15 | ✅ | P3 | Log JSON estructurado (`compliance.alerts`) para reglas de alerta inválidas en `generate_alerts` (plan externo, Bloque 0) | XS | — |

---

## Detalle de las tareas de FASE 0 — ✅ completada 2026-07-24

> Las 7 tareas quedaron implementadas y verificadas en `codex/impeccable-ui-audit`
> (commits `7dc4151`, `0ed12c5`, `4bf76ed`, `86c57ce`, `0af0c82`, `dab1538`, `83d48a9`).
> Se conserva el detalle como referencia de lo que se hizo y por qué.

### T0.1 — Bloque `extrahead` duplicado *(PRIMERA TAREA)*
- **Evidencia:** AUDIT_CLAUDE.md §6/§23; `templates/dashboard/index.html:4` y `:128`.
- **Cambio:** eliminar el `{% block extrahead %}` de la línea 4 y mover su `<script defer chart.js>` al bloque de las líneas 128-131, dejando **un solo** `extrahead`. No tocar `base.html` ni la vista.
- **Aceptación:** `uv run pytest` 0 fallos; login→dashboard 200 con los 5 gráficos; solo cambia `templates/dashboard/index.html`.
- **Prompt para Codex:** ver AUDIT_CLAUDE.md §23.

### T0.2 — Cierre de mantenimiento
- **Evidencia:** F-02; `apps/maintenance/views.py:112-127`, `templates/maintenance/record_detail.html`.
- **Cambio:** renderizar `completion_form` (crispy) en `record_detail.html` cuando la vista lo pasa, para capturar `performed_by` y `cost`.
- **Aceptación:** completar una mantención `in_progress → completed` funciona y muestra errores si faltan campos; test de la transición (parte de T4.3, mínimo un caso aquí).

### T0.3 — Gate que realmente falla
- **Evidencia:** F-09; `scripts/verify.ps1:8-14` (verificado: `$PSNativeCommandUseErrorActionPreference=False`, un exit≠0 no lanza excepción).
- **Cambio:** `if ($LASTEXITCODE -ne 0) { throw "Fallo: <paso>" }` tras cada invocación (o fijar `$PSNativeCommandUseErrorActionPreference=$true` al inicio). Alinear `verify.ps1` con CI (añadir `check --deploy`, `compile_translations`, `--cov`).
- **Aceptación:** con un test forzado en rojo, `verify.ps1` termina con código ≠0.

### T0.4 — Umbral de cobertura
- **Evidencia:** F-11; `.github/workflows/ci.yml:30`.
- **Cambio:** `--cov-fail-under=<línea base actual>` en CI; `[tool.coverage]` en `pyproject.toml`. Subir el número con cada PR (ratchet). Mejor: mínimo por app para exponer `maintenance`/`dashboard` a 0%.
- **Aceptación:** CI falla si la cobertura baja del umbral.

### T0.5 — Compilación de plantillas en CI
- **Evidencia:** causa de T0.1; `manage.py check` no compila plantillas.
- **Cambio:** test que haga `get_template()` de las 43 plantillas (o comando dedicado en el gate).
- **Aceptación:** un bloque duplicado o error de sintaxis en cualquier plantilla hace fallar CI.

### T0.6 — Sincronizar metadatos
- **Evidencia:** F-12; `openspec/config.yaml:8,28,38-49`, `docs/dev/03-Roadmap.md`.
- **Cambio:** (parcialmente hecho, ver TL.1) marcar en `docs/dev/03-Roadmap.md` las 13 casillas ya implementadas.
- **Aceptación:** ningún doc afirma capacidades falsas del proyecto.

### T0.7 — Formato
- **Evidencia:** `ruff format --check` falla en 35 archivos.
- **Cambio:** `uv run ruff format .` y commit del reformateo (idealmente en su propio commit «style:»).
- **Aceptación:** `verify.ps1` verde de punta a punta.

---

## Reglas de trabajo con agentes

> El contrato completo vive en [AGENTS.md](AGENTS.md) (precedencia documental, contrato de lectura, DoD por tipo de cambio, convención de ramas). Resumen aplicado a este tablero:

1. **Una intención por rama y por commit**, rama `codex/<área-o-bloque>` (no `feat/...`). Nunca mezclar tooling/dependencias con producto (el commit `980b763` con 62.661 líneas es el anti-ejemplo).
2. **Definition of Done por tipo de cambio** (detalle en `AGENTS.md`): modelo → migración + test de constraint; vista → test 403 + test de scope de tenant; comando → test camino feliz + error; formulario → test por cada `add_error`.
3. **Contrato de lectura (causa de F-05/F-06):** toda vista que expone datos de dominio exige `view_*` y acota por tenant.
4. **El gate manda:** ninguna tarea se marca ✅ sin `pwsh scripts/verify.ps1` verde y sin cumplir su criterio de aceptación.
5. **No implementar FASE 6 antes de cerrar FASE 0-3.** DJI/telemetría/PostgreSQL/Celery están diferidos por diseño (YAGNI). Los **BLOQUE 1-4** de producto sí pueden avanzar en paralelo (ver nota de dependencia de B1 con T3.1).
6. **B4.3/B4.4 (habilitaciones DGAC, compatibilidad operador-aeronave) se entregan primero como propuesta de diseño en el PR**, y se implementan solo tras validación del usuario.

---

*Este plan reemplaza como fuente de trabajo pendiente a la sección «pendiente» de `BACKLOG.md`. Evidencia completa en [AUDIT_CLAUDE.md](AUDIT_CLAUDE.md).*
