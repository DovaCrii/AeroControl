# AUDIT_CLAUDE.md — Auditoría técnica de AeroControl

> **Autor:** Claude Code (auditor / arquitecto / challenger)
> **Fecha:** 2026-07-24
> **Rama auditada:** `codex/impeccable-ui-audit` (HEAD `75e56f2`; `main` está 25 commits por detrás)
> **Alcance:** auditoría y planificación. **No se implementó ningún cambio de código.** El único archivo creado es este documento.
> **Método:** ejecución de la batería de verificación (`check`, `check --deploy`, `pytest --cov`, `ruff`, `bandit`, `pip-audit`, `makemigrations --check`), más cuatro barridos de código en paralelo (arquitectura/datos, seguridad, testing/DevEx, UX/UI/producto). Cada hallazgo P0/P1 fue **confirmado por lectura directa del código o por ejecución**, no solo reportado.

**Convención de etiquetas:**
- **HECHO** — comprobado directamente en el código o ejecutando una herramienta.
- **INFERENCIA** — deducción de alta probabilidad a partir de la arquitectura, no ejecutada.
- **RECOMENDACIÓN** — mejora propuesta.

**Prioridades de seguridad/severidad:** P0 crítico · P1 alto · P2 medio · P3 bajo.

---

## 1. Executive Summary

AeroControl es un monolito Django modular **razonablemente bien construido en sus cimientos** (auditoría append-only con guardas reales, validación de firma de archivos, neutralización de inyección de fórmulas CSV, API DRF con default-deny y concurrencia optimista, hardening de producción correcto), pero **inestable en su estado actual y con deuda estructural que es barata de pagar hoy y muy cara mañana**.

Los tres mensajes centrales de esta auditoría:

1. **Hay un P0 vivo en la rama activa.** `templates/dashboard/index.html` declara dos veces `{% block extrahead %}` (líneas 4 y 128). Como `LOGIN_REDIRECT_URL = "/"` apunta al dashboard, **cualquier usuario que inicie sesión aterriza en un error 500**. Verificado ejecutando `pytest` (7 tests en rojo) y el compilador de plantillas. `main` no tiene este bug; lo introdujo el commit `c6025d5` en esta rama.

2. **El aislamiento multi-tenant es aspiracional, no real, y varias decisiones de modelo de datos serán irreversibles con datos de producción.** Hoy 17 de 21 modelos no tienen `tenant`, el campo es nullable y nunca se asigna desde formularios, y la regla de scoping por OR sobre tres FKs filtra registros mixtos a ambos tenants. Además hay `on_delete=CASCADE` en el expediente documental de cumplimiento y cero `CheckConstraint` en todo el proyecto. **Estas correcciones cuestan una migración trivial ahora y son irrecuperables tras acumular datos reales.**

3. **No se puede confiar en ninguna señal automatizada actual.** El gate obligatorio `scripts/verify.ps1` no comprueba códigos de salida (un `pytest` rojo puede reportar éxito), CI mide cobertura y la descarta, `openspec/config.yaml` afirma falsamente que "no hay runner de tests", y `docs/dev/03-Roadmap.md` lleva 13 casillas sin marcar de trabajo ya hecho. **Reparar las señales es prerequisito de todo lo demás**, incluida cualquier revisión asistida por IA.

La recomendación de proceso del usuario es correcta: **detener la incorporación de DJI Cloud API y estabilizar el núcleo primero.** El riesgo de adaptar la aplicación alrededor de una integración externa antes de fijar el modelo de tenancy y las constraints de datos es alto y transversal.

**No hay ningún hallazgo de seguridad P0.** Todas las fugas requieren un usuario autenticado y su impacto se materializa al pasar al servidor centralizado; hoy están mitigadas por `tenant = NULL` universal. Son gaps de código reales que deben cerrarse antes de centralizar, no emergencias.

---

## 2. Estado general del proyecto (puntuación 1–10)

| Dimensión | Nota | Justificación (una línea) |
|---|:--:|---|
| Arquitectura | **5** | Modular y con buenas piezas, pero `core` es un god-module con ciclo de dependencias e imports diferidos; vista de calendario de 231 líneas acoplando 6 apps. |
| Calidad de código | **5** | Código legible, pero tres estilos de declaración de vistas coexisten, código muerto sin detectar, y `ruff format` fallaría en 35 archivos en esta rama. |
| Seguridad | **6** | Cimientos fuertes (CSRF, auditoría, uploads, DRF); pero autorización solo a nivel de modelo (sin objeto/tenant) en varias vistas de lectura, y el gate no falla. |
| Testing | **4** | 87 tests, pero `maintenance` y `dashboard` a 0%, `generate_alerts` a 0%, sin tests de aislamiento de tenant, y ~14 tests de bajo valor. |
| Modelo de datos | **4** | `CASCADE` peligrosos, cero `CheckConstraint`, tenancy a medias, sin `db_index`: todo barato ahora, doloroso con datos reales. |
| Mantenibilidad | **5** | Buenas abstracciones (mixins, `selectors.py` en workboard) conviven con duplicación (5 pares List/Create, 3 representaciones de tarea). |
| Documentación | **4** | Mucha documentación, pero deriva severa: `openspec/config.yaml` y `docs/dev/03-Roadmap.md` congelados en el día 1. |
| DevEx | **5** | `AGENTS.md` denso y útil, estructura openspec correcta; pero gate roto, metadatos falsos y 62.661 líneas de tooling JS vendorizado. |
| Preparación para crecer | **5** | Switch a PostgreSQL listo, storage abstraído; pero el modelo de tenancy debe arreglarse antes de tener datos, o bloqueará la centralización. |

**Promedio: 4.8 / 10** — un proyecto con buen ADN de ingeniería en fase alpha, que necesita una pausa de estabilización disciplinada antes de crecer.

---

## 3. Arquitectura actual

**Stack (HECHO):** Django 6.0.7 · Python 3.12 · uv · SQLite por defecto con switch a PostgreSQL vía `DB_ENGINE` · DRF (token + sesión) · WhiteNoise · Bootstrap 5 + crispy-forms + HTMX + Chart.js + FullCalendar + SortableJS (todos por CDN) · i18n es/en · renderizado server-side.

**Apps (7):**

```
core        Infra (BaseModel, mixins de vista, middleware, audit, imports)
            + dominio transversal (calendario unificado, búsqueda global,
              centro de administración, tenancy) ← mezcla de responsabilidades
registry    CostCenter, Aircraft, Operator, Assignment, Qualification
compliance  DocumentType, Document (GFK), AlertRule, Alert
operations  FlightPermission, FlightRecord, PermissionHistory
maintenance MaintenanceRecord, MaintenanceHistory
workboard   Kanban genérico (Board/Stage/Label/Task/Checklist/Access) + API DRF
dashboard   Sin modelos: una FBV de agregación y una URL
```

**Grafo de dependencias (HECHO):** `registry`, `compliance`, `operations`, `maintenance`, `workboard` dependen de `core` (a nivel de módulo). `dashboard` depende de las otras 5 (top-level, `apps/dashboard/views.py:8-12`). **`core` a su vez depende de las 5 apps de dominio**, pero mediante *imports diferidos dentro de funciones* (`apps/core/views.py:228-232`, `:476-478`, `:514-516`; `apps/core/signals.py:12-13`) para no romper. Esto es el síntoma de que `core` no es una capa base pura, sino una app de dominio con nombre equivocado.

**Dónde vive la lógica de negocio (HECHO):** `ARCHITECTURE.md:58` declara "Fat models, thin views" y "no business logic in templates". El código incumple ambas de forma sistemática: reglas de solapamiento de asignaciones solo en el form (`apps/registry/forms.py:107-123`), coherencia de FlightRecord solo en el form (`apps/operations/forms.py:41-54`), transiciones de estado en la vista (`apps/core/views.py:568-592`), y agregación de calendario en la plantilla (`templates/core/calendar.html:56`).

---

## 4. Fortalezas

Lo que está bien hecho y **no debe tocarse** en la estabilización (HECHO, verificado):

1. **Auditoría append-only real.** `AuditEvent` bloquea `save`/`delete`/`update`/`bulk_update` a nivel de manager y de instancia (`apps/core/models.py:49-92`), admin read-only (`apps/core/admin.py:15-22`), con tests que lo ejercen (`apps/core/tests.py:282-299`).
2. **Pipeline de subida de documentos sólido.** Validación de **firma binaria real** ignorando el `content_type` del cliente, límite de 20 MB, antivirus opcional sin inyección de comando (`shutil.which` + lista de argumentos, sin `shell=True`), y anti-path-traversal doble en storage (`apps/compliance/forms.py:127-169`, `apps/compliance/security.py:9-37`, `apps/compliance/storage.py:37-54`).
3. **Documentos fuera del web root.** No hay ninguna ruta que sirva `MEDIA_URL`; la única salida es `DocumentDownload` con `FileResponse(as_attachment=True)` + `nosniff`.
4. **API DRF con default-deny.** `IsAuthenticated` global, `ViewModelPermissions` exige `view_*` también en GET, scoping por tenant y `KanbanBoardAccess`, allowlist estricta de campos en PATCH y concurrencia optimista con `If-Unmodified-Since` (`apps/workboard/api.py`). Es la parte mejor protegida del sistema.
5. **CSRF sin excepciones.** Cero `csrf_exempt` en el repo; HTMX inyecta `X-CSRFToken` en todas las peticiones, incluido el drag&drop.
6. **Logging limpio de datos sensibles.** `JsonLogFormatter` emite solo `request_id/method/path/status/duration`; `AuditEvent.metadata` guarda claves de querystring, no valores.
7. **Hardening de producción correcto.** `config/settings/prod.py` aborta sin `ALLOWED_HOSTS`, activa HSTS + preload, cookies seguras, SSL redirect. `manage.py check --deploy` con settings de prod **pasa limpio** (verificado).
8. **Importadores CSV con revert transaccional** y neutralización de inyección de fórmulas en exportaciones (`apps/core/views.py:92-95`).
9. **CI con controles de seguridad reales** (`bandit`, `pip-audit`, `check --deploy`). `pip-audit` reporta **cero vulnerabilidades** (verificado).

---

## 5. Problemas encontrados (resumen)

| ID | Sev. | Título | Evidencia principal |
|---|:--:|---|---|
| **F-01** | P0 | Dashboard/home lanza 500 tras login | `templates/dashboard/index.html:4,128` |
| **F-02** | P1 | Cierre de mantenimiento imposible (callejón sin salida silencioso) | `apps/maintenance/views.py:112` + `record_detail.html` |
| **F-03** | P1 | IDOR en workboard: checklist/StageCreate sin verificar acceso al tablero | `apps/workboard/views.py:268-292,380-394` |
| **F-04** | P1 | `/workboard/tasks/` y `/boards/` evitan el scoping de tableros | `apps/workboard/views.py:295-309` |
| **F-05** | P1 | Descarga de documentos sin autorización a nivel de objeto/tenant | `apps/compliance/views.py:130-143` |
| **F-06** | P1 | `/calendar/` y Kanban HTML no exigen permisos de dominio | `apps/operations/views.py:193`; `apps/workboard/views.py:315` |
| **F-07** | P1 | Modelo de datos: `on_delete=CASCADE` destruye expediente de cumplimiento | `apps/compliance/models.py:34,59,60` |
| **F-08** | P1 | Tenancy incompleta e irreversible con datos reales | 17/21 modelos sin `tenant`; scoping OR que filtra a ambos |
| **F-09** | P1 | Gate obligatorio `verify.ps1` no falla ante tests rojos | `scripts/verify.ps1:8-14` |
| **F-10** | P1 | Cero `CheckConstraint`; ~11 invariantes solo en forms | `grep AddConstraint` en 21 migraciones |
| **F-11** | P2 | CI mide cobertura y la descarta; `maintenance`/`dashboard` a 0% | `.github/workflows/ci.yml:30` |
| **F-12** | P2 | `openspec/config.yaml` y `docs/dev/03-Roadmap.md` gravemente desactualizados | `openspec/config.yaml:8,38,41` |
| **F-13** | P2 | Paginación HTMX muerta en 3 listados | `permission_list.html:47`, `record_list.html:16`, `alert_list.html:4` |
| **F-14** | P2 | Búsqueda global e importadores sin enlace en la UI | `apps/core/views.py:500`; `templates/base.html:53-80` |
| **F-15** | P2 | `app.css` son dos sistemas de diseño apilados con duplicados | `static/css/app.css:2-7` vs `:653-669` |
| **F-16** | P2 | `.agents/skills/impeccable/` — 62.661 líneas de tooling JS vendorizado | commit `980b763` |
| **F-17** | P2 | CSP imposible de activar en enforcing; dependencias front sin SRI | `apps/core/middleware.py:36-43`; `templates/base.html:9-11` |
| **F-18** | P3 | Código muerto, fugas de i18n, badge siempre rojo, artefactos temporales | ver §16, §14 |

**Falso positivo descartado por verificación directa:** un barrido inicial señaló `models.NullBooleanField` en `apps/core/templatetags/aero_tags.py:15` como posible ruptura de todas las páginas de detalle. **Verificado: `hasattr(models, "NullBooleanField")` devuelve `True` en Django 6.0.7** — la clase sigue existiendo, el `isinstance` no rompe. No es un hallazgo.

---

## 6. Hallazgos P0

### F-01 · El dashboard lanza 500 para cualquier usuario autenticado — **HECHO (verificado ejecutando)**

**Problema:** `templates/dashboard/index.html` declara `{% block extrahead %}` dos veces: en la línea 4 (`<script chart.js>`, añadido por el commit `c6025d5 "perf: load charts only on dashboard"`) y en la línea 128 (el original con `json_script`). Django prohíbe bloques duplicados.

**Evidencia:**
```
TemplateSyntaxError: 'block' tag with name 'extrahead' appears more than once
```
`pytest` reporta 7 tests en rojo por esta causa (`apps/core/tests.py::TestChapter1DocxImport::test_dashboard`, `TestAuthRequiredURLs[...dashboard]`, etc.). Como `LOGIN_REDIRECT_URL = "/"` (`config/settings/base.py:122`) y `/` resuelve a la vista `dashboard`, **el primer render tras login es un 500**.

Por qué no se detectó: `manage.py check` no compila plantillas, y las dos tareas abiertas de `openspec/changes/ui-modernization/tasks.md` — "revisión visual escritorio/móvil" y "abrir PR" — son precisamente las que lo habrían capturado. `docs/dev/impeccable-audit.md:19` presenta este mismo commit como mejora de rendimiento con 4/4.

**Archivos:** `templates/dashboard/index.html`.

**Impacto:** aplicación inutilizable tras login en esta rama. **`main` no está afectado** (el commit vive solo en `codex/impeccable-ui-audit`).

**Es la primera tarea recomendada.** Detalle completo en §23.

---

## 7. Hallazgos P1

### F-02 · Cierre de mantenimiento: callejón sin salida silencioso — **HECHO (verificado en runtime)**

`MaintenanceComplete.post` (`apps/maintenance/views.py:112-127`) exige un `MaintenanceCompletionForm` con `performed_by` y `cost` **obligatorios**. Pero el botón "Complete" en `templates/maintenance/record_detail.html:9` postea únicamente el `csrf_token`. Al fallar la validación, la vista re-renderiza `record_detail.html` pasando `completion_form=form` — pero **la plantilla nunca renderiza `completion_form`** (carga `crispy_forms_tags` pero no lo usa). Resultado: el usuario pulsa "Complete", la página vuelve idéntica sin error visible, y el registro queda en `in_progress` para siempre. El flujo de mantenimiento no se puede cerrar desde la UI.

**Archivos:** `apps/maintenance/views.py`, `templates/maintenance/record_detail.html`.

### F-03 · IDOR en workboard: checklist y StageCreate sin verificar acceso al tablero — **HECHO**

`ChecklistItemCreate` (`apps/workboard/views.py:268-280`) y `ChecklistItemToggle` (`:283-292`) exigen solo el permiso de modelo (`ModelPermissionRequiredMixin`), **sin llamar a `user_can_edit_board`** — a diferencia de `MoveTaskView`, `TaskEditView` y `QuickTaskCreate`, que sí lo hacen. Ambas respuestas renderizan `_task_detail.html` completo (título, descripción, checklist, registro operativo vinculado). Un usuario con `change_kanbanchecklistitem` puede leer y escribir en tareas de un tablero restringido por `KanbanBoardAccess`/tenant.

`StageCreate` (`:380-394`) es peor: el bucle de la línea 295 genera una versión con verificación de tablero, pero la definición explícita de la línea 380 la **sobrescribe** con una clase sin verificación de objeto → `POST /workboard/stages/new/` con `board=<uuid ajeno>` inserta una etapa en el tablero de otro tenant.

**Archivos:** `apps/workboard/views.py`.

### F-04 · `/workboard/tasks/` y `/workboard/boards/` evitan el scoping — **HECHO**

`WList` (`apps/workboard/views.py:35`) no define `get_queryset`, así que devuelve `KanbanTask.objects.all()` / `KanbanBoard.objects.all()`. Las clases `TaskList`/`BoardList` se generan a partir de `WList` en el bucle `:295-309`, sin scoping. La lógica de tenancy vive en `selectors.py` y aquí no se usa. Un usuario con `view_kanbantask` abre `GET /workboard/tasks/?export=csv` y descarga todas las tareas de todos los tableros y tenants — rompiendo la garantía que los tests solo protegen en la API.

**Archivos:** `apps/workboard/views.py`, `apps/workboard/urls.py`.

### F-05 · Descarga de documentos sin autorización a nivel de objeto — **HECHO**

`DocumentDownload` (`apps/compliance/views.py:130-143`), `DocumentDetail`, `DocumentList`, `DocumentReplace`, `DocumentDelete` exigen solo el permiso de modelo `compliance.view_document`. `get_object_or_404(Document, pk=pk)` no filtra por tenant, `content_object` ni membresía — a pesar de que `storage.py:4-6` documenta que "las vistas son responsables de la autorización". Un usuario con `view_document` enumera `/compliance/document/` y descarga el documento de cualquier organización. Agravante: el rol `Viewer` (`bootstrap_roles.py:46`) recibe **todos** los `view_*`, así que el rol nominalmente más bajo puede descargar todos los documentos y leer la pista de auditoría.

**Archivos:** `apps/compliance/views.py`, `apps/core/management/commands/bootstrap_roles.py`.

### F-06 · `/calendar/` y Kanban HTML no exigen permisos de dominio — **HECHO**

`CalendarView` (`apps/operations/views.py:193`) es `LoginRequiredMixin` sin ningún `view_*`, y expone el padrón completo: matrícula+modelo de todas las aeronaves, nombre de todos los operadores, códigos de centros de costo, permisos y mantenimientos del mes (`templates/core/calendar.html:41-56`). Un usuario sin ningún permiso `view_*` (que recibe 403 en `/registry/operator/`) obtiene el mismo padrón vía `/calendar/`. Igual el Kanban HTML (`apps/workboard/views.py:315`, `KanbanBoardView`) frente a su API, que sí exige permiso. `UnifiedCalendarEventsView` (`apps/core/views.py:200`) aísla bien por tenant pero tampoco comprueba `has_perm`.

**Archivos:** `apps/operations/views.py`, `apps/workboard/views.py`, `apps/core/views.py`.

### F-07 · `on_delete=CASCADE` destruye el expediente de cumplimiento — **HECHO · CAMBIAR AHORA**

`Document.content_type` y `Alert.content_type` (`apps/compliance/models.py:34,60`) usan CASCADE hacia `ContentType`. `django.contrib.contenttypes` borra filas de `ContentType` cuando un modelo desaparece (`remove_stale_contenttypes`, que corre tras `migrate`). Un renombrado de app/modelo **borra en cascada todos los `Document` y `Alert` de ese tipo de entidad**, sin rastro. Además `Alert.alert_rule` CASCADE (`:59`) destruye alertas resueltas al borrar una regla; `PermissionHistory.permission` y `MaintenanceHistory.record` CASCADE destruyen historial. En una app de cumplimiento aeronáutico, "resolví esta alerta / cambié este estado" es evidencia regulatoria. Corrección: `PROTECT` en los cuatro + desnormalizar `app_label`/`model` como texto de respaldo. Coste hoy: una `AlterField` trivial. Coste tras una pérdida: irrecuperable.

**Archivos:** `apps/compliance/models.py`, `apps/operations/models.py:55`, `apps/maintenance/models.py:38`.

### F-08 · Tenancy incompleta e irreversible con datos reales — **HECHO/INFERENCIA · CAMBIAR AHORA**

- Solo 4 modelos tienen `tenant` (`CostCenter`, `Aircraft`, `Operator`, `KanbanBoard`); **17 no lo tienen** (`Assignment`, `Qualification`, `FlightPermission`, `FlightRecord`, historias, `Document`, `Alert`, etc.).
- El campo es **nullable** en los 4 y se añadió **sin backfill** → toda fila preexistente tiene `tenant = NULL`.
- Ningún formulario de registry/compliance/operations expone `tenant`; solo se asigna en `KanbanBoardForm` y en el admin → **todos los registros operativos hoy son globales**.
- El scoping de lectura es un **OR sobre tres FKs** (`apps/core/views.py:259-263`, `apps/registry/views.py:132-136`): un registro con aeronave del tenant A y operador del tenant B se filtra a **ambos** tenants. Es fuga por diseño.
- Hay **tres implementaciones distintas** del scoping y ninguna validación que impida mezclar tenants en un `FlightPermission` (`apps/operations/models.py:16-18`, sin `clean()`).

Decidir la clave de tenancy y hacerla `NOT NULL` con backfill es un `AddField`+`AlterField` con 0 filas de producción; con datos reales es una migración de datos con criterio de negocio irrecuperable. **Este es el bloqueador arquitectónico #1 para el servidor centralizado y para DJI Cloud API.**

**Archivos:** todos los `models.py`; `apps/core/views.py`, `apps/registry/views.py`, `apps/workboard/selectors.py`.

### F-09 · El gate obligatorio no falla ante tests rojos — **HECHO (verificado)**

`scripts/verify.ps1:8-14` son 7 invocaciones de ejecutable nativo sin ninguna comprobación de `$LASTEXITCODE`. Verificado en este entorno (PowerShell 7.6.4): `$PSNativeCommandUseErrorActionPreference = False`, así que un código de salida ≠0 **no lanza excepción** pese a `$ErrorActionPreference="Stop"` (probado: la línea posterior a `exit 3` siguió ejecutándose). Consecuencia: un `pytest` en rojo (línea 10) no detiene el script, cuyo código de salida final es el de `pip-audit` (línea 14). El gate obligatorio de `AGENTS.md:10` puede reportar éxito con la suite rota — exactamente lo que ocurre hoy con el P0. Es la causa mecánica de que se pueda entregar una rama con la home caída.

**Archivos:** `scripts/verify.ps1`, `scripts/setup.ps1`.

### F-10 · Cero `CheckConstraint`; ~11 invariantes solo en forms — **HECHO · CAMBIAR AHORA**

`grep AddConstraint` en las 21 migraciones devuelve solo 3 `UniqueConstraint` y **ninguna `CheckConstraint`**. Reglas de negocio evadibles por admin/API/import/shell:

| Invariante | Dónde está hoy |
|---|---|
| `Assignment.end_date >= start_date` | `apps/registry/models.py:114` (`clean`) |
| No solapamiento de asignaciones confirmadas | `apps/registry/forms.py:107-123` (solo form, con race) |
| `FlightRecord.arrival_time > departure_time` | `apps/operations/forms.py:51` (solo form) |
| `MaintenanceRecord.cost >= 0` | **nada** |
| `MaintenanceRecord.completed_date >= scheduled_date` | **nada** |
| `status="completed" ⇒ completed_date NOT NULL` | **nada** |
| `Qualification.expiry_date >= issue_date` | **nada** |
| `Document.expiry_date >= issue_date` | **nada** |
| `Alert.is_resolved ⇔ resolved_at NOT NULL` | `apps/compliance/views.py:228-230` (vista) |

Faltan también `UniqueConstraint(tenant, code/employee_id/permission_number)` (hoy unicidad global bloquea multi-tenant) y `UniqueConstraint` de "un documento vigente por tipo+objeto" (`apps/compliance/models.py:33-45` no tiene ninguna constraint). Añadir constraints a tablas con datos que ya las violan requiere limpieza manual → **AHORA**.

---

## 8. Hallazgos P2

- **F-11 · CI mide cobertura y la descarta.** `.github/workflows/ci.yml:30` no tiene `--cov-fail-under`; no hay `[tool.coverage]`. Es la causa mecánica de que `maintenance` y `dashboard` estén a 0% sin queja. Cobertura global medida hoy: **82%** (`generate_alerts` 0%, `bootstrap_roles` 0%, `compliance/security.py` 35%, `chapter1_import` 21%).
- **F-12 · Deriva documental severa.** `openspec/config.yaml:8,38` afirma "No test runner configured / discovered" (hay 87 tests); `:28` `test_command: "python -m pytest"` (el real es `uv run pytest`); `:41-49` declara linter/formatter/coverage no disponibles (todos existen). `docs/dev/03-Roadmap.md` tiene 13 casillas sin marcar de trabajo ya hecho. Un agente que lea estos artefactos como verdad concluirá que no debe escribir tests.
- **F-13 · Paginación HTMX muerta.** `generic/_pagination.html` apunta a `hx-target="#table-body"`, pero `permission_list.html:47`, `record_list.html:16` y `alert_list.html:4` tienen `<tbody>` sin `id` → los botones de página no hacen nada. El spec `phase3-htmx` pedía `#table-wrapper`.
- **F-14 · Funcionalidad inalcanzable desde la UI.** Búsqueda global (`GlobalSearchView`), importadores CSV (`costcenter-import`, `aircraft-import`, `operator-import`) y habilitaciones DGAC (`qualification-list`) **existen en el backend pero no tienen ningún enlace** en las 43 plantillas ni en el centro de administración (`templates/base.html:53-80`). Además los resultados de búsqueda apuntan al **listado**, no al detalle (`apps/core/views.py:500`).
- **F-15 · `app.css` son dos sistemas de diseño apilados.** 973 líneas con dos generaciones de tokens (`:root` en `:2-7` con `--navy` vs `:653-669` con `--ac-*`) y selectores duplicados (`.sidebar`, `.btn-primary`, bloque dark). Además hay clases usadas en plantillas sin definición CSS (`.status-*`, `.kanban-label` color, `.is-overdue`, `.form-shell`).
- **F-16 · 62.661 líneas de tooling vendorizado.** `.agents/skills/impeccable/` (127 archivos, commit `980b763`) no está referenciado por ningún código de la app, no tiene pin de versión ni entra en `pip-audit`/Dependabot. Contamina cada `git log --stat` y cada auditoría.
- **F-17 · CSP y SRI.** `apps/core/middleware.py:36-43`: no hay `django-csp` instalado; poner `CSP_REPORT_ONLY=False` **elimina** la cabecera en vez de hacerla enforcing, y la política no coincide con los CDN reales (unpkg, cdnjs). HTMX se carga con rango flotante `htmx.org@2.x` sin SRI (`base.html:11`); 3 de 4 dependencias externas sin `integrity`, contradiciendo `docs/SECURITY.md:28`.
- **F-18 · Sin protección brute-force** en login ni `/api-token/` (sin `django-axes` ni throttling DRF); tokens DRF sin caducidad en claro.
- **N+1 confirmados:** render del tablero Kanban (`selectors.py:111-115` reconsulta por stage; `_card.html:16` hace un COUNT por tarjeta), `generate_alerts` (2N+1), export CSV genérico (FK sin `select_related`), dashboard (agregaciones que además ignoran `is_active`).

---

## 9. Hallazgos P3

- Parámetro GET interpolado en literal JS en `templates/core/calendar.html:80` (no explotable hoy por autoescape, pero viola la regla propia `AGENTS.md:20`; el dashboard sí usa `json_script` correctamente).
- Inyección CSS vía `KanbanLabel.color`/`KanbanStage.color` sin validador (`workboard/models.py:34,41`) — a lo sumo defacement.
- `HealthCheckView` y `api_openapi_schema` públicos (intencional, sin datos de negocio).
- Badge de alertas siempre rojo aun con 0 alertas (`base.html:65`).
- Fugas de i18n: `_quick_form.html` completo en inglés sin `{% load i18n %}`; español hardcodeado en `aircraft_list.html:18`; mensajes de vista sin `_()` (`compliance/views.py:194`, `core/views.py:573`); antipatrón `_(variable)` no extraíble.
- `<main>` anidado en `search.html:5` y `costcenter_import.html:5`.
- Artefactos temporales en la raíz (`.tmp-integration-check.sqlite3`, `.tmp-check-logs/`), `.env` local con SECRET_KEY débil (**verificado: NO está en git**), `.atl/skill-registry.md` con rutas absolutas y nombre de usuario versionados.

---

## 10. Deuda técnica

1. **`core` como god-module** con ciclo de dependencias e imports diferidos (5 puntos).
2. **`UnifiedCalendarEventsView.get`**: 231 líneas, 7 bloques casi idénticos, importa 5 apps (`apps/core/views.py:225-455`).
3. **Duplicación estructural:** 5 pares List/Create casi idénticos; 3 representaciones de `KanbanTask` (`api.py` serializer, `_legacy_item`, `selectors.task_row`); 2 implementaciones del mismo filtro de tareas; 4 implementaciones de "vencimiento".
4. **Tres estilos de declaración de vistas** (clase explícita, `type()`, `globals()[...]=type()` en un `for`), el último rompe navegación de IDE y ocultó que `MaintenanceHistoryCreate` está roto.
5. **Señales `pre_save` innecesarias** con dependencia invertida (`core` importa `maintenance`/`operations`) y contrato por atributos mágicos (`_changed_by`), con una rama muerta (`signals.py:30` siempre verdadera).
6. **`AuditEvent` no atómico** con la mutación que audita (se crea en el middleware, tras cerrar la transacción de la vista, y se traga los fallos — `middleware.py:44-76`).
7. **Escritura a storage dentro de `transaction.atomic`** → ficheros huérfanos si algo posterior falla (`compliance/views.py:90-94`).
8. **Código muerto:** `MaintenanceHistoryCreate`/`MaintenanceHistoryForm`, ruta duplicada `ops-calendar`, `alerts_by_severity: []`, `StageList`/`BoardFilterPartial` no enrutados, `prompts/` obsoleto.

---

## 11. Problemas de arquitectura

Ver §3 y §10. Puntos clave para el roadmap:

- **INFERENCIA/RECOMENDACIÓN:** partir `apps/core` en (a) infra pura sin imports de dominio, (b) `apps/tenancy` con `OperationalTenant`/`TenantMembership` + el scoping canónico único, y mover calendario/búsqueda a `dashboard` (que ya importa las 5 apps legítimamente). Esto rompe el ciclo y elimina los 5 imports diferidos.
- **`dashboard` debería absorberse en `core`** (no tiene modelos, migraciones vacías; es un módulo, no una app).
- **`workboard` está bien aislada**; la única dependencia dura es `KanbanTask.assigned_to → registry.Operator` (`workboard/models.py:76-78`). Reemplazarla por `→ User` o GFK cerraría el acoplamiento.
- **Mantener el monolito modular.** No hay ninguna razón para microservicios (el usuario ya lo pidió explícitamente y coincido).

---

## 12. Problemas de modelo de datos

Ver §7 (F-07, F-08, F-10). Adicionales clasificados:

**CAMBIAR AHORA:** `on_delete` (F-07), tenancy (F-08), `CheckConstraint`/`UniqueConstraint` (F-10), migrar a `TextChoices` (hoy cero; estados son strings crudos comparados en ~20 sitios — no cambia el esquema, barato ahora), índices `is_active`+fecha/estado compuestos.

**PUEDE ESPERAR:** duplicación de timestamps de auditoría (`MaintenanceHistory.changed_at` vs `created_at`), cobertura asimétrica de historial (Aircraft/Document/Assignment sin historia dedicada), normalización de `authorized_services`/`authorizations` (blobs de texto → tablas), `Operator.rut` sin validador chileno, `db_index` no compuestos, limpieza de `CharField` `changed_by` que coexiste con el FK `changed_by_user`.

---

## 13. Problemas de seguridad

Ver §7 (F-03–F-06) y §8 (F-17, F-18). **No hay P0.** Encuadre correcto: hoy nada es alcanzable sin autenticación y el multi-tenant es aspiracional (`tenant=NULL` universal), así que los IDOR son gaps de código cuyo impacto real llega con el servidor centralizado. **Cerrarlos es prerequisito de la centralización**, no una emergencia de hoy.

**Hardening recomendado (no vulnerabilidades):** `TenantScopedQuerysetMixin` obligatorio; `tenant` en los formularios; `django-csp` enforcing por entorno; SRI en las 4 dependencias externas; `django-axes` + throttling DRF; revisar el rol `Viewer` (hoy `codename__startswith="view_"` es demasiado amplio); mover `/admin/` a ruta no adivinable antes de centralizar; cifrar backups + `icacls`.

---

## 14. Problemas de testing

Ver §8 (F-11). Detalle:

- **Reglas críticas sin cobertura:** `generate_alerts` (0%, núcleo de cumplimiento), todo `maintenance`, todo `dashboard`, aislamiento de tenant (no existe ni un test cross-tenant fuera de workboard, y `apps/workboard/tests.py:511-525` **codifica el modo permisivo como esperado**), rol `Viewer`, neutralización de fórmulas CSV (obligatoria por `AGENTS.md:21` pero sin test; además los reportes XLSX/DOCX de workboard **no la aplican**), versionado de documentos.
- **~14 tests de bajo valor:** aserciones `in (200, 302)` (una vista rota que redirige pasa), tests de markup (`"htmx.org" in content`), tests de Django (staticfiles finders, widget input_type).
- **Sin infraestructura compartida:** no hay `conftest.py` ni factories; ~60 líneas de setup idéntico repetidas 3 veces en `operations/tests.py`. Una fixture `two_tenant_world` es el desbloqueante técnico de los tests de aislamiento P0.

---

## 15. Problemas de rendimiento

N+1 confirmados (ver §8): render Kanban, `generate_alerts`, export CSV genérico, dashboard. Reordenamiento kanban con O(n) UPDATEs por drag (`workboard/views.py:468-492`). `AssignmentList` ejecuta su queryset 4-5 veces (`registry/views.py:139-147`). Agregación cuadrática en `templates/core/calendar.html:56`. **Ninguno es urgente en alpha con pocos datos**, pero conviene añadir `assertNumQueries` a los tests de las listas antes de que crezcan.

---

## 16. Problemas de mantenibilidad

Ver §10. Además: `main` está **25 commits por detrás** de la rama activa y hay 5 ramas locales sin mergear + 16 remotas vivas (incluidos pares `-clean` que evidencian reescritura de historia) + 5 PRs de Dependabot sin atender. No existe `CODEOWNERS`, `PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md` ni `.pre-commit-config.yaml`. El estilo de mensajes de commit cambió tres veces (hoy Conventional Commits, el bueno, pero no está codificado).

---

## 17. Recomendaciones que NO deberíamos implementar todavía (YAGNI)

- **DJI Cloud API, telemetría, sincronización con terreno.** Depende de que el modelo de tenancy y las constraints estén fijos. Diseñar la capa de integración **después** de la estabilización.
- **Migración a PostgreSQL en producción.** El switch ya está en el código (`DB_ENGINE`); hacerla efectiva puede esperar a tener aislamiento de tenant y `ExclusionConstraint` (que Postgres habilita para el no-solapamiento de asignaciones). No migrar todavía.
- **Servidor centralizado / API interna pública.** Prerequisito: F-03–F-08 cerrados.
- **PWA/offline para captura en terreno.** Valioso pero prematuro; primero cerrar los flujos rotos (F-01, F-02) y reducir la fricción del formulario de vuelo.
- **Microservicios, cambio de framework CSS, SPA.** Descartados: el monolito modular server-side es la elección correcta para este equipo y dominio.
- **Gestión de baterías, mantenimiento por horas/ciclos.** Requieren modelos nuevos; entran en FASE 6, no antes.

---

## 18. Arquitectura objetivo recomendada

**Monolito Django modular, server-side, evolutivo.** Cambios de límites, no de tecnología:

```
core        SOLO infra: BaseModel, mixins de vista, middleware, audit, imports.
            Cero imports de apps de dominio. Rompe el ciclo.
tenancy     OperationalTenant, TenantMembership + un ÚNICO TenantScopedQuerySet/Manager
            canónico, reutilizado por todas las apps.
registry / compliance / operations / maintenance   sin cambios de límite.
workboard   se mantiene aislada; assigned_to → User (rompe la última dependencia dura).
dashboard   absorbe calendario unificado + búsqueda global (ya importa las 5 apps).
```

Principios: business rules en modelos (`clean()` + `CheckConstraint`), un `selectors.py` por app para lecturas/scoping/agregaciones, transiciones de estado como método de modelo `transition_to(status, actor, notes)` llamado explícitamente (elimina las señales `pre_save`), auditoría en el mismo `atomic` que la mutación.

---

## 19. Roadmap priorizado

Etapas dependientes. Esfuerzo relativo XS/S/M/L/XL.

### FASE 0 — Estabilización inmediata (desbloquea todo)

| ID | Prio | Problema | Evidencia | Archivos | Solución | Dep. | Riesgo | Esf. | Criterio de aceptación |
|---|:--:|---|---|---|---|:--:|:--:|:--:|---|
| T0.1 | P0 | Dashboard 500 tras login | `dashboard/index.html:4,128` | ídem | Fusionar el `<script>` de la línea 4 dentro del bloque de la 128 | — | Bajo | XS | Login → dashboard 200; los 7 tests en verde |
| T0.2 | P1 | Cierre de mantenimiento imposible | `maintenance/views.py:112`, `record_detail.html` | ídem | Renderizar `completion_form` en la plantilla | — | Bajo | S | Completar mantención funciona; test de la transición |
| T0.3 | P1 | Gate no falla | `scripts/verify.ps1:8-14` | ídem | `if ($LASTEXITCODE -ne 0){throw}` tras cada paso; alinear con CI | — | Bajo | XS | Un pytest rojo hace fallar `verify.ps1` |
| T0.4 | P1 | CI descarta cobertura | `ci.yml:30` | ídem + `pyproject.toml` | `--cov-fail-under` con línea base + ratchet | T0.3 | Bajo | S | CI falla si baja la cobertura |
| T0.5 | P2 | Añadir compilación de plantillas al CI/gate | causa de T0.1 | test o comando | Test que haga `get_template` de las 43 plantillas | T0.3 | Bajo | S | Un bloque duplicado hace fallar CI |
| T0.6 | P2 | `openspec/config.yaml` falso | `config.yaml:8,28,41` | ídem | Corregir 9 campos; validar contra realidad en CI | — | Bajo | XS | `config.yaml` refleja el runner real |

### FASE 1 — Arquitectura y deuda crítica

| ID | Prio | Problema | Archivos | Solución | Dep. | Esf. |
|---|:--:|---|---|---|:--:|:--:|
| T1.1 | P1 | `core` god-module + ciclo | `apps/core/*` | Extraer `apps/tenancy`; mover calendario/búsqueda a `dashboard`; core = infra pura | FASE 0 | XL |
| T1.2 | P1 | Vista de calendario de 231 líneas | `core/views.py:225-455` | Proveedores de eventos por app | T1.1 | L |
| T1.3 | P2 | Señales `pre_save` + dependencia invertida | `core/signals.py` | `transition_to()` en el modelo | T1.1 | M |
| T1.4 | P2 | Auditoría no atómica | `middleware.py:44-76` | Mover al `atomic` de la mutación; no tragar fallos | T1.3 | M |
| T1.5 | P3 | `selectors.py` por app | todas | Centralizar lecturas/scoping/agregaciones | T1.1 | L |

### FASE 2 — Seguridad y permisos

| ID | Prio | Problema | Archivos | Solución | Dep. | Esf. |
|---|:--:|---|---|---|:--:|:--:|
| T2.1 | P1 | IDOR workboard (F-03, F-04) | `workboard/views.py` | `user_can_edit_board`/`visible_tasks` en checklist/stage; `get_queryset` scoped en List | T1.1 | M |
| T2.2 | P1 | Doc sin authz de objeto (F-05) | `compliance/views.py` | `TenantScopedQuerysetMixin` + filtro por entidad | T1.1 | M |
| T2.3 | P1 | Calendar/Kanban HTML sin perms (F-06) | `operations/views.py`, `workboard/views.py`, `core/views.py` | Añadir `has_perm` | T1.1 | S |
| T2.4 | P2 | Rol `Viewer` demasiado amplio | `bootstrap_roles.py` | Enumerar `view_*` explícitos | — | S |
| T2.5 | P2 | CSP/SRI/brute-force (F-17, F-18) | settings, templates | `django-csp` enforcing, SRI, `django-axes` | — | M |

### FASE 3 — Integridad de datos

| ID | Prio | Problema | Archivos | Solución | Dep. | Esf. |
|---|:--:|---|---|---|:--:|:--:|
| T3.1 | P1 | `on_delete=CASCADE` (F-07) | `compliance/`, `operations/`, `maintenance/` models | `PROTECT` + desnormalizar respaldo | — | S |
| T3.2 | P1 | Tenancy irreversible (F-08) | todos los models + scoping | `tenant` en 17 modelos, `NOT NULL` con backfill, scoping único, `clean()` anti-mezcla | T1.1 | XL |
| T3.3 | P1 | Cero constraints (F-10) | todos los models | `CheckConstraint` + `UniqueConstraint` compuestos con tenant | T3.2 | L |
| T3.4 | P2 | Estados como strings | todos los models | Migrar a `TextChoices` | — | M |
| T3.5 | P3 | Índices | migraciones | `db_index` compuestos `is_active`+fecha/estado | — | S |

### FASE 4 — Testing

| ID | Prio | Problema | Solución | Dep. | Esf. |
|---|:--:|---|---|:--:|:--:|
| T4.1 | P1 | Sin fixtures compartidas | `conftest.py` con `two_tenant_world`, `role_user()` | FASE 0 | M |
| T4.2 | P1 | Aislamiento de tenant sin test | Matriz cross-tenant por vista | T4.1, T3.2 | L |
| T4.3 | P1 | `generate_alerts`, maintenance, dashboard a 0% | Tests de reglas de negocio | T4.1 | L |
| T4.4 | P2 | Fórmulas CSV/XLSX/DOCX sin test ni impl. en workboard | Test + neutralización en `task_row` | — | M |
| T4.5 | P3 | ~14 tests de bajo valor | Sustituir por los P0 de arriba | T4.1 | S |

### FASE 5 — UX y flujos operacionales

(Ver §24-25 para el detalle de producto.) T5.1 sistema de diseño unificado; T5.2 paginación HTMX + búsqueda en vivo; T5.3 enlaces faltantes (habilitaciones, búsqueda, importadores); T5.4 dashboard accionable; T5.5 formulario de vuelo reducido + prellenado; T5.6 i18n (limpiar fugas); T5.7 accesibilidad (`scope`, labels).

### FASE 6 — Nuevas funcionalidades

Solo después de FASE 0-3: alertas programadas + notificaciones email, checklists pre-vuelo (cablear `KanbanTask.source_object → FlightPermission`), mantenimiento por horas/ciclos (campos nuevos), gestión de baterías (modelo nuevo), vista previa de adjuntos, panel de auditoría en la UI. Y **entonces** DJI Cloud API / telemetría.

---

## 20. Backlog técnico propuesto

Se recomienda materializar FASE 0-6 como changes de `openspec/` (un change por tarea, con `tasks.md` verificable), cerrar el ciclo con `openspec/specs/` consolidado, y limpiar la deuda de proceso: eliminar `.agents/skills/impeccable/` del repo (submódulo/paquete externo), borrar `.atl/skill-registry.md` y `prompts/`, limpiar código muerto (§10.8), poner al día `main`, y podar ramas remotas obsoletas.

---

## 21. Estrategia de desarrollo con Codex + Claude Code

**Diagnóstico:** el repo tiene un problema de *verificación*, no de *implementación*. El código es de calidad razonable, pero el gate no falla, CI descarta cobertura, los metadatos que el agente lee son falsos y los docs de estado no se actualizan. **Reparar las señales (FASE 0) antes de formalizar el split.**

**Reparto de roles:**
- **Claude Code → arquitectura, auditoría, revisión crítica, segunda opinión.** Diseña specs (openspec), define contratos de aceptación, revisa diffs contra el contrato, produce auditorías como esta. Fuerte en FASE 1 (límites de apps), FASE 3 (modelo de datos) y en la revisión de cada PR.
- **Codex → implementación, debugging, refactoring, ejecución tarea-a-tarea.** Toma un `tasks.md` cerrado y lo implementa en una rama pequeña con su gate verde.

**Flujo:** `AUDITORÍA → MASTER_PLAN → ISSUE → SPEC (openspec) → PLAN → IMPLEMENTACIÓN → TEST → REVIEW → COMMIT`. Nunca `PROMPT GRANDE → CAMBIA TODO`.

**Artefactos que hacen la revisión mecánica (a crear en FASE 0):**
- `AGENTS.md` ampliado: ciclo rápido (`uv run pytest apps/<app>/tests.py`) vs gate completo; Definition of Done por tipo de cambio (vista → test de 403 + test de scope de tenant; modelo → migración + test de constraint); reglas de commit (una intención, Conventional Commits, sin mezclar tooling con producto); **contrato de lectura** (toda vista que expone datos de dominio exige `view_*` y acota por tenant — hoy ausente y causa de F-05/F-06); precedencia documental explícita.
- `.github/pull_request_template.md` con casillas verificables contra el diff.
- `conftest.py` con fixtures de tenant/rol (desbloquea los tests P0).
- Gate `verify.ps1` que realmente falla y es superconjunto de CI.

**Tercera pasada (la que pidió el usuario):** con `AUDIT_CLAUDE.md` y `AUDIT_CODEX.md`, verificar cada hallazgo contra el código, descartar falsos positivos (como el de `NullBooleanField` que ya descarté aquí), consolidar duplicados y generar `MASTER_PLAN.md` sin implementar.

---

## 22. Las siguientes 10 tareas concretas

1. **T0.1** — Corregir el bloque `extrahead` duplicado (P0, restaura la app). *(primera tarea, §23)*
2. **T0.3** — Hacer que `scripts/verify.ps1` falle ante error (P1, restaura la confianza en el gate).
3. **T0.2** — Renderizar `completion_form` para poder cerrar mantenimientos (P1).
4. **T0.4 + T0.5** — Umbral de cobertura y compilación de plantillas en CI (P1/P2).
5. **T0.6** — Corregir `openspec/config.yaml` y sincronizar `docs/dev/03-Roadmap.md` (P2).
6. **T4.1** — `conftest.py` con `two_tenant_world` y `role_user()` (desbloquea tests de aislamiento).
7. **T3.1** — `on_delete=CASCADE → PROTECT` en Document/Alert/historias (P1, barato ahora).
8. **T2.1 + T2.2 + T2.3** — Cerrar los IDOR y las vistas de lectura sin permiso (P1).
9. **T3.2 (diseño)** — Decidir la clave de tenancy y escribir el ADR + migración de backfill (bloqueador de centralización).
10. **Limpieza de repo** — Sacar `.agents/skills/impeccable/`, borrar `.atl/` y `prompts/`, poner al día `main`.

---

## 23. PRIMERA tarea recomendada (no implementada)

### T0.1 — Restaurar el dashboard eliminando el bloque `extrahead` duplicado

**Objetivo.** Devolver la aplicación a un estado funcional: que un usuario que inicie sesión llegue al dashboard (HTTP 200) en lugar de un 500, y que los 7 tests hoy en rojo pasen. Es un cambio de una plantilla, sin tocar lógica.

**Archivos afectados.**
- `templates/dashboard/index.html` (único cambio de código).

**Cambios esperados.**
- Django solo admite un `{% block extrahead %}` por plantilla. Hoy hay dos: la línea 4 (`<script defer chart.js>`) y las líneas 128-131 (`json_script` + parseo). Fusionar el `<script>` de la línea 4 dentro del bloque de las líneas 128-131 y **eliminar el bloque de la línea 4**, conservando la carga condicional de Chart.js que introdujo el commit `c6025d5` (el objetivo de ese commit — cargar Chart.js solo en el dashboard — sigue siendo válido; solo hay que ubicarlo en un único bloque).
- No cambiar `base.html` ni la vista `dashboard`.

**Tests requeridos.**
- Los 7 tests existentes deben pasar sin modificarlos: `apps/core/tests.py::TestChapter1DocxImport::{test_dashboard, test_base_template_has_htmx, test_base_template_has_dark_mode_toggle, test_base_template_has_accessible_navigation_and_modal_hooks, test_dashboard_serializes_chart_data_without_marking_it_safe, test_language_switches_navigation_and_status_labels_to_spanish}` y `TestAuthRequiredURLs::test_returns_success_when_authenticated[dashboard]`.
- (Recomendado, parte de T0.5, no obligatorio para esta tarea) un test nuevo que compile las 43 plantillas con `get_template` para que un bloque duplicado vuelva a fallar en CI, ya que `manage.py check` no lo detecta.

**Criterio de aceptación.**
- `uv run pytest` en verde (0 fallos).
- `uv run python manage.py check` limpio.
- Manualmente: login → dashboard renderiza 200 con los gráficos; el `json_script#chart-data` sigue presente y Chart.js se carga solo en esa página.
- Sin cambios en ningún archivo fuera de `templates/dashboard/index.html`.

**Riesgos.**
- Bajo. El único riesgo es romper el orden de carga de scripts (Chart.js debe cargar antes del `<script>` de `extrascripts` que lo usa). Se mitiga manteniendo el `defer` de Chart.js y verificando en el navegador que los 5 gráficos renderizan.

**Prompt exacto para el agente implementador (Codex):**

> En el repositorio AeroControl, la plantilla `templates/dashboard/index.html` declara `{% block extrahead %}` dos veces (líneas 4 y 128), lo que provoca `TemplateSyntaxError: 'block' tag with name 'extrahead' appears more than once`. Como `LOGIN_REDIRECT_URL = "/"` resuelve al dashboard, todo login termina en 500.
>
> Corrige **solo** `templates/dashboard/index.html`: elimina el bloque `{% block extrahead %}...{% endblock %}` de la línea 4 y mueve su `<script defer src=".../chart.js...">` al inicio del bloque `extrahead` que ya existe en las líneas 128-131 (junto al `json_script` y el parseo de `chartData`), de modo que quede **un único** bloque `extrahead`. Conserva el `defer` y no toques `base.html`, la vista `dashboard`, ni ningún otro archivo.
>
> Verifica con `uv run pytest` (los 7 tests en rojo deben pasar) y `uv run python manage.py check`. No modifiques los tests. No hagas commit; deja el cambio listo para revisión.

**No implementes esta tarea todavía.** Primero revisemos juntos esta auditoría y el roadmap.

---

## 24. Workflow de diseño UX/UI recomendado

**Diagnóstico (HECHO).** La rama tiene mucha ingeniería sólida y poco recorrido de usuario: la home no compila, el cierre de mantenimiento es un callejón sin salida, y la búsqueda global, los importadores y las habilitaciones DGAC no tienen enlace en la UI. La causa es que las dos últimas tareas de `ui-modernization` — "revisión visual" y "abrir PR" — nunca se hicieron. **El problema no es de diseño visual, es de cierre de flujo.**

**Workflow propuesto (repetible, por pantalla):**

1. **Fundación una sola vez (FASE 5, T5.1).** Consolidar `app.css` en **un** sistema de design tokens (`--ac-*`), eliminando la generación 1 (`--navy`) y las clases usadas-sin-definir (`.status-*`, `.kanban-label`, `.is-overdue`, `.form-shell`). Un solo bloque dark. Documentar los tokens en un `docs/ui-tokens.md` corto. Esto es prerequisito: sin fundación, cada pantalla reinventa CSS ad-hoc (ya hay 12 estilos inline y 3 dialectos de cabecera).

2. **Por cada pantalla, un mini-ciclo:**
   - **Spec UX en openspec** (`openspec/changes/<pantalla>/`): usuario, tarea, flujo, y los **estados vacío/error/carga** explícitos (hoy varios flujos no muestran error — F-02).
   - **Referencia visual** (mockup o captura anotada) antes de codificar.
   - **Implementación en rama pequeña** (un flujo por rama, Conventional Commits).
   - **Revisión con checklist**: consistencia de tokens, `scope`/labels/foco (accesibilidad), i18n (`{% trans %}` + entrada en el `.po`), estados vacío/error, y **una acción primaria visible por pantalla** (el spec ya lo pide y las páginas de detalle no lo cumplen).
   - **Verificación visual real** en 320/768/1440 px — la tarea que faltó y dejó pasar el P0.

3. **Reparto de roles:**
   - **Claude Code:** crítica de diseño, spec UX, checklist de accesibilidad/consistencia, segunda opinión sobre jerarquía y flujos.
   - **Codex:** implementación de templates/CSS, extracción del JS inline a archivos estáticos, cableado HTMX.
   - La skill `impeccable` ya vendorizada puede servir como detector de anti-patrones de UI en la revisión (hoy no está integrada en CI; si se conserva, integrarla; si no, sacarla del repo — F-16).

---

## 25. Mejoras de utilidades para lo que la app necesita hoy

Priorizadas. Todas tienen **base ya existente en el código** (no requieren rearquitectura), salvo donde se indica. La comparación con herramientas modernas de operación de flota es ANÁLISIS; el estado del código es HECHO.

| ID | Prio | Mejora | Valor para el operador | Base existente | Esf. |
|---|:--:|---|---|---|:--:|
| U1 | P1 | **Enlazar habilitaciones DGAC, búsqueda e importadores** en el sidebar/centro de administración | El seguimiento de vigencias de tripulación es el núcleo regulatorio y hoy solo se llega por `/admin/` | Modelos, forms, vistas y URLs ya existen (`registry/urls.py:11`) | S |
| U2 | P1 | **Búsqueda global que lleve al detalle** y esté enlazada en la navbar | Encontrar una aeronave/operador/documento en 1 paso | `GlobalSearchView` ya recoge `obj.pk`; falta `reverse(f"{model}-detail")` | S |
| U3 | P1 | **Dashboard accionable**: KPIs y gráficos clicables → listas filtradas | Un jefe de operaciones ve "3 alertas" y va directo a ellas | Datos ya calculados en `dashboard/views.py` | M |
| U4 | P1 | **Dashboard: disponibilidad de flota + mantenimientos vencidos + documentos por vencer** | Panorama operativo real (hoy el KPI "por vencer" ignora `Document.expiry_date`) | `Aircraft.status`, `MaintenanceRecord.scheduled_date`, feed de calendario ya los tienen | M |
| U5 | P1 | **Formulario de registro de vuelo reducido + prellenado desde el permiso** | De ~10-12 clics a 2-3; menos errores en terreno | `FlightRecordCreate.get_initial` ya soporta `?permission=`; falta el link y ocultar campos derivados | M |
| U6 | P2 | **Exportación visible donde ya funciona** (documentos, alertas, permisos, vuelos, mantención) | El backend ya exporta CSV; solo falta el botón | `CsvExportMixin` heredado por todas las listas | S |
| U7 | P2 | **Alertas de vencimiento programadas + notificación por email** | Hoy `generate_alerts` es manual y no hay ningún canal de notificación | `Operator.email` existe; `BackupConfig` muestra el patrón de scheduling; **falta backend de email** (nuevo) | M |
| U8 | P2 | **Cerrar el lazo de alertas**: resolver desde la lista sin perder filtros, enlace a la entidad, y snooze | Gestión real de alertas | `AlertResolve` existe; falta snooze (campo nuevo) y mostrar `content_object` en vez del UUID | M |
| U9 | P2 | **Checklists pre-vuelo** cableando `KanbanTask.source_object → FlightPermission` | Trazabilidad operacional sin modelo nuevo | `KanbanChecklistItem` + toggle HTMX ya funcionan; `source_object` está migrado pero **nunca se escribe** | M |
| U10 | P3 | **Vista previa de adjuntos** (PDF/imagen inline) | Evita descargar para revisar | `DocumentDownload` usa `FileResponse`; cambiar a `as_attachment=False` selectivo | S |
| U11 | P3 | **Panel "historial de este registro"** en las páginas de detalle | Auditoría visible sin entrar a `/admin/` | `AuditEvent` con índices por actor/modelo/fecha ya hechos para esa consulta | M |

**Sin base en el código (FASE 6, requieren modelos nuevos):** mantenimiento por horas/ciclos (ni `Aircraft` ni `FlightRecord` acumulan horas), gestión de baterías (no existe), PWA/offline.

---

## 26. Complementos necesarios

Evaluación explícita de qué agregar y qué **no**, bajo YAGNI. Solo se justifican los complementos que desbloquean §25.

| Complemento | ¿Agregar? | Justificación | Momento |
|---|:--:|---|:--:|
| **HTMX** | Ya está, mantener | Bien usado (8 patrones); no migrar a SPA | — |
| **Design tokens propios (CSS)** | Sí, consolidar | No agregar librería nueva: unificar el `app.css` existente en un solo set de tokens. Mantener Bootstrap + crispy | FASE 5 |
| **Vendorizar assets locales (Bootstrap/HTMX/Chart.js/FullCalendar)** | Sí | La app se declara "local-first" pero sin red queda sin CSS/JS. Auto-hospedar + SRI resuelve F-17 y la contradicción | FASE 5 |
| **`django-csp`** | Sí | Única forma de tener CSP enforcing (hoy imposible, F-17) | FASE 2 |
| **`django-axes` + throttling DRF** | Sí | Brute-force en login/`api-token` (F-18); bajo costo | FASE 2 |
| **Backend de email (SMTP/console)** | Sí | Desbloquea U7 (notificaciones); Django lo trae de fábrica, solo configurar | FASE 6 |
| **Scheduler (cron / django management + tarea programada)** | Sí | `generate_alerts` y backups deben correr solos; empezar con tarea programada del SO (ya hay `register-backup-task.ps1`), no meter Celery todavía | FASE 6 |
| **`--cov-fail-under` + `[tool.coverage]`** | Sí | Sin umbral, la cobertura se descarta (F-11) | FASE 0 |
| **`pytest` factories (`conftest.py`)** | Sí | Desbloquea tests de aislamiento; no requiere `factory_boy`, basta fixtures | FASE 0 |
| **Type checker (mypy/pyright)** | Opcional, más tarde | Beneficio real pero no urgente; introducir en modo gradual | FASE 4+ |
| **`django-filter` / export a PDF** | Diferir | Los filtros manuales actuales bastan; PDF solo si un requisito lo pide | FASE 5/6 |
| **Celery / Redis** | **No** | Sobredimensionado para local-first alpha; la tarea programada del SO cubre el caso | — |
| **`factory_boy`, Playwright/Selenium** | Diferir | Útiles pero no ahora; Playwright entra cuando exista presupuesto para tests visuales | FASE 4+ |
| **DJI Cloud SDK / MQTT / telemetría** | **No todavía** | Prerequisito: tenancy y constraints fijas (F-08, F-10). Diseñar después de estabilizar | FASE 6 |

---

*Fin de AUDIT_CLAUDE.md. Ninguna de estas recomendaciones fue implementada; el único archivo creado por esta auditoría es este documento.*
