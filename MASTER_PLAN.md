# MASTER_PLAN — AeroControl

> **Fuente única de verdad del trabajo pendiente.** Consolida la auditoría técnica ([AUDIT_CLAUDE.md](AUDIT_CLAUDE.md)) en bloques ejecutables con seguimiento de estado.
> **Creado:** 2026-07-24 · **Rama base de referencia:** `main` (25 commits por detrás de `codex/impeccable-ui-audit`).
> **Regla de oro:** este proyecto está en **pausa de estabilización**. No se incorpora DJI Cloud API ni funcionalidad nueva hasta cerrar FASE 0-3. Un bloque no empieza hasta que sus dependencias estén ✅.

---

## Cómo usar este documento

Es el **tablero de bloques**. `BACKLOG.md` queda como registro histórico de lo entregado; este archivo manda para lo que viene.

**Leyenda de estado:**
`⬜ Pendiente` · `🔄 En progreso` · `✅ Hecho` · `⛔ Bloqueado` (esperando una dependencia) · `⏸ Diferido` (YAGNI, no ahora)

**Ciclo por tarea (disciplina anti «prompt gigante»):**

1. Tomar la **siguiente tarea no bloqueada** de mayor prioridad del tablero.
2. Rama pequeña `codex/<area>-<id>` (una intención por rama).
3. (Opcional para cambios grandes) crear un change en `openspec/changes/<id>/` con `proposal.md` + `tasks.md`.
4. Implementar. Ejecutar el gate: `pwsh scripts/verify.ps1` **debe** pasar (ver T0.3 — hoy no falla; arréglese primero).
5. Revisión (Claude Code) contra el criterio de aceptación de la tarea.
6. Marcar la casilla aquí (`⬜`→`✅`), actualizar `BACKLOG.md` si corresponde, commit con Conventional Commits, PR.

**Reparto de roles:** Claude Code diseña/revisa (arquitectura, specs, criterio de aceptación, segunda opinión); Codex implementa tarea-a-tarea. Ver §"Reglas de trabajo con agentes".

**Trazabilidad:** cada tarea referencia su evidencia en `AUDIT_CLAUDE.md` (sección o ID de hallazgo F-xx) y los archivos concretos.

---

## Estado actual (actualizado 2026-07-24 — FASE 0 cerrada)

- **FASE 0 completa** en `codex/impeccable-ui-audit`: T0.1-T0.7 hechas y commiteadas. El dashboard vuelve a renderizar, `verify.ps1` falla de verdad ante un paso roto, hay un test que compila las 43 plantillas, cobertura con piso real (83%), mantenimiento ya se puede cerrar desde la UI, y `docs/03-Roadmap.md`/`openspec/config.yaml` reflejan el estado real.
- **Verificación tras el cierre de FASE 0:** `pytest` **170/170 verdes** (124 originales + 3 de mantenimiento + 43 de compilación de plantillas) · cobertura real **83.28%** (umbral `fail_under=83`) · `ruff check` limpio · `ruff format --check` limpio (35 archivos reformateados) · `manage.py check --deploy` limpio.
- **Nota de entorno:** en el sandbox de esta sesión, `ruff format --check` devuelve código de salida 2 con "Acceso denegado" pese a reportar el chequeo correcto ("88 files already formatted") — es un artefacto de este entorno (relación de confianza de dominio rota, confirmado con `icacls`/`whoami`), no un bug del repo ni de `verify.ps1`. Si reaparece en tu máquina, es señal de revisar permisos de `.ruff_cache`/`.pytest_cache`, no de tocar el script.
- **Sin P0 de seguridad.** Los IDOR (F-03–F-06) son gaps reales pero mitigados hoy por `tenant=NULL` universal; se cierran antes de centralizar el servidor (FASE 2).
- **Siguiente bloque recomendado:** FASE 1 (T1.1, partir `core`) o FASE 3 (T3.1, `on_delete=CASCADE→PROTECT`, es más chico y barato de hacer primero).

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
| T0.6 | ✅ | P2 | Corregir `openspec/config.yaml` y sincronizar `docs/03-Roadmap.md` | XS | — |
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
| T2.2 | ⬜ | P1 | `TenantScopedQuerysetMixin` en documentos + filtro por entidad (F-05) | M | T1.1 |
| T2.3 | ⬜ | P1 | `has_perm` en `/calendar/`, Kanban HTML y feed de eventos (F-06) | S | T1.1 |
| T2.4 | ⬜ | P2 | Rol `Viewer` con `view_*` explícitos (no `startswith`) | S | — |
| T2.5 | ⬜ | P2 | `django-csp` enforcing por entorno; SRI en 4 dependencias; `django-axes` + throttling (F-17, F-18) | M | — |

### FASE 3 — Integridad de datos `⛔ requiere FASE 1 · CAMBIAR AHORA`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T3.1 | ⬜ | P1 | `on_delete=CASCADE → PROTECT` en Document/Alert/historias + respaldo desnormalizado (F-07) | S | — |
| T3.2 | ⬜ | P1 | ADR + migración de tenancy: `tenant` en 17 modelos, `NOT NULL` con backfill, scoping único (F-08) | XL | T1.1 |
| T3.3 | ⬜ | P1 | `CheckConstraint` + `UniqueConstraint` compuestos con tenant (F-10) | L | T3.2 |
| T3.4 | ⬜ | P2 | Migrar estados a `TextChoices` (no cambia el esquema) | M | — |
| T3.5 | ⬜ | P3 | Índices compuestos `is_active`+fecha/estado | S | — |

### FASE 4 — Testing `⛔ requiere FASE 0; parcial tras FASE 3`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T4.1 | ⬜ | P1 | `conftest.py` con fixtures `two_tenant_world`, `role_user()` | M | FASE 0 |
| T4.2 | ⬜ | P1 | Matriz de aislamiento cross-tenant por vista | L | T4.1, T3.2 |
| T4.3 | ⬜ | P1 | Tests de `generate_alerts`, `maintenance`, `dashboard` (hoy 0%) | L | T4.1 |
| T4.4 | ⬜ | P2 | Neutralización de fórmulas en reportes workboard (XLSX/DOCX) + test | M | — |
| T4.5 | ⬜ | P3 | Sustituir ~14 tests de bajo valor por los P0 de arriba | S | T4.1 |

### FASE 5 — UX y flujos operacionales `requiere FASE 0`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T5.1 | ⬜ | P2 | Unificar `app.css` en un solo set de tokens; eliminar clases sin definir (F-15) | M | — |
| T5.2 | ⬜ | P1 | Enlazar habilitaciones, búsqueda global e importadores en el sidebar (U1, F-14) | S | — |
| T5.3 | ⬜ | P1 | Búsqueda global que lleve al detalle (U2) | S | — |
| T5.4 | ⬜ | P1 | Dashboard accionable + disponibilidad de flota/vencimientos reales (U3, U4) | M | — |
| T5.5 | ⬜ | P1 | Formulario de vuelo reducido + prellenado desde permiso (U5) | M | — |
| T5.6 | ⬜ | P2 | Paginación HTMX + búsqueda en vivo alineadas (F-13) | S | — |
| T5.7 | ⬜ | P2 | Exportación visible en todas las listas (U6) | S | — |
| T5.8 | ⬜ | P2 | Limpiar fugas de i18n; accesibilidad (`scope`, labels) | M | — |
| T5.9 | ⬜ | P2 | Vendorizar assets locales (Bootstrap/HTMX/Chart.js/FullCalendar) + SRI | M | T2.5 |

### FASE 6 — Nuevas funcionalidades `⏸ requiere FASE 0-3 cerradas`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T6.1 | ⏸ | P2 | Alertas programadas + notificación email (U7, U8) | M | FASE 3 |
| T6.2 | ⏸ | P2 | Checklists pre-vuelo cableando `KanbanTask.source_object → FlightPermission` (U9) | M | FASE 3 |
| T6.3 | ⏸ | P3 | Vista previa de adjuntos (U10) | S | — |
| T6.4 | ⏸ | P3 | Panel de auditoría en la UI (U11) | M | T1.1 |
| T6.5 | ⏸ | P2 | Mantenimiento por horas/ciclos (campos nuevos) | L | FASE 3 |
| T6.6 | ⏸ | P3 | Gestión de baterías (modelo nuevo) | L | FASE 3 |
| T6.7 | ⏸ | P1 | **DJI Cloud API / telemetría** — diseñar SOLO tras estabilizar tenancy y constraints | XL | FASE 3 |

### FASE L — Limpieza y orden del repositorio `puede correr en paralelo a FASE 0`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| TL.1 | ✅ | P2 | Corregir `openspec/config.yaml` (metadatos falsos) | XS | — |
| TL.2 | ✅ | P2 | `BACKLOG.md` → registro histórico que apunta a este plan | XS | — |
| TL.3 | ✅ | P3 | Eliminar artefactos temporales sueltos (`.tmp-*.sqlite3`, `.tmp-check-logs/`) | XS | — |
| TL.4 | ⬜ | P2 | Sacar `.agents/skills/impeccable/` del repo (submódulo/externo) — **decisión del dueño** | S | — |
| TL.5 | ⬜ | P3 | Borrar `.atl/skill-registry.md` (rutas absolutas, usuario) y `prompts/` (obsoleto) — **decisión del dueño** | XS | — |
| TL.6 | ⬜ | P2 | Cerrar `ui-modernization`, mergear a `main`, podar ramas remotas obsoletas y pares `-clean` | M | FASE 0 |
| TL.7 | ⬜ | P3 | Atender los 5 PRs de Dependabot | S | T0.3 |
| TL.8 | ⬜ | P2 | Consolidar `openspec/`: crear `openspec/specs/` y archivar los 5 changes al 100% | M | — |
| TL.9 | ⬜ | P2 | Ampliar `AGENTS.md`: DoD por tipo de cambio, contrato de lectura, reglas de commit, precedencia documental | S | — |
| TL.10 | ⬜ | P3 | Añadir `.github/pull_request_template.md` con casillas verificables | XS | — |

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
- **Evidencia:** F-12; `openspec/config.yaml:8,28,38-49`, `docs/03-Roadmap.md`.
- **Cambio:** (parcialmente hecho, ver TL.1) marcar en `docs/03-Roadmap.md` las 13 casillas ya implementadas.
- **Aceptación:** ningún doc afirma capacidades falsas del proyecto.

### T0.7 — Formato
- **Evidencia:** `ruff format --check` falla en 35 archivos.
- **Cambio:** `uv run ruff format .` y commit del reformateo (idealmente en su propio commit «style:»).
- **Aceptación:** `verify.ps1` verde de punta a punta.

---

## Reglas de trabajo con agentes

1. **Una intención por rama y por commit.** Nunca mezclar tooling/dependencias con producto (el commit `980b763` con 62.661 líneas es el anti-ejemplo).
2. **Definition of Done por tipo de cambio:** modelo → migración + test de constraint; vista → test 403 + test de scope de tenant; comando → test camino feliz + error; formulario → test por cada `add_error`.
3. **Contrato de lectura (hoy ausente, causa de F-05/F-06):** toda vista que expone datos de dominio exige `view_*` y acota por tenant.
4. **Precedencia documental:** `AGENTS.md` > `MASTER_PLAN.md` > `openspec/specs/` > `AUDIT_CLAUDE.md` > `BACKLOG.md` > `README.md` > `docs/*`. `prompts/` y `docs/0X-*.md` son históricos, no autoritativos.
5. **El gate manda:** ninguna tarea se marca ✅ sin `verify.ps1` verde (tras T0.3) y sin cumplir su criterio de aceptación.
6. **No implementar FASE 6 antes de cerrar FASE 0-3.** DJI/telemetría/PostgreSQL/Celery están diferidos por diseño (YAGNI).

---

*Este plan reemplaza como fuente de trabajo pendiente a la sección «pendiente» de `BACKLOG.md`. Evidencia completa en [AUDIT_CLAUDE.md](AUDIT_CLAUDE.md).*
