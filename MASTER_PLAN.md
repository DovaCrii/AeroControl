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

La ruta obligatoria del plan externo está **completa**. Lo siguiente ya no viene
de esa ruta sino de la auditoría, y el orden recomendado es:

1. **Cargar datos reales** — 0 documentos, 0 reglas: todo BLOQUE 2/6 está
   construido y sin nada que procesar. El dashboard ahora **guía los tres
   pasos** (tarjeta "Activa el monitoreo de cumplimiento"): tipo de documento →
   documentos con vencimiento → una regla → `generate_alerts`; recién entonces
   asignar operadores responsables y validar el digest. *(Decisión de negocio del
   usuario, no del agente.)*
2. **BLOQUE GEO** — editor geoespacial KMZ/KML. Propuesta aprobada 2026-07-27
   ([docs/dev/geo-editor-plan.md](docs/dev/geo-editor-plan.md)); arranca en GEO-0
   con el "go" del usuario. Es el trabajo grande de producto pendiente.
3. **V.10-V.12** — la seguridad diferida de la revisión: endurecer CSP (exige
   extraer el JS inline primero), vendorizar CDN con SRI (T5.9 — GEO-0 lo empieza),
   y la política de sesión/cambio de contraseña.
4. **TL.7** — los 5 PRs de Dependabot.

La revisión V.1-V.39 está **completa** salvo V.3 (⛔ T3.2) y V.10-V.12 (⬜
decisión). La tanda E se ejecutó el 2026-07-25 con el alcance que eligió el
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
- Agregar usuarios al grupo *Dirección*. Hoy existe **un solo usuario** en todo
  el sistema, así que el informe ejecutivo llegaría solo a esa cuenta.
- No hay documentos, alertas ni reglas cargadas (0/0/0): el resumen diario no
  tiene nada que enviar hasta que exista documentación con vencimientos.

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
| V.10 | ⬜ | P2 | CSP decorativo: `CSP_REPORT_ONLY=False` **borra** la cabecera, htmx viene de unpkg fuera de la política, ~50 líneas inline sin nonce, sin report-uri. Orden: extraer JS inline → alinear orígenes → `django-csp` | — |
| V.11 | ⬜ | P2 | Sin SRI en Bootstrap/htmx y `htmx.org@2.x` es rango flotante en unpkg. Es T5.9 (vendorizar) | — |
| V.12 | ⬜ | P2 | Sesión: 14 días por defecto, sin expiración deslizante, sin `password_change` fuera de `/admin/`. Decidir política para equipos compartidos en terreno | — |
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
| T2.2 | ⬜ | P1 | `TenantScopedQuerysetMixin` en documentos + filtro por entidad (F-05) | M | T1.1 |
| T2.3 | ✅ | P1 | `has_perm` en `/calendar/`, Kanban HTML y feed de eventos (F-06) — `CalendarAccessMixin` por fuente de evento, desplegables por `view_*` del modelo que listan, `?types=` acotado a lo permitido (`3611d06`) | S | T1.1 |
| T2.4 | ✅ | P2 | Rol `Viewer` con `view_*` explícitos (no `startswith`). En la base real recibía **35** permisos, incluidos `authtoken.view_token`, `auth.view_user`, `sessions.view_session` y `core.view_auditevent`; ahora 20 (`c5d22dd`) | S | — |
| T2.5 | ✅ | P2 | **[nuevo]** `TIME_ZONE` pasa a `America/Santiago` (decisión del usuario, 2026-07-25) y configurable por entorno. Todo `date.today()` de producción reemplazado por `timezone.localdate()` en `generate_alerts`, `send_alert_digest`, `digest.py`, `dashboard/views.py` y `compliance/models.py`, más las fixtures de prueba que comparaban contra la fecha del SO. Verificado: las dos nociones de "hoy" ahora coinciden | S | — |
| T2.5 | ⬜ | P2 | `django-csp` enforcing por entorno; SRI en 4 dependencias; `django-axes` + throttling (F-17, F-18) | M | — |

### FASE 3 — Integridad de datos `⛔ requiere FASE 1 · CAMBIAR AHORA`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T3.1 | ✅ | P1 | `on_delete=CASCADE → PROTECT` en Document/Alert/historias (F-07). Respaldo desnormalizado descartado deliberadamente (ver commit `6066271`) | S | — |
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
| R.10 | ⬜ | P3 | **[UI, pendiente]** Unificar `app.css`. Medido: ver "Anatomía de R.10" más abajo. Es T5.1 | M | — |

**Verificado en vivo** (servidor de demo, mediciones de contraste reales, no a ojo). Hallazgos extra encontrados durante la revisión y corregidos: paleta de gráficos invisible en modo oscuro, etiquetas de gráficos con valores crudos (`active` → `Activo`), agregaciones del dashboard contando registros archivados (A5), y ~19 cadenas sin traducir.

**Nota de causa raíz:** R.7 tardó dos intentos porque `[data-theme="dark"] .sidebar-label` ganaba por especificidad sobre la regla de tokens más nueva. Mientras `app.css` conserve dos generaciones superpuestas (R.10/T5.1), este tipo de corrección seguirá necesitando editar el override antiguo además del nuevo.

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
4. **BLOQUE 4 (parcial)** ✅ — B4.1 (validación de `AlertRule`) y B4.2 (duplicados de operadores). B4.3/B4.4 (habilitaciones DGAC, compatibilidad operador–aeronave) **diferidos** hasta que el usuario apruebe su diseño.
5. **BLOQUE 6.1 y 6.2** ✅ — Reporte documental determinista + informe ejecutivo por correo.

> **Ruta completa.** Los cinco pasos en alcance están cerrados. Conforme al plan, aquí se **detiene** la ejecución automática: lo que queda requiere instrucción explícita.

**Bloques DIFERIDOS (no ejecutar sin instrucción explícita):** BLOQUE 3 (UX Kanban), BLOQUE 5 (centro de administración, salvo `JobRun` ya adelantado), BLOQUE 6.3 (asistente IA), y B4.3/B4.4 (habilitaciones DGAC y compatibilidad operador–aeronave, que además deben proponerse como diseño antes de implementarse).

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
| B4.3 | ⏸ | P2 | **DIFERIDO** Habilitaciones DGAC: modelo (operador, tipo, vigencia, evidencia vía `Document`, reglas de alerta). Proponer diseño en el PR antes de implementar | M | Aprobación del usuario |
| B4.4 | ⏸ | P2 | **DIFERIDO** Compatibilidad operador–aeronave al crear permisos de vuelo. Proponer diseño antes de implementar | M | Aprobación del usuario |

**Aceptación del bloque (parte en alcance): cumplida.** B4.1 con 10 pruebas y migración verificada sobre la base de demo (normalizó un valor heredado y archivó una regla rota con nota); B4.2 con 12 pruebas, incluida la fusión de referencias por GFK, y verificada de punta a punta en la demo. B4.3/B4.4 siguen diferidos esperando aprobación de diseño.

**Decisión registrada (B4.2):** el registro que sobrevive a una fusión se elige por **cantidad de referencias** primero, no por campos rellenos. Probando con datos realistas, contar campos elegía un duplicado con poco uso que solo tenía un teléfono extra, en vez del registro que era responsable del centro de costo y tenía tarea asignada. La fusión es de un grupo por ejecución y hay que nombrarlo: no existe modo masivo.

### BLOQUE 5 — Centro de administración operativo `rama codex/admin-center` `⏸ DIFERIDO (salvo B2.0 JobRun, adelantado al Bloque 2)`

Convertir `AdministrationCenterView` + `administration.html` en panel de situación, no solo menú.

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| B5.1 | ⏸ | P2 | Badges por tarjeta: alertas sin resolver, documentos que vencen ≤30 días, reglas activas, usuarios sin grupo (una consulta agregada por métrica) | M | — |
| B5.2 | ⏸ | P2 | Sección "Salud y operación": último respaldo (fecha+hash), última ejecución de cada job (`JobRun`) con resultado, estado de `/health/`; aviso si un job diario no corre hace >48 h | M | B2.0 |
| B5.3 | ⏸ | P2 | Acciones rápidas (POST + confirmación + permiso + `AuditEvent`): correr `generate_alerts`, enviar digest de prueba, iniciar respaldo. Documentar el límite de ejecutar en el request | M | B2.0 |
| B5.4 | ⏸ | P2 | Vista de auditoría de solo lectura (`AuditEvent` filtrable por usuario/modelo/fecha, permiso `view_auditevent`) | M | — |
| B5.5 | ⏸ | P3 | Panel de usuarios y roles (solo lectura, con enlace al admin técnico) | S | — |

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
| GEO-0 | ⬜ | Fundaciones: app `apps/geo`, vendorizar Leaflet+Geoman con SRI (`static/vendor/`), lxml a dep directa, `FILE_UPLOAD_MAX_MEMORY_SIZE`/`DATA_UPLOAD_MAX_MEMORY_SIZE` explícitos, enmienda a `docs/frontend-boundary.md` (islas JS admisibles) | — | ✔ |
| GEO-0b | ⬜ | Quick-wins ortogonales: `set_audit_context` en `DocumentReplace`/`DocumentDelete`/`StatusTransitionView`/`FlightRecordDelete`; handler de error 4xx en el drag del Kanban | — | opc. |
| GEO-1 | ⬜ | Modelos (`GeoPlan`/`GeoPlanVersion` append-only/`GeoPlanHistory`) + migración + `approve_geoplan` en `bootstrap_roles` + mapping en `signals.py`. Tests: unicidad, cerrojos, historia | GEO-0 | ✔ |
| GEO-2 | ⬜ | Parser KML/KMZ endurecido + canónico AeroKML JSON. Tests: corpus feliz + 6 fixtures maliciosos (DOCTYPE, bomba, traversal, 300 entradas) | GEO-0 | ✔ |
| GEO-3 | ⬜ | Generador export + **round-trip test** (igualdad semántica doble pasada; verificación manual en Google Earth documentada) | GEO-2 | ✔ |
| GEO-4 | ⬜ | Import (form multipart sobre el pipeline existente → `Document` `GEO_SOURCE` + `GeoPlan` + V1, atómico) + lista/detalle shell + mover `ViewModelPermissions` a core. Tests 403 | GEO-1, GEO-2 | ✔ |
| GEO-5 | ⬜ | API lectura (meta, versiones, content con `ETag`) + OpenAPI manual extendido | GEO-1 | ✔ |
| GEO-6 | ⬜ | API commit + restore (409 doble capa `conflict`/`plan_locked`, validación server, audit, throttle scoped). Tests: conflicto, bloqueo, `no_change` | GEO-5, GEO-3 | ✔ |
| GEO-7 | ⬜ | Isla JS fase 1 (solo lectura): mapa + proveedores de tiles + render por folder + panel show/hide + mediciones | GEO-4, GEO-5 | ✔ |
| GEO-8 | ⬜ | Isla JS fase 2: edición Geoman (punto/línea/polígono/rect, mover, vértices), inspector, undo/redo, guardar con `summary`, manejo 409. Aceptación: importar→editar→commit→export→abre en Google Earth | GEO-7, GEO-6 | ✔ |
| GEO-9 | ⬜ | Workflow: 6 transiciones + botones en el shell + editor read-only en aprobados + tests 403/transición inválida | GEO-4 | ✔ |
| GEO-10 | ⬜ | Export POST + UI (KML/KMZ, copia de `kmz_resources` del original) + panel de versiones con restore | GEO-6, GEO-3 | ✔ |
| GEO-11 | ⬜ | Capas avanzado: reorder/mover entre folders/duplicar/split de geometrías | GEO-8 | V2 |
| GEO-12 | ⬜ | Diff visual entre versiones (por `uid`) + edición de `ExtendedData` | GEO-10 | V2 |
| GEO-13 | ⬜ | Iconos embebidos servidos, StyleMap highlight editable, validación XSD | GEO-10 | V2 |
| GEO-14 | ⬜ | Hooks DJI: interfaz `MissionExporter` + comparación planificado-vs-ejecutado | GEO-10 | V2 |

**No bloquea T3.2** (tenancy): el scoping entra por `cost_center` como el resto y la migración futura lo cubre. GEO-0 absorbe parte de T5.9 (vendorización+SRI) y prepara V.10 (CSP).

### FASE L — Limpieza y orden del repositorio `puede correr en paralelo a FASE 0`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| TL.1 | ✅ | P2 | Corregir `openspec/config.yaml` (metadatos falsos) | XS | — |
| TL.2 | ✅ | P2 | `BACKLOG.md` → registro histórico que apunta a este plan | XS | — |
| TL.3 | ✅ | P3 | Eliminar artefactos temporales sueltos (`.tmp-*.sqlite3`, `.tmp-check-logs/`) | XS | — |
| TL.4 | ✅ | P2 | Sacar `.agents/skills/impeccable/` del repo (aprobado por el usuario) | S | — |
| TL.5 | ✅ | P3 | Borrar `.atl/skill-registry.md` y `prompts/` (aprobado por el usuario) | XS | — |
| TL.6 | 🔄 | P2 | Merge a `main` preparado (fast-forward, verificado); falta el `push`. Poda de ramas inventariada más abajo ("Inventario de ramas"), pendiente de ejecución por el usuario | M | FASE 0 |
| TL.7 | ⬜ | P3 | Atender los 5 PRs de Dependabot | S | T0.3 |
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
