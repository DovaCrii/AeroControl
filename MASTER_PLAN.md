# MASTER_PLAN — AeroControl

> **Fuente única de verdad del trabajo pendiente.** Consolida la auditoría técnica ([AUDIT_CLAUDE.md](AUDIT_CLAUDE.md)) y el plan de producto que el usuario aportó (`PLAN_CLAUDE_CODE.md`, integrado el 2026-07-24 como los BLOQUE 0-4 de la sección "Bloques de producto" más abajo) en un único tablero ejecutable con seguimiento de estado.
> **Creado:** 2026-07-24 · **Rama base de referencia:** `main` (25 commits por detrás de `codex/impeccable-ui-audit`).
> **Regla de oro:** este proyecto está en **pausa de estabilización**. No se incorpora DJI Cloud API (T6.7) ni funcionalidad fuera de lo listado aquí. Los BLOQUE 1-4 de producto sí están autorizados a avanzar sin esperar el cierre completo de FASE 1-3 (solo con las dependencias puntuales que cada tarea declara, p. ej. B1.1→T3.1). Un bloque no empieza hasta que sus dependencias declaradas estén ✅.

---

## Prioridades post-auditoría (2026-08-07 — leer esto primero)

`v0.4.0-beta` está cortado, desplegado y operando con datos reales. El
2026-08-07 entraron **tres insumos nuevos** que reordenan el tablero:

- **Revisión en vivo del usuario** (`D:\I+D\Obsidian\Revisiones luego de
  Auditoria.md`, 19 capturas) — origen de los bloques `R1`–`R8` de más abajo.
- **Guía de auditoría ISO 9001/14001/45001** para levantamientos con RPAS —
  14 cláusulas con evidencia exigible. Mapeo completo en
  [docs/auditoria-iso-trazabilidad.md](docs/auditoria-iso-trazabilidad.md);
  bloque `R7`.
- **AeroLink** (`DovaCrii/AeroLink`) — gateway DJI Pilot 2 que extrae datos del
  RPA sin depender de lo que escriba el operador. Contrato de coexistencia en
  [docs/dev/adr-0002-coexistencia-aerolink.md](docs/dev/adr-0002-coexistencia-aerolink.md);
  bloque `X`.

**Orden vigente:**

1. ~~**Ensayo de restauración de respaldos (B-01/B-02) + copia fuera de la VM.**~~
   **✅ Hecho 2026-08-10.** `verify_backup` + `restore_backup` contra el
   snapshot `aero_ops_20260809_180019.sqlite3` (checksum verificado, copia
   fuera de la VM en OneDrive, restauración a ruta de ensayo, 16
   aeronaves/41 operadores/14 centros de costo/2 permisos legibles por el
   ORM). Registro completo en `docs/backend-follow-up.md`. **Ya no bloquea
   R2.2/R2.3, R3.1/R3.1a ni R4** — la copia restaurada queda disponible para
   que el importador de R4 corra contra ella en modo informe.
2. **`R1` — bugs que ocultan información de cumplimiento.** Barato y crítico:
   hoy el calendario **no muestra** las vigencias DGAC/JAC en su vista por
   defecto. Es justo la información que la auditoría exige tener a la vista.
3. **`R2` — permiso de vuelo**: no existe vista de edición, y el folio DGAC
   ausente se filtra como `status · purpose` a cuatro pantallas distintas.
4. **`R3` — estandarización**, y **`X.1` — `serial_number` como llave única.**
   Ambos **antes** de importar documentos: si se importa primero, se reimporta.
5. **`R4` — repositorio documental** (importador desde `Z:` con revisión previa).
6. `R5` trazabilidad → `R6` alertas/reportes → `R7` base ISO → `R8` clima.
7. **CSP a enforcing en producción**: verificado en demo, solo falta activar la
   variable de entorno en `p340`.
8. **Deuda técnica (T1.x, T3.x, T4.x): política incremental**, sin migración
   grande. `core/views.py` (1.150 líneas) y `registry/views.py` (948) son
   grandes, pero con 679 tests verdes y uso diario real, el riesgo de una
   migración XL supera su beneficio *ahora*. Extraer mixins/selectors **solo al
   tocar el flujo correspondiente** por otra razón. Ver la nota en T1.1.
9. **Higiene recurrente**: cerrar cada ventana con `ruff check .` **y**
   `ruff format --check .`, no solo `pytest` — el CI corre ambos (`ci.yml:26-27`)
   y ya estuvo rojo días por no hacerlo.

*Cerrados y fuera de la cola:* ~~T2.1~~ (ya estaba en el código desde `03b4dbb`),
~~B3.1/B3.2/B3.5~~ y ~~T5.7~~ (2026-08-07), ~~LV-59 (c)~~ (2026-08-05).
Quedan bajo demanda: LV-6 (Gantt), T5.8, LV-65 (absorbido por `R5.5`).

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

> **Histórico — superado por "Prioridades post-v0.4.0-beta" al inicio del
> documento.** Todo lo que este bloque describe como pendiente (GEO V2, T3.2
> antes que nada, etc.) ya se resolvió o se reordenó desde el 2026-07-30. Se
> conserva tal cual por su valor de bitácora de decisiones, no como guía de
> qué hacer ahora.

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
| T1.1 | ⬜ | P1 | Partir `core`: infra pura + `apps/tenancy`; mover calendario/búsqueda a `dashboard`. **Política 2026-08-05** (auditoría de Codex + estado real del proyecto): diferida deliberadamente, no como proyecto aparte — con 670+ tests verdes y uso diario real en producción, el riesgo de una migración XL ahora supera su beneficio. Extraer piezas de `core` (1.150 líneas) solo al tocar el flujo correspondiente por otra razón, nunca de una sola vez. Ver "Prioridades post-v0.4.0-beta" al inicio del documento. | XL | FASE 0 |
| T1.2 | ⬜ | P1 | Refactor `UnifiedCalendarEventsView` (231 líneas) → proveedores de eventos por app | L | T1.1 |
| T1.3 | ⬜ | P2 | Eliminar señales `pre_save`; `transition_to(status, actor, notes)` en el modelo | M | T1.1 |
| T1.4 | ⬜ | P2 | Auditoría atómica con la mutación; no tragar el fallo de escritura | M | T1.3 |
| T1.5 | ⬜ | P3 | `selectors.py` por app (lecturas/scoping/agregaciones) | L | T1.1 |

### FASE 2 — Seguridad y permisos `⛔ requiere FASE 1`

| ID | Est. | Prio | Tarea | Esf. | Dep. |
|---|:--:|:--:|---|:--:|:--:|
| T2.1 | ✅ | P1 | Cerrar IDOR workboard: acceso a tablero en checklist/stage; `get_queryset` scoped en List (F-03, F-04). **Corregido 2026-08-07**: esta fila seguía en ⬜ pero el fix ya estaba en el código desde el `03b4dbb` del 2026-07-24 (tanda A de seguridad, ver V.1/V.2 arriba) — `WList.get_queryset` ya scopea por `visible_tasks_for_user`/`accessible_boards`, y `ChecklistItemCreate`/`ChecklistItemToggle`/`StageCreate` ya llaman `user_can_edit_board` antes de mutar. Verificado leyendo `apps/workboard/views.py` línea a línea contra F-03/F-04; el checklist de FASE 2 nunca se actualizó cuando se cerró V.1/V.2. Sin cambio de código, solo de tablero. | M | — |
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
| T5.7 | ✅ | P2 | **Hecho 2026-08-07.** El backend ya soportaba `?export=csv` en casi todas las listas (`CsvExportMixin` mezclado en `WList`/`OList`/`MList`/`ComplianceList`/registry); el hueco real eran 3 plantillas que reconstruyen `content` a mano y nunca renderizaban el link: Documentos, Alertas y Registros de mantenimiento. Agregado el botón en las 3, con test que verifica presencia del link **y** que `?export=csv` devuelve un CSV real. **Fuera de alcance, marcado para otra sesión**: `ResourceMovementLogList` (registry) no tiene `CsvExportMixin` en absoluto — necesitaría además resolver cómo exportar su `resource_label` (property, no field). | `templates/compliance/{document,alert}_list.html`, `templates/maintenance/record_list.html` |
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
| LV-23 | ✅ | P3 | **Resuelto vía LV-38** (2026-08-03, ver esa entrada más abajo): el roster de operadores/flota ya quedó como grid multi-columna con scroll acotado. Esta fila quedó desactualizada (seguía marcada abierta pese a que LV-38 la cita explícitamente como su concreción) — corregido al hacer el cierre de pendientes previo al 3er deploy (2026-08-04). | `app.css` + form del permiso |
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
| LV-44 | ✅ | P3 | **Hecho 2026-08-04** (encontrado en la verificación visual post-deploy de LV-36/34): la ficha de detalle del CC mostraba **"RESPONSIBLE CONTACT NAME"/"RESPONSIBLE CONTACT EMAIL" en inglés**, únicos campos sin traducir en una página toda en español. Causa: `CostCenter.responsible_contact_name/email` no tenían `verbose_name` explícito → Django deriva "Responsible contact name", msgid ausente del catálogo (el form sí traduce, con label propio "External contact name/email", ya en el `.po`). Fix: `verbose_name=_("External contact name"/"External contact email")` en el modelo — mismo pipeline `translate_field_label` que ya usa el form, reutiliza los msgids existentes sin tocar el `.po`/`.mo`. Migración `registry 0022` (solo `AlterField`, sin cambio de esquema). 222 tests (registry+compliance) verdes; verificado en browser: ahora dice "NOMBRE DEL CONTACTO EXTERNO"/"CORREO DEL CONTACTO EXTERNO". **Corrección 2026-08-04 (misma sesión):** el primer intento usó minúscula (`"external contact name"`) — se veía bien en el navegador *por casualidad* (el pipeline de doble-traducción de `translate_field_label` capitaliza y reintenta, tapando el desajuste), pero `test_every_translatable_string_is_in_the_catalog` lo detectó como mayúscula distinta a la del catálogo — el patrón correcto y ya usado por otros campos (`"Employee ID"`, `"DGAC credential"`, etc.) es que el literal `_()` coincida **exactamente** con el msgid. Corregido a mayúscula inicial en el modelo y en la migración `0022` (aún no desplegada a ningún lado); suite completa 632/632 verde. | `apps/registry/models.py`, migración `0022` |
| LV-45 | ✅ | P1 | **Hecho 2026-08-04** (reportado por el usuario: "el botón crear tarea no funciona"): reproducido en el demo — el botón manual "Crear tarea" de cada fila en `/compliance/alert/` fallaba con "No hay ningún tablero Kanban disponible para alojar la tarea de seguimiento". Causa raíz: el comando `init_dgac_board` (que siembra el tablero "Cumplimiento DGAC") **nunca se corrió** — ni en el demo ni en el runbook de deploy de la VM (Parte D solo hacía migrate/bootstrap_roles/collectstatic/createsuperuser). El botón manual es independiente del flag automático `create_kanban_task` de cada regla (que sí queda apagado a propósito por `seed_alert_rules`), así que necesita el tablero igual. Fix: corrido `init_dgac_board` en el demo (verificado en browser: "Tarea de seguimiento creada.", tablero visible en `/workboard/`); doc `compliance-setup.md` aclarado (correr `init_dgac_board` desde el día 1, no solo si se activa la creación automática); añadido a `docs/dev/ubuntu-vm-deploy.md` Parte D para que no falte en futuros setups. **Corrido en la VM `p340` el 2026-08-04** por el usuario ("Created board 'Cumplimiento DGAC' with 6 stages and 5 labels.") — el botón funciona también en producción. | `docs/compliance-setup.md`, `docs/dev/ubuntu-vm-deploy.md` |
| LV-46 | ✅ | P1 | **Hecho 2026-08-04** (pedido del usuario: marcar una aeronave que "se cayó" y aún no fue enviada a mantenimiento, cruzado con alerta): nuevo estado `Aircraft.status="damaged"` ("Mal estado", badge rojo en la lista, distinto de "Mantenimiento" ámbar). Botón de un clic **"Reportar accidente / daño"** en la ficha (junto a "Enviar a mantenimiento" de LV-26, con confirmación) — sin formulario que llenar primero, porque un reporte de accidente no debería esperar a elegir fecha/responsable. La acción (`AircraftReportIncident`) pone el estado en `damaged` **y** crea de inmediato un `MaintenanceRecord` (`emergency`/`pending`), lo que dispara la regla de alerta **ya existente** "Mantenciones abiertas" (LV-26) sin necesitar una regla nueva — se investigó y se descartó ligar una regla nueva directamente a `registry.aircraft`/`status` porque el motor genérico de alertas por status trata cualquier valor fuera de {completed, denied, non_compliant} como abierto, lo que habría generado una alerta para *cada* aeronave "Activa". Migración `registry 0023` (solo `choices`, sin cambio de esquema). 234 tests (registry+maintenance+compliance) verdes; verificado end-to-end en el demo: estado→"Mal estado", badge rojo en lista, registro "Emergencia·Pendiente" en la ficha, y tras `generate_alerts` la alerta aparece en `/compliance/alert/` con "Crear tarea"/"Resolver" funcionando. | `apps/registry/models.py`, `apps/maintenance/views.py`, `apps/maintenance/urls.py`, `templates/registry/_aircraft_rows.html`, `templates/registry/aircraft_detail.html`, migración `0023` |
| LV-47 | ✅ | P1 | **Hecho 2026-08-04** (reportado por el usuario: "botón siguiente anterior no funciona" en `/calendar/`): el calendario tenía **tres** navegadores de mes superpuestos y desconectados entre sí — los "← Anterior / Siguiente →" del `.page-header` (los de la captura) usaban links `?month=`, pero **FullCalendar los ignora por completo** (se re-inicializa siempre en el mes actual vía JS, no lee ese parámetro) — click cambiaba la URL pero el calendario visible no se movía nunca. Además había una copia idéntica en `.legacy-calendar-header`, pensada como respaldo si JS falla, pero **permanentemente oculta por CSS** (`display:none !important`), o sea que ni siquiera servía de respaldo real. Fix: quitados los botones muertos del `.page-header` (FullCalendar ya tiene su propia navegación funcional junto a "Hoy"); unidos `.legacy-calendar-header` + `.calendar-fallback` bajo un solo wrapper `.calendar-noscript` que `calendar.js` oculta en un solo paso **cuando FullCalendar realmente carga** — así el respaldo sin JS ahora sí tiene título+navegación funcionando en el escenario real para el que existe (falla de JS/CDN), en vez de quedar permanentemente oculto por CSS. 2 tests de calendario verdes; verificado en browser inyectando el `calendar.js` fresco (el `<script src>` cacheado de la sesión de pruebas no reflejaba la edición, un artefacto de caché del navegador de prueba, no del producto) — confirma que el wrapper se oculta correctamente y ya no quedan botones duplicados en el texto de la página. | `templates/core/calendar.html`, `static/js/calendar.js`, `static/css/app.css` |
| LV-48 | ✅ | P2 | **Hecho 2026-08-04** (reapertura del standby de Kanban, ver [[aerocontrol-kanban-standby]]): el usuario aclaró que el tablero ya no es un Kanban genérico sino el mecanismo de **seguimiento y ejecución correctiva de alertas** (evidente tras LV-45/LV-46, donde "Crear tarea" y el accidente de aeronave ya cruzan con este tablero) y pidió renombrarlo — eligió **"Seguimiento de alertas"** entre las opciones ofrecidas. Cambiado el msgid `"Action plan"` (única fuente para el `<h1>`, el `<title>` y el link del sidebar, hoy comentado por LV-7) de "Plan de acción" a "Seguimiento de alertas"; quitado el span oculto `visually-hidden` "Tablero Kanban" del `<h1>` (decorativo para lectores de pantalla, redundante y contradice el reencuadre). Sin más apariciones de "Kanban" en texto de usuario. 145 tests (workboard+compliance) verdes; verificado en browser: título de pestaña y `<h1>` dicen "Seguimiento de alertas", nada dice ya "Kanban". El link del sidebar sigue oculto por LV-7 (razón distinta, redundancia con el calendario/Gantt) — no se reabrió esa decisión; si se quiere navegación directa hay que decidirlo aparte. | `templates/workboard/kanban.html`, `django.po`/`.mo` |
| LV-49 | ✅ | P2 | **Hecho 2026-08-04** (pedido del usuario tras revisar el "Reporte de estado documental"): el reporte mostraba **0 documentos / 0,0% vigentes / 0 vencidos en todo centro de costo**, mientras "Alertas abiertas" sí mostraba datos reales — porque `_cost_center_row()` (`apps/compliance/reports.py`) solo contaba `compliance.Document` y nunca se actualizó tras LV-29 (vigencias DGAC en `Operator.credential_expiry`/`Aircraft.insurance_expiry`, que ya disparan alertas reales). Fix: nuevo helper `_vigencia_bucket_counts()` suma esas dos vigencias con los mismos buckets (vencido/≤7/≤15/≤30d) **solo cuando no hay filtro de tipo de documento** (las vigencias no tienen `doc_type`, así que un filtro por tipo las excluye correctamente en vez de arrastrarlas de vuelta). A diferencia de `Document.expiry_date` (null = nunca vence, cuenta como vigente), una vigencia sin valor se **excluye del total** (no se entró el dato aún), igual que ya hace `generate_alerts`. Como las 4 vistas (pantalla/CSV/XLSX/DOCX) y el informe ejecutivo comparten `build_compliance_report()`, el fix se propaga solo — un único punto de cambio. Nota aclaratoria agregada bajo la tabla ("Incluye vigencias DGAC…", oculta cuando hay filtro de tipo). 3 tests nuevos + 21/21 de `test_reports.py` + 103 de compliance completo, todos verdes. Verificado en demo: pasó de 0/0,0%/0 a **6/66,7%/2** con desglose real por CC; con filtro de tipo activo vuelve a 0 (correcto, sin documentos de ese tipo) y la nota se oculta. De paso se encontró (y se dejó como tarea aparte, no corregido aquí) un bug preexistente: un `doc_type`/`cost_center` mal formado en la URL rompe la página con un 500 en vez de ignorarlo. | `apps/compliance/reports.py`, `templates/compliance/report.html`, `apps/compliance/test_reports.py` |
| LV-52 | ✅ | P1 | **Hecho 2026-08-04** (reportado por el usuario con captura: la ficha de un permiso mostraba **"None"** como título): la plantilla usaba `{{ permission.permission_number }}` (campo crudo) en vez de `{{ permission }}` (que llama a `__str__()`, ya con fallback correcto desde LV-39 — "Solicitado · Propósito" cuando no hay folio). Encontrado y corregido el mismo patrón en **5 lugares**: `permission_detail.html` (título+H1), `permission_list.html` (columna Número), `flightrecord_detail.html`, `costcenter_detail.html` (pestaña Permisos) y el respaldo sin-JS de `calendar.html`. Sin migración. Verificado end-to-end en demo: un permiso nuevo sin folio ahora muestra "Solicitado · Verificacion LV-39-fix" en la lista y en el título/H1 de su ficha, en vez de "None". | `templates/operations/permission_detail.html`, `templates/operations/permission_list.html`, `templates/operations/flightrecord_detail.html`, `templates/registry/costcenter_detail.html`, `templates/core/calendar.html` |
| LV-50 | ✅ | P2 | **Hecho 2026-08-04** (reportado por el usuario: "planes geoespaciales no permite cargar documento… no lo encuentra"): la sección "Planes geoespaciales" de la ficha del permiso no tenía **ninguna** forma de vincular/importar un plan — a diferencia de "Documentos" y "Registros de vuelo", que sí tienen su botón "+ Agregar". La única vía existente era `/geo/plans/import/`, sin acceso desde el permiso y sin preselección. Fix: botón **"+ Importar plan"** en esa sección (gated por `perms.geo.add_geoplan`, mismo patrón que las otras dos) que enlaza a `geo-plan-import?flight_permission=<pk>`; nuevo `GeoPlanImportView.get_initial()` que preselecciona ese permiso en el formulario (mismo patrón que `maintenance-create?aircraft=`). 1 test nuevo + 118 de operations+geo verdes. Verificado en demo: el botón aparece con el link correcto. | `apps/geo/views.py`, `templates/operations/permission_detail.html`, `apps/geo/test_views.py` |
| LV-51 | ✅ | P1 | **Hecho 2026-08-04** (pedido del usuario: "al aprobar el permiso de vuelo debe ser obligación subir el permiso en PDF que arroja el SIGO"): `FlightPermissionApprove` ahora exige que exista un `Document` activo, de versión vigente, con `doc_type__code="dgac-flight-permit"` ("Autorización DGAC (carta de permiso)") ligado al permiso **antes** de permitir la transición a "Aprobado" — evita que el estado en AeroControl adelante al papeleo real de la DGAC. Sin el documento, la aprobación se bloquea con mensaje de error y el estado no cambia (sin fila de historial). Actualizado el test existente que aprobaba sin documento (ahora adjunta uno primero) + 3 tests nuevos (bloqueo sin doc, éxito con doc, ignora una versión no vigente/archivada). Verificado end-to-end en demo: "Aprobar" sin el PDF deja el permiso en "Solicitado" con el mensaje de error correcto. | `apps/operations/views.py`, `apps/operations/tests.py` |
| LV-53 | ✅ | P2 | **Hecho 2026-08-04** (pedido del usuario: "optimizar columnas y distribución de Permisos, aplicarlo como se ha hecho antes, normalizar" — alcance acordado: solo Permisos por ahora). Auditoría: Centros de costo/Aeronaves/Operadores/Habilitaciones/Asignaciones/Registros de mantenimiento ya seguían el patrón `generic/list.html` + partial de filas HTMX; Permisos (junto con Documentos de la empresa, Alertas, Movimientos de recursos, Planes geoespaciales y Tareas — quedan fuera de este alcance) tenía una plantilla plana propia, sin búsqueda en vivo ni partial. Migrado Permisos al patrón: nuevo `_permission_rows.html` (Número/Operadores/Aeronaves/Vigencia/Estado + acción "Ver", con el fix de LV-52 ya aplicado), vista con `htmx_template_name` propio (mismo patrón que `OperatorList`, T5.6\F-13). **Cambio aditivo en `generic/list.html`** (afecta a todos los módulos, pero sin cambiar su salida): se envolvieron en bloques nuevos `{% block list_primary_actions %}` (Exportar CSV + Nuevo) y `{% block list_filters %}` (antes código fijo, sin bloque) para que Permisos pueda tener sus propios filtros (estado de negocio + rango de fechas) sin heredar el filtro genérico `is_active` que no le aplica — contenido por defecto idéntico al anterior, cero cambio visual para los módulos que no sobrescriben. Permisos conserva su "+ Nuevo" como link de página completa (no modal — el form de un permiso no cabe cómodo en un modal) sobrescribiendo ese bloque. También se amplió `is_filtered` en la vista para que reconozca sus propios filtros (estado/fechas), no solo `q`/`is_active`. 262 tests (operations+registry+maintenance+compliance, cubre a todos los módulos que usan la plantilla base) verdes — confirma que el cambio aditivo no rompió nada en otro módulo. Verificado en demo: búsqueda en vivo vía HTMX filtra correctamente con las columnas propias, filtro de estado funciona (mensaje "Ningún registro coincide con los filtros actuales" al filtrar sin resultados), exportar CSV y "+ Nuevo" con el comportamiento de siempre. | `templates/generic/list.html`, `templates/operations/permission_list.html`, `templates/operations/_permission_rows.html`, `apps/operations/views.py` |
| LV-54 | ✅ | P3 | **Hecho 2026-08-04** (encontrado al verificar LV-49; cierre de pendientes previo al 3er deploy): `ComplianceReportMixin.report_for()` rompía con `ValidationError` (500) si `doc_type`/`cost_center` en la URL no era un UUID válido (bookmark viejo, autofill, un bot probando query strings) — cualquier otro tipo de discordancia (UUID válido pero inexistente, otro tenant, archivado) ya se trataba como "sin filtro", solo este caso rompía la página. Fix: `_lookup_by_pk()` envuelve el `.filter(pk=...).first()` en un try/except. Test parametrizado nuevo para ambos campos. 105 tests de compliance verdes; verificado en demo: `?doc_type=1` ahora renderiza el reporte normal en vez de la página de error. | `apps/compliance/report_views.py`, `apps/compliance/test_reports.py` |
| LV-55 | ✅ | P2 | **Hecho 2026-08-04** (pedido del usuario tras el 3er deploy: notó que "Seguimiento de alertas" no tenía entrada propia en el menú lateral, solo se llegaba por URL directa o el botón "Crear tarea" de una alerta). Reabierto el enlace de LV-7 (oculto desde 2026-07-30) y ubicado dentro del grupo **Cumplimiento**, justo debajo de "Alertas" (no como sección propia "Follow-up" separada) — el usuario confirmó esa ubicación porque el tablero es hoy el mecanismo de seguimiento/acción correctiva de las alertas (LV-45/46/48), no un Kanban genérico aparte. Mismo msgid `"Action plan"` (ya resuelve a "Seguimiento de alertas" desde LV-48), clase `nav-compliance` para heredar el color de grupo. De paso, a pedido del usuario, se quitó la pestaña **"Vista de calendario"** del tablero (enlazaba a `/calendar/?types=task`) por ser redundante con el Calendario de la app, que ya existe. 275 tests (core+workboard) + suite completa 639/639 verdes. Verificado en el demo: el enlace aparece bajo Alertas con el badge de conteo, el tablero ya no ofrece la pestaña de calendario. | `templates/base.html`, `templates/workboard/kanban.html` |
| LV-56 | ✅ | P1 | **Hecho 2026-08-04** (pedido del usuario con captura del form del CC: "el nombre del administrador de contrato es obligatorio siempre"). Aclarado con el usuario: el nombre del administrador **no depende** del "Tipo de responsable" elegido — es un campo base siempre exigido, y "Tipo de responsable" pasa a ser una distinción aparte y opcional ("¿el contacto del día a día es distinto del administrador?"). Antes era el único de los 3 campos condicionales sin validación (Operador/Externo ya la tenían desde LV-34). Fix: `CostCenterForm.clean()` exige `responsible` sin condicionar al `rtype`; `responsible_type` reordenado después del nombre del administrador en el form (antes iba primero) y su choice "Administrador" renombrada a "El mismo administrador" + help_text aclaratorio; JS (`app.js`) deja de ocultar `div_id_responsible` con el toggle — siempre visible. Sin migración (`responsible` ya era `blank=True`; validación a nivel de formulario, no de modelo — la importación CSV de CC sigue sin pedirlo, no pasa por este form). 4 tests nuevos + 124 de registry verdes. | `apps/registry/forms.py`, `static/js/app.js`, `templates/registry/_costcenter_form_fields.html` |
| LV-57 | ✅ | P2 | **Hecho 2026-08-04** (pedido del usuario con 4 capturas — Centros de costo, Aeronaves, Operadores, Habilitaciones: "son todas distintas… normalizar cómo se muestran, mismo estilo para todas… aprovechar el espacio". **Diseño hecho con Opus 5**; continúa LV-32, que quedó parcial). Diagnóstico: las 4 ya compartían el esqueleto (`generic/list.html` + partial HTMX) — lo que divergía era el interior de la celda y, sobre todo, que la tabla no declaraba anchos, así que la columna con el texto más largo se quedaba con el espacio. **Anatomía única de fila: `IDENTIDAD \| ATRIBUTOS \| ESTADO \| ACCIÓN`.** (1) El bloque de identidad de **dos líneas** (que sólo tenía Aeronaves, la lista que el usuario percibía mejor) se generaliza a las 4 y pasa a la primera columna: código+nombre (CC), matrícula+modelo·fabricante (Aeronaves), nombre+RUT (Operadores/Habilitaciones) — eso **libera una columna** en 3 de las 4 listas. (2) Anchos por `<colgroup>` + `table-layout:fixed`, vía **cambio aditivo** en `generic/list.html` (bloques nuevos `list_colgroup`/`list_table_class`, **vacíos por defecto** → las otras 9 listas renderizan byte por byte igual; verificado en browser: siguen en `layout:auto`, sin colgroup). Las 4 fijan igual primaria (26%) y acción (110px) — mismo ancla y mismo botón en la misma posición en las 4 pantallas — y cada una deja **una** columna sin ancho que absorbe el sobrante, así los porcentajes no tienen que sumar exacto pese al distinto número de columnas. (3) Numéricos a la derecha con `tabular-nums` (antes flotaban a la izquierda de una franja ancha: el "espacio muerto" que reportó el usuario) y el `0` en gris, como estado y no como dato. (4) **NOTAS se elimina como columna** de CC (campo genérico de `BaseModel`, "—" en casi todas las filas, ~15% del ancho, requería un `style="max-width"` inline): las filas con nota la marcan con un glifo + tooltip junto al código y el texto completo sigue en la ficha. (5) **Habilitaciones** (desperdiciaba ~50% del ancho con sólo 2 columnas) suma Centro de costo y Vence credencial — sigue operator-centric (LV-14), pero la fila *es* un operador, así que sus atributos son columnas legítimas; ahora se lee como "la lista de Operadores enfocada en equipos" y permite ver "habilitado en 4 equipos **pero credencial vencida**" sin saltar entre dos listas (requirió `select_related("cost_center")` en `QualificationList.get_queryset`, si no era 1 query por fila). (6) **Verbo único "Editar"** en las 4 (Habilitaciones decía "Ver operador"); el nombre sigue enlazando al detalle, misma convención que el resto. Gotcha resuelto: la regla LV-D7 `.table td:first-child { white-space: nowrap }` rompía la primaria de dos líneas → acotada a `:not(.table-normalized)`, y dentro del patrón nuevo el nowrap aplica sólo a la línea del ancla. Decisiones (4), (1-RUT) y (6) confirmadas con el usuario antes de implementar. 653/653 verdes; verificado en browser: anchos computados correctos en las 4, listas no normalizadas sin cambios, swap HTMX conserva el colgroup (vive en la plantilla completa, no en el partial), contraste del subtítulo ≈8:1 oscuro / ≈7:1 claro (token `--ac-text-secondary` ya validado), y en móvil la tabla scrollea dentro de su contenedor sin desbordar el body. | `static/css/app.css`, `templates/generic/list.html`, `templates/registry/{costcenter,aircraft,operator,qualification}_list.html` + sus 4 partials de filas, `apps/registry/views.py` |
| LV-58 | ✅ | P3 | **Hecho 2026-08-04** (pedido del usuario tras ver LV-57 desplegado, con captura: "centro de costo sigue teniendo un gran espacio… podemos poner ahí el nombre del responsable"). La columna del administrador de contrato rara vez llena su ancho sola; cuando el contacto del día a día (LV-34) es distinto del administrador —un operador del padrón o un contacto externo— esa info no se mostraba en ningún lado de la lista. Nueva property `CostCenter.day_to_day_contact` (operador si `responsible_operator`, si no `responsible_contact_name`, vacío si el administrador ya cubre el rol) mostrada como subtítulo bajo el nombre del administrador (mismo patrón `table-primary-value`/`table-primary-sub` de LV-57), solo cuando hay algo que agregar. `CostCenterList.get_queryset` suma `select_related("responsible_operator")` para no costar una query por fila. 3 tests nuevos (con operador, con externo, y que una fila sin contacto adicional no muestre la etiqueta suelta); 653+ suite verde. | `apps/registry/models.py`, `apps/registry/views.py`, `templates/registry/_costcenter_rows.html` |
| LV-62 | ✅ | P2 | **Hecho 2026-08-04** (pedido del usuario tras notar "Flight Records" en inglés en el modal de Registros de vuelo; pidió además "buscar traducir lo que falte"). Causa: `OList`/`WList`/`MList`/`ComplianceList` arman el título de cada lista con `_(model._meta.verbose_name_plural.title())` — un `.title()` aplicado **antes** del `_()`, así que lo que realmente busca en el catálogo es la versión en Title Case, no el msgid en minúscula que ya existía. Auditoría completa (test temporal que pegó las 21 páginas de lista como usuario en español, listado y borrado): además de "Flight Records" aparecían **"Alert Rules"**, **"Document Types"**, **"Kanban Boards"**, **"Kanban Labels"** en inglés puro, y **"Registros De Mantenimiento"**/**"Tipos De Habilitación"** en español pero con Title Case inconsistente con el resto de la app. Fix: 7 msgids nuevos con la variante Title Case exacta que se busca en runtime, apuntando al texto correcto ya usado en otras partes de la app ("Tableros"/"Etiquetas" ya existían para "Manage boards"/"Manage labels"; "Reglas de alerta"/"Tipos de documento" ya existían en minúscula). Sin cambio de código, solo catálogo — recompilado el `.mo`. Verificado con el mismo test de auditoría: las 21 páginas ya muestran español correcto y consistente. | `locale/es/LC_MESSAGES/django.po` |
| LV-59 | ✅ | P3 | **Parcial, hecho 2026-08-04 (opción (a)+(b) elegida por el usuario entre 3; diagnóstico y diseño con Opus 5).** Vuelos era la única lista del área todavía en el patrón genérico. Fix: `FlightRecordList` deja de construirse con `type(...)` dinámico y pasa a una clase normal con `template_name`/`htmx_template_name` propios (`record_list.html` + `_record_rows.html`, patrón LV-57: columna de identidad, `select_related` para evitar N+1); columnas reales **Fecha / Permiso de vuelo / Piloto / Aeronaves / Duración**, con el permiso enlazado a su ficha. Nueva property `FlightRecord.duration`/`duration_display` ("1h 30min"): `departure_time`/`arrival_time` se guardaban pero nunca se restaban en ninguna vista; el formulario rechaza `arrival <= departure` pero eso no es una garantía del modelo (un registro por fixture/admin no la tiene), así que una llegada no posterior a la salida se trata como vuelo que cruzó medianoche, no como duración negativa. 8 tests nuevos (duración parametrizada incl. cruce de medianoche, columnas reales, HTMX conserva sus columnas); 31 de operations + suite completa verdes. Verificado en el demo: título ya en español (LV-62), columnas y duración correctas, "+ Nuevo" sigue abriendo el modal sin cambios.

**Opción (c) — revisada 2026-08-05, resuelta sin fusionar módulos.** La pregunta era si Vuelos debería vivir sobre todo como pestaña del permiso en vez de módulo de primer nivel. Al revisarla: (1) la ficha del permiso **ya tiene** su sección "Registros de vuelo" con "+ Agregar registro", que prellena permiso/piloto/aeronave (T5.5) — el camino natural ya existe y no cambió; (2) LV-61 ya movió Vuelos al grupo **VUELO** del menú, justo después de Permisos — la contigüidad que pedía esta opción ya quedó resuelta en la navegación, sin tocar el módulo; (3) la lista global SÍ tiene valor propio real (a diferencia de "Documentos" en LV-D8, que se ocultó porque su información ya vivía repartida por ficha): exportar CSV de todos los vuelos, o buscar uno sin recordar bajo qué permiso quedó, son casos de uso reales que fusionar el módulo habría perdido. **Lo que sí encontró la revisión**: el desplegable "Permiso de vuelo" del formulario no tenía `queryset` propio — mostraba **todos** los permisos alguna vez creados (activos o archivados), sin ordenar, el mismo problema de fondo que motivó la opción (c) pero concreto y acotado. Fix: `FlightRecordForm.__init__` ahora filtra `is_active=True` y ordena por `-valid_from`, mismo patrón que `GeoPlanImportForm` (LV-50/60). 1 test nuevo; 669 de la suite completa verdes. Verificado en demo: el desplegable pasó de mostrar 3+ permisos sin filtrar a solo los activos, más recientes primero. **LV-59 queda completamente cerrado.** | `apps/operations/models.py`, `apps/operations/views.py`, `apps/operations/forms.py`, `templates/operations/record_list.html`, `templates/operations/_record_rows.html` |
| LV-64 | ✅ | P1 | **Hecho 2026-08-05** (pedido del usuario, subiendo un PDF real de la DGAC — "Autorización de Operación RPA" N° 6031, CC691 — al elegir "Tipo de documento": *"son dos cosas, una es la carta de permiso de la DGAC y lo otro es el permiso de vuelo de la DGAC aprobada"*). El catálogo solo modelaba **un** documento DGAC ("Autorización DGAC (carta de permiso)", `dgac-flight-permit`) cuando en la operación real hay **dos**: la carta que se presenta *a* la DGAC como parte de la solicitud, y la autorización firmada y foliada que la DGAC devuelve *ya aprobada* (justo el PDF que trajo el usuario, con rango de vigencia, operadores y firma electrónica). Fix: nuevo `DocumentType` `dgac-rpa-operation-authorization` ("Autorización de Operación RPA (DGAC aprobada)") en `seed_document_types` (10 tipos, antes 9) — ambos tipos quedan visibles y archivables por separado, ninguno se elimina. La regla de aprobación de LV-51 (`FlightPermissionApprove`) se movió para exigir el tipo **nuevo**, no la carta — decisión explícita del usuario: solo el PDF firmado certifica una aprobación real, la carta sola sigue sin bastar. Test nuevo que confirma justo eso (adjuntar solo la carta no permite aprobar). 3 tests nuevos + 138 de operations/compliance + suite completa 670 verdes. Verificado en el demo: el nuevo tipo aparece en el desplegable, y aprobar sin él muestra el mensaje de error actualizado. **Pendiente en el deploy**: re-correr `seed_document_types` en `p340` tras el `git pull` (mismo gotcha de LV-45/`init_dgac_board` — es idempotente pero no se re-ejecuta solo). | `apps/compliance/management/commands/seed_document_types.py`, `apps/operations/views.py`, `apps/operations/tests.py`, `apps/compliance/tests.py` |
| LV-65 | ⬜ | P3 | **Pendiente** (pedido del usuario con captura del formulario "Nuevo: Registro de mantenimiento"): el desplegable "Aeronaves" solo muestra la matrícula (`RPA-XXXX`) — con ~18 aeronaves de matrículas parecidas es difícil distinguir cuál es cuál sin abrir cada una. Causa confirmada: el `ModelChoiceField` usa `Aircraft.__str__`, que solo devuelve `self.registration` (línea 178 de `registry/models.py`) — no hay `label_from_instance` propio en `MaintenanceRecordForm`. Sumar modelo y número de serie para verlas más fácil. **No implementado** — falta acordar el formato exacto (¿"RPA-4025 · Mavic 3 Enterprise" en el mismo option vía `label_from_instance`, sin tocar `__str__` global que usan otras vistas?) y si aplica solo a este form o también a otros selectores de aeronave (permiso, asignaciones). | `apps/maintenance/forms.py::MaintenanceRecordForm` |
| — | ✅ | P1 | **Higiene de calidad — 2026-08-05** (auditoría externa de Codex, verificada contra `main` antes de actuar). Dos hallazgos reales: (1) **el CI de GitHub llevaba días en rojo** (`ruff check`/`ruff format --check` corren en `ci.yml:26-27`, pero esta sesión venía verificando solo con `pytest` localmente) — 2 `F841` (variables sin usar, introducidas en LV-46 y en un test de LV-64) y 23 archivos sin formatear. Corregidas las 2 variables (`maintenance/views.py`, `operations/tests.py`) y aplicado `ruff format .`. `ruff check`/`format --check` verdes, 670/670 verde. **Lección**: cerrar cada ventana corriendo Ruff, no solo pytest — el hazard ya estaba anotado en la memoria del repo y se repitió igual. (2) Confirmado (no corregido aún, ver LV-63): el bug móvil crítico que reportó la auditoría era real. | `apps/maintenance/views.py`, `apps/operations/tests.py`, 23 archivos de formato |
| LV-63 | ✅ | P1 | **Hecho 2026-08-05** (auditoría externa de Codex, verificada y diseñada con Opus 5): a 390px de ancho el contenido quedaba comprimido a ~94px con scroll horizontal — crítico, afecta a cualquier persona que abra la app desde el celular. Causa raíz: `app.css` tenía **dos generaciones de la regla `.sidebar`** con la misma especificidad (0,1,0) — una base sin `@media` (línea ~719, del pase de tokens de diseño) y el bloque móvil (`@media max-width:768px`, línea ~410). Al tener igual especificidad, gana la que aparece **después** en el archivo — y la base (sin media query) quedaba después, pisando `position:fixed`/`width`/`transition` del bloque móvil **en cualquier viewport**, siempre. El `transform: translateX(-105%)` sobrevivía (la base no lo declaraba), así que el sidebar se veía desplazado fuera de pantalla **sin liberar su pista flex de 248px** — de ahí el hueco vacío y la compresión. Mismo patrón que el hazard R.10 ya documentado (dos generaciones de tokens apiladas), pero en la geometría del layout, no en colores. Fix: **fusionadas** ambas reglas en una sola base; la transición de tema (antes una regla aparte que solo cubría background/color/border/box-shadow) ahora incluye `transform`, así que el drawer móvil también **anima** al abrir/cerrar (no lo hacía antes tampoco). Dos bugs menores encontrados de paso: `main { padding: 1rem !important }` era **inerte** (perdía por especificidad contra `.p-4` de Bootstrap, ambos `!important`) — corregido a `#main-content` (gana por id); y `.sidebar.is-collapsed` dejaba el drawer móvil en 72px con etiquetas visibles si se colapsaba en desktop y luego se achicaba la ventana sin recargar — corregido escopando todo el modo colapsado a `@media (min-width:769px)` (es exclusivamente de escritorio; `app.js` nunca lo activa por debajo de 769px) y borrando las contra-reglas que intentaban deshacerlo mal. Sin tests (no hay suite de CSS); verificado en el demo con geometría real (`getBoundingClientRect`, no solo `getComputedStyle`, que mostró lecturas inconsistentes por un problema de caché de hoja de estilos en el navegador de pruebas — mismo patrón ya documentado con `<script src>`, resuelto reemplazando el `<link>` en vez de reasignar su `href`): a 375px `mainLeft` pasó de 248 (comprimido) a 0, sin scroll horizontal (`bodyScrollWidth === clientWidth`); en escritorio + oscuro el colapso y la sombra siguen correctos. | `static/css/app.css` |
| LV-60 | ✅ | P2 | **Hecho 2026-08-04** (pedido del usuario con captura de "Importar KMZ/KML": *"no tiene sentido linkear con un nuevo título un permiso de vuelo que ya existe, estos deben estar unidos… ahora es como si fueran aparte"*. **Diseño con Opus 5**, en conjunto con LV-61). Un plan importado contra un permiso no es un registro aparte que lo referencia: **es el área de vuelo de ese permiso**. Pedir un título nuevo y volver a elegir el centro de costo hacía que dos mitades de una misma solicitud parecieran cosas sin relación. (1) **Título opcional y autogenerado** como `{permiso o CC} · {nombre del archivo}` — mismo patrón que LV-2 ya estableció para los títulos de `Document`; el nombre del archivo distingue dos planes del mismo permiso (el vínculo es 1:N). (2) **Centro de costo heredado**: `get_initial` lo prellena desde el permiso (`?flight_permission=`, ruta de LV-50) y `clean()` lo deriva si viene vacío. (3) **Hallazgo de integridad, no solo UX**: nada impedía que un plan quedara en un centro de costo **distinto** al del permiso que dice cubrir — dato incoherente que ahora se rechaza con un error que nombra el CC esperado. El lookup del permiso va protegido contra un `?flight_permission=` malformado (mismo guard de LV-54: query string basura deja el campo vacío, no rompe con 500). 7 tests nuevos (herencia de título/CC, título explícito respetado, CC discordante rechazado, sin permiso ni CC rechazado, id malformado); 99 de geo + suite completa 660 verdes. Verificado en el demo: llegando desde el permiso REV-P1 el CC aparece ya puesto y el título queda opcional con su ayuda en español. **La parte "mover geo a una pestaña del permiso" NO se hizo** — en su lugar LV-61 lo resolvió en la navegación (Planificación geoespacial pasó al grupo VUELO, justo bajo Permisos), que da la contigüidad pedida sin romper el módulo ni su API/versionado. | `apps/geo/forms.py`, `apps/geo/views.py`, `apps/geo/test_views.py` |
| LV-61 | ✅ | P3 | **Hecho 2026-08-04** (pedido del usuario con captura del menú completo: *"mejorar la distribución y el uso del panel lateral con la estrategia de las operaciones y los nombres… mantenerlos como flujo directo de lo que se va usando"*. **Diseño con Opus 5**; supersede el agrupamiento de LV-13a). Diagnóstico: **el menú estaba ordenado por modelo de datos, no por uso** — lo que se configura una vez (padrón, asignaciones) ocupaba los dos primeros grupos y el trabajo diario (permisos, alertas) quedaba enterrado debajo. Además (a) "Planificación" mezclaba dotar un contrato de recursos (acto administrativo) con planificar el área de un vuelo (parte de la solicitud del permiso, LV-60); (b) el ciclo del permiso estaba repartido en 4 grupos; (c) **tres cosas distintas se llamaban "Registros"** (Mantenimiento › Registros, Cumplimiento › Registros operacionales, y los vuelos son registros de vuelo). Nueva estructura, elegida por el usuario entre 2 opciones: **VUELO** (Permisos → Planificación geoespacial → Vuelos → Calendario: el ciclo en el orden en que ocurre) · **CUMPLIMIENTO** · **MANTENIMIENTO** · **PADRÓN** (todo lo de configurar, al final). Mantenimiento › "Registros" renombrado a **"Mantenciones"** (también elegido por el usuario) para deshacer la colisión. Gotcha resuelto: `msgid "Registry"` ya significaba "Registro" (eyebrow de la importación de CC), así que el rótulo del grupo usa `{% translate "Registry" context "sidebar group" %}` → "Padrón" (solución idiomática de Django para un mismo literal con dos traducciones, en vez de duplicar el msgid — lo que además habría roto `compilemessages`, ver el hazard de LV-36). **De paso se corrigió el guard `test_catalog_has_no_duplicate_msgids`**: parseaba el `.po` leyendo solo el `msgid`, así que veía la entrada contextual como duplicada. En gettext la unicidad es por el par `(msgctxt, msgid)` — confirmado con `msgfmt --check`, que sale con exit 0 y 797 mensajes sobre este catálogo. El guard ahora usa esa clave; verificado empíricamente que **sigue cazando un duplicado real** (se agregó uno falso a propósito, falló como debe, y se quitó). Verificado en el demo: los 4 grupos en orden, y el resaltado "activo" sigue correcto en geo/mantenimiento/permisos/padrón (las rutas no cambiaron, solo su posición). | `templates/base.html`, `django.po`/`.mo` |
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
| B3.1 | ✅ | P2 | **Hecho 2026-08-07.** Alternativa más barata elegida: filtro rápido por operador (existía en el backend de `KanbanTaskListView` pero nunca se mostraba en `task_list.html`) + `group_by=operator\|cost_center` con subcabeceras, en vez de swimlanes en el tablero. `itertools.groupby` sobre la página ya ordenada por el campo de agrupación. | `apps/workboard/views.py`, `templates/workboard/task_list.html` |
| B3.2 | ✅ | P2 | **Hecho 2026-08-07.** No existía vínculo User↔Operator; decisión del usuario: FK explícita (`Operator.user`, opcional, se asigna en el form/admin del operador) en vez de match automático por email — mismo criterio que el precedente de `CostCenter.responsible_operator`. Botón "Mi trabajo" en tablero y lista (oculto si el usuario no tiene operador vinculado), reutiliza el filtro por operador de B3.1. | `apps/registry/models.py`, `apps/workboard/selectors.py`, `templates/workboard/kanban.html`, `templates/workboard/task_list.html` |
| B3.3 | ✅ | P2 | **Hecho 2026-08-04** (retomado a pedido del usuario, ahora que el tablero es "Seguimiento de alertas"). Nuevo `KanbanTask.urgency_bucket(today)` — mismos límites vencido/≤7/≤15/≤30 días que el reporte de cumplimiento (`apps/compliance/reports.py`), para que "urgente" signifique lo mismo en toda la app. La tarjeta agrega una etiqueta traducida propia por bucket ("Vence en 7 días", etc., msgids ya existentes en el catálogo) además del color/negrita (`text-warning-emphasis`/`fw-bold`/`fw-semibold` de Bootstrap, ya con soporte de tema oscuro vía `data-bs-theme`) — la accesibilidad no depende solo del color. 10 tests nuevos (bucket parametrizado + render). | `apps/workboard/models.py`, `templates/workboard/_card.html`, `apps/workboard/templatetags/workboard_extras.py` |
| B3.4 | ✅ | P3 | **Hecho 2026-08-04** (junto con B3.3). Contador de vencidas junto al total en la cabecera de cada columna (`⚠ N`), calculado en `build_stage_data()` sin queries extra (ya itera las tareas de la etapa). Bug encontrado y corregido durante la verificación: el badge no se veía rojo porque `.kanban-count-overdue` compartía especificidad CSS con una redeclaración posterior de `.kanban-count` (paleta de tokens) y perdía por orden de aparición — solucionado con selector compuesto `.kanban-count.kanban-count-overdue`. 2 tests nuevos. Verificado en demo con una tarea vencida real (antes/después del fix de especificidad). | `apps/workboard/selectors.py`, `templates/workboard/_column.html`, `templates/workboard/_board.html`, `static/css/app.css` |
| B3.5 | ✅ | P3 | **Hecho 2026-08-07.** `wip_limit` opcional en `KanbanStage` (editable en `/admin/` por ahora — la app no tiene vista de edición de etapas). El contador de la columna pasa a ámbar y muestra "cuenta/límite" al superarse, sin bloquear el drop (`MoveTaskView`/`QuickTaskCreate` intactos). Bug propio encontrado y corregido antes de comitear: `{% if stage.wip_limit %}` trataba un límite de 0 como "sin límite" y ocultaba la fracción justo en ese caso. | `apps/workboard/models.py`, `apps/workboard/selectors.py`, `templates/workboard/_column.html`, `static/css/app.css` |

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

## REVISIÓN POST-AUDITORÍA (2026-08-07) — bloques R1-R8 y X

> Origen: revisión en vivo del usuario (19 capturas), guía de auditoría ISO y la
> aparición de AeroLink. Ver "Prioridades post-auditoría" al inicio para el orden.
> Los ítems marcados **[bug]** no los reportó el usuario: salieron de cruzar su
> feedback con el código y son, varios, peores que los reportados.

### BLOQUE R1 — Bugs que ocultan información de cumplimiento `P0`

| ID | Est. | Tarea | Archivos |
|---|:--:|---|---|
| R1.1 | ⬜ | **[bug] El calendario oculta las vigencias DGAC y JAC en su vista por defecto.** `typeQuery()` expande `'all'` a 7 tipos literales y omite `operator_credential` y `aircraft_insurance`; el selector arranca en "Todos los eventos", así que un seguro que vence mañana **no se ve**. Arreglar la **causa**: derivar la lista desde el servidor (los 9 tipos ya están en `CALENDAR_EVENT_PERMISSIONS`) en vez de repetirla en el JS, para que no vuelva a desincronizarse. | `static/js/calendar.js:19-23`, `templates/core/calendar.html`, `apps/core/views.py:286-298` |
| R1.2 | ⬜ | **[bug]** Permiso sin folio renderiza el literal `"None"` en el calendario. Lo resuelve R2.2; dejar además una guarda explícita. | `apps/core/views.py:491-503` |
| R1.3 | ⬜ | Panel "Próximos vencimientos": la etiqueta es el mismo gris para las 5 fuentes y no hay noción de urgencia — un vencimiento de mañana se ve igual que uno de un mes. Reutilizar los buckets **ya existentes** (`KanbanTask.urgency_bucket` / `compliance/reports.py`: vencido/≤7/≤15/≤30), mostrar "faltan N días", y hacer clickeable la tarjeta KPI "Vence en 30 días" (es la única del grid que no lo es). | `apps/dashboard/views.py:18-110`, `templates/dashboard/index.html:41-44,97-110` |
| R1.4 | ✅ | **Investigado 2026-08-07, no reproducible con el código actual.** `_card.html:28` usa `{{ task.due_date\|date:"M j" }}`, que pasa por `django.utils.dateformat` — traducido, no un `strftime` crudo (se auditó todo `apps/` buscando `%b`/`%B` directos: cero resultados). Verificado en vivo contra la demo (fecha en agosto) y en test sin `override()` de idioma (usa el default del proyecto, `LANGUAGE_CODE="es"`): ambos muestran "Ago 5", no "Aug 5". `LocaleMiddleware` está bien ubicado en `MIDDLEWARE` y no hay ningún `translation.activate()`/`deactivate()` sin scope que pudiera filtrar estado entre requests. Conclusión más probable: la captura del usuario corresponde a una sesión con idioma de navegador o cookie en inglés en ese momento, no a un defecto de código. **Test de regresión agregado** (`test_kanban_card_due_date_month_is_localized`) para que, si esto reaparece, falle un test en vez de descubrirse otra vez en producción. | `apps/workboard/tests.py` |
| R1.5 | ✅ | **Investigado 2026-08-07, no reproducible.** Es un `<a href="{% url 'geo-plan-list' %}">` plano, sin `hx-*` ni `data-history-back`, así que no depende de JS para navegar. Probado en el navegador contra la demo en los tres estados relevantes de la ficha — vista simple, edición activa, y con "Comparar" versiones abierto — sin ningún error de consola ni fallo de navegación en ninguno. Hipótesis más probable: algo transitorio de la sesión del usuario en el momento de la captura (no un defecto de código reproducible). Si vuelve a pasar, hace falta el estado exacto del plan (¿cuántas versiones, `flight_permission` vinculado, estado del borrador?) para reproducirlo. | `templates/geo/plan_detail.html:34` |

**Aceptación del bloque:** un seguro que vence mañana aparece en el calendario en la
vista por defecto, y en el panel se distingue de uno que vence en un mes sin leer la fecha.

### BLOQUE R2 — Permiso de vuelo: numeración, edición y flujo `P0`

Núcleo del feedback (4 de las 19 capturas). **Causa raíz común:** `FlightPermission.__str__`
cae en `f"{status} · {purpose[:30]}"` cuando no hay folio (`apps/operations/models.py:56-61`),
y ese texto se filtra a la columna NÚMERO, a los títulos de planes geo, a los eventos del
calendario y al título de la ficha. Un solo arreglo de raíz corrige las cuatro pantallas.

| ID | Est. | Tarea |
|---|:--:|---|
| R2.1 | ✅ | **Hecho 2026-08-07.** `FlightPermissionUpdate` (local, mismo patrón que `RegistryUpdate`; no comparte clase porque esta app usa `permission-list`/`permission-update`, no `flightpermission-*`) + ruta `permission-update` + botón "Editar" en la ficha, visible solo con `operations.change_flightpermission`. Vuelve a la lista al guardar, igual que `RegistryUpdate`/`ComplianceUpdate`. Reutiliza `FlightPermissionForm` sin cambios — la validez del correlativo/folio queda para R2.2/R2.3. Verificado en vivo (demo local): edición completa vía POST directo (el clic en "Guardar" no llegó a probarse en el navegador embebido por una limitación del panel de vista previa, no del código) y con los tests nuevos. | `apps/operations/views.py`, `apps/operations/urls.py`, `templates/operations/permission_detail.html` |
| R2.2 | ✅ | **Hecho 2026-08-10.** `FlightPermission.internal_folio` (`JEJ-2026-001`, correlativo anual), asignado en `save()` dentro de una transacción con `select_for_update()` sobre las filas del año — no `count()+1`. Backfill corrido primero contra la copia restaurada del respaldo (2 permisos reales: `JEJ-2026-001`/`JEJ-2026-002`), luego migración `0014` con `AddField(null=True)` → `RunPython` backfill → `AlterField(null=False)`. Folio DGAC (`permission_number`) sigue opcional; sin él, la ficha y la lista muestran "En proceso". | `apps/operations/models.py`, migración `0014`
| R2.3 | ✅ | **Hecho 2026-08-10.** `__str__` devuelve `internal_folio` → cascada automática a lista, calendario, panel de vencimientos, ficha de centro de costo y título de plan geo (todos renderizan `{{ permission }}` o el `__str__` del modelo). `purpose` volvió a ser dato, ya no identificador de respaldo. | `apps/operations/models.py`, `apps/core/views.py`, `apps/dashboard/views.py`
| R2.4 | ✅ | **Hecho 2026-08-07.** El guard del PDF DGAC (`dgac-rpa-operation-authorization`, actual y activo) que ya protegía `approved` ahora también protege `completed` — extraído a `RequireDgacPermitPdfMixin` para no duplicar la consulta. Antes un permiso podía llegar a `completed` sin el PDF si nunca se validó al aprobar, o si el documento se reemplazó/archivó después. | `apps/operations/views.py`
| R2.5 | ✅ | **Hecho 2026-08-07.** (a) Un solo desplegable + campo de notas + botón "Aplicar" en vez de un botón de color por transición (`permission-status.js`, degrada sin JS al primer destino). (b) Notas ya viajaban al modelo (`_transition_notes`) pero la plantilla nunca las mostraba ni las pedía — ahora hay un campo y una columna "Notas" en el historial. (c) **[bug real, reproducido en vivo]** "← Volver" usaba `data-history-back`, y *toda* transición (éxito o error) redirige a la misma URL — cada redirect empuja una entrada nueva al historial, así que `history.back()` caía en un render anterior de la misma página: hacían falta **dos clics** para salir. Se reprodujo con Aprobar sin el PDF y se confirmó el arreglo con un clic. Mismo patrón encontrado y corregido en `maintenance/record_detail.html` y `operations/flightrecord_detail.html` (ambas con acciones que redirigen a sí mismas). (d) Bug adicional encontrado al verificar: `PermissionHistory.previous_status`/`new_status` no declaraban `choices`, así que el historial mostraba "requested"/"denied" en inglés crudo en vez de "Solicitado"/"Rechazado" — agregado `choices=FlightPermission.STATUS_CHOICES` (migración `0012`). | `apps/operations/views.py`, `apps/operations/models.py`, `templates/operations/permission_detail.html`, `templates/maintenance/record_detail.html`, `templates/operations/flightrecord_detail.html`, `static/js/permission-status.js` |
| R2.6 | ✅ | **Hecho 2026-08-07.** `FlightPermission.area_type` (poblado/no poblado/mixto), obligatorio en el formulario (create y update), sin exigencia documental adicional. Campo nulo a nivel de BD (`null=True`, migración `0013`) para no romper los permisos que ya existen sin este dato — la ficha muestra "—" para esos. Sin cambios en `search_fields`/columnas de lista (fuera del alcance de este ítem). | `apps/operations/models.py`, `apps/operations/forms.py`, `templates/operations/permission_detail.html`, migración `0013`
| R2.7 | ✅ | **Hecho 2026-08-10** (tras R3.1). `search_fields = ["internal_folio", "permission_number", "purpose_detail", "location"]` — el placeholder ya prometía número/propósito/ubicación, ahora los busca de verdad. 3 tests nuevos. |

### BLOQUE R3 — Estandarización transversal `P1` — antes de importar

| ID | Est. | Tarea |
|---|:--:|---|
| R3.1a | ✅ | **Hecho 2026-08-10.** `report_purpose_mapping` (solo lectura) corrido contra la copia restaurada del respaldo real. Congelado: solo **3 filas** con `purpose` en toda la base (2 `FlightPermission`, 1 `OperatorAssignment`) — las 3 mezclan más de un concepto (`"Fotogrametría - Fotos - Videos"`, `"Fotogrametría y videos"`, `"Audiovisual"`), ninguna calza limpio con un solo procedimiento. **Confirmado con el usuario 2026-08-10**: los 2 procedimientos SIGO son **"Fotogrametría"** y **"Videos"** (no "Videografía" — rechazado explícitamente por no calzar con el uso real). Mapa congelado en `apps/core/choices.py::PURPOSE_LEGACY_MAP`. | `apps/core/management/commands/report_purpose_mapping.py`
| R3.1 | ✅ | **Hecho 2026-08-10.** `purpose` (código, `apps/core/choices.py::PURPOSE_CHOICES` — lista de tuplas, no `TextChoices`, mismo criterio que el resto del repo) + `purpose_detail` (libre) + `purpose_legacy` (**inmutable**, mismo criterio que `CostCenter.responsible`) en `FlightPermission` (obligatorio) y `Assignment`/`OperatorAssignment`/`AircraftAssignment` (opcional, LV-17 ya lo decidió así). `CheckConstraint` **por modelo concreto** — se comprobó empíricamente que `Meta.constraints` en la clase abstracta `ResourceAssignment` **no se hereda** si la subclase declara su propio `Meta` sin subclasificar el del padre (`OperatorAssignment`/`AircraftAssignment` ya hacían esto para sus `indexes`), así que cada constraint vive en el `Meta` concreto. `clean()` en los 4 modelos exige `purpose_detail` cuando `purpose == "other"` — la constraint de BD es el guardia real (probado con un `.save()` que lo esquiva a propósito). Backfill de las 3 filas reales: las 3 quedaron en `other` con el texto original preservado en `purpose_detail` y `purpose_legacy`. Tocó los 5 formularios previstos (`OperatorBulkAssignForm` con su propio `clean()`, al no ser `ModelForm`), `services.bulk_assign_operators` (nuevo parámetro `purpose_detail`) y las 3 plantillas que mostraban `.purpose` crudo. 12 tests nuevos. | `apps/core/choices.py`, `apps/operations/models.py`, `apps/registry/models.py`, `apps/operations/forms.py`, `apps/registry/forms.py`, `apps/registry/services.py`, `apps/registry/views.py`, migraciones `operations/0015`, `registry/0026`
| R3.2 | ✅ | **Hecho 2026-08-07.** `CostCenterList`/`AircraftList`/`OperatorList` ahora ordenan explícitamente en vez de caer en el fallback `created_at` de `SearchMixin` (`apps/core/views.py:108`). CC: `order_by(Length("code"), "code")` — agrupa por cantidad de dígitos antes de alfabético, así una serie numérica con el mismo prefijo (CC1, CC2, ..., CC100, CC110) queda en orden correcto sin una función de regex/substring específica de motor de BD. Aeronaves por `registration`, operadores por `full_name`. | `apps/registry/views.py`
| R3.3 | ✅ | **Estados visibles — hecho 2026-08-07.** (a) el operador archivado ahora muestra una insignia "Archivado" y el botón cambia a "Restaurar" en vez de "Editar" (`_operator_rows.html`), igual que la tabla genérica ya hace para modelos sin partial propio. (b) **`CostCenter.contract_status`** (activo/cerrado), eje independiente de `is_active` — decisión de negocio 2026-08-07: un contrato cerrado no es un error/duplicado para archivar, sigue en la lista normal (atenuado, agrupado después de los activos vía `order_by("contract_status", ...)`; "active" < "closed" alfabético ya da ese orden). Opcional en el formulario (`blank=True`, default "active" en `clean()` si se omite) — cerrar un contrato es una acción ocasional sobre un registro existente, no un dato obligatorio al crear. (c) **investigado, ya estaba implementado** — `Aircraft.retired` ya se ve (columna "Status" en `aircraft_list.html`, insignia gris) y ya es editable (`AircraftForm` incluye `status`); solo faltaba el test de regresión, agregado. | `apps/registry/models.py`, `apps/registry/forms.py`, `apps/registry/views.py`, `templates/registry/_operator_rows.html`, `templates/registry/_costcenter_rows.html`, `templates/registry/_costcenter_form_fields.html`, migración `0025`

> **Conflicto de traducción resuelto:** los nombres de procedimiento son normativos y en
> español, pero `test_source_strings_are_written_in_english` falla si un string fuente
> lleva tilde. Solución: **msgid en inglés como clave, `msgstr` español como literal
> autoritativo** (`_("Photogrammetry Procedure")` → `"Procedimiento de Fotogrametría"`).
> La cita "DAN 137 Cap. J" va una vez en el `help_text`, no repetida en cada etiqueta.
> `"Other"` necesita `pgettext_lazy` (msgid probablemente ya usado, precedente LV-61).

### BLOQUE R4 — Repositorio documental `P1`

Fuente: `Z:\01-116 OPERACIONES_RPA_JEJ` — 79 archivos / 0.17 GB, 16 carpetas de aeronave
`CC{centro}-{serie}-{modelo}` con 5 subcarpetas fijas, más `DOCUMENTOS BASES`.
**`Z:` es de solo lectura: no se escribe, borra ni mueve nada ahí.**

| ID | Est. | Tarea |
|---|:--:|---|
| R4.1 | ✅ | **Importador `import_document_repository`, hecho 2026-08-10.** Por defecto **informa, no escribe**; se escribe solo con `--apply` (precedente del repo: `chapter1_import --apply`, `cleanup_documents --execute`). Se **niega** a aplicar si quedan filas bloqueantes (`REVIEW-NO-MATCH`/`REVIEW-NEEDS-ANTIVIRUS`/`REVIEW-UNKNOWN-SUBFOLDER`/`REVIEW-CONTENT-CHANGED`/`REVIEW-ANTIVIRUS-REJECTED`) — `REVIEW-SENSITIVE` (R4.5) es la única excepción a propósito, ver su fila. Lógica pura en `apps/compliance/repository_import.py` (testeable sin filesystem, `test_r4_repository_import.py`), IO real en `apps/compliance/management/commands/import_document_repository.py` (`test_r4_import_command.py`). **Corrido en modo informe contra `Z:` real** (copia descartable de la restauración, borrada después): de 73 archivos en las 16 carpetas de aeronave, 42 `OK`, 15 `REVIEW-NEEDS-ANTIVIRUS`, 5 `REVIEW-NO-MATCH`, 5 `REVIEW-SENSITIVE`, 5 `SKIP-FORMAT`, 1 `REVIEW-UNKNOWN-SUBFOLDER` — cuadra exacto con el conteo real de archivos. **Dos hallazgos reales durante esa corrida, no anticipados por el plan**: (a) una subcarpeta (`02.- Solicitud de Vuelos`) tiene a su vez una subcarpeta propia (`Junio-Agosto/`) — el primer intento la recorría con `iterdir()` y esos archivos desaparecían del informe sin ningún aviso, peor que cualquier `REVIEW-*`; (b) hay un archivo suelto en la raíz de una carpeta de aeronave (`CC738/Manual_Tecnico_...pdf`), fuera de las 5 subcarpetas fijas — no tiene convención de archivo, así que cae en el nuevo `REVIEW-UNKNOWN-SUBFOLDER` (bloqueante) en vez de perderse. **`--apply` no se corrió** — queda para cuando el usuario confirme el mapeo de `doc_type` por subcarpeta (ver R4.1a) y decida ejecutarlo él mismo, primero contra la copia local, nunca directo a producción. |
| R4.1a | 🔄 | **Calce por serial, sin difuso — normalización cerrada (X.1), calce funcionando, quedan 2 carpetas por corregir a mano en `Z:`.** De 16 aeronaves, **14 ya calzan exacto** por serial (las 2 de espacio las resolvió X.1; `RPA-2019` calza pese al CC distinto — el CC de la carpeta es solo informativo, no parte de la llave). **Siguen sin calzar 2** porque el nombre de carpeta en `Z:` todavía tiene el valor incorrecto que X.1 detectó: `RPA-4647` (carpeta `...246BOOD7WPK` con "OO", el valor correcto confirmado por el usuario es con ceros) y `RPA-4884` (carpeta `CC717-1582...`, el valor correcto confirmado es `1581`). **Nada de Levenshtein ni sustitución O↔0** — el importador los reporta como `REVIEW-NO-MATCH` con el hint `near:<matrícula>` (hay exactamente un candidato sin calce en el mismo CC en ambos casos) y no adivina. El usuario corrige los 2 nombres de carpeta en `Z:` por su cuenta; tras eso una nueva corrida calza las 16. `RPA-2198` (no está en `Z:`) y la carpeta `CC633/"M3E Revisión"` (sin aeronave, y vacía — 0 archivos, nada que revisar) siguen como se documentó. |
| R4.2 | ✅ | **Idempotencia y procedencia, hecho 2026-08-10.** `Document.content_sha256` y `Document.source_reference` (migración `0012_r4_document_provenance`, desplegada sola y primero, sin lógica de importador). El importador usa `source_reference` para detectar "ya importado" (`ALREADY-IMPORTED`, no bloqueante, no duplica) y compara `content_sha256` para detectar "mismo `source_reference` pero contenido distinto" (`REVIEW-CONTENT-CHANGED`, bloqueante) — cubre el caso real de **mismo nombre con contenido distinto** (`Poliza_0020099470-21147.pdf`, 110.176 B vs 107.152 B, confirmado en la corrida real). |
| R4.3 | ✅ | **`expiry_date` nunca se infiere — siempre `NULL`, hecho 2026-08-10.** El importador no toca `expiry_date` (queda `NULL` por defecto del modelo). Mismo criterio aplicado también a `issue_date` (obligatorio en el modelo, a diferencia de `expiry_date`): en vez de adivinar una fecha del nombre del archivo, se usa la fecha de la corrida de importación, con una nota explícita en `Document.notes` con la ruta de origen y la aclaración de que la fecha real del documento no está disponible sin abrirlo. |
| R4.4 | 🔄 | **Formatos, calce funcionando, antivirus todavía no configurado en ningún ambiente.** `.rar`/`.zip`/`.kmz` (`SKIP-FORMAT`) nunca se importan. `.msg` (17 en total: 15 puros + 2 que además son PII) exige antivirus configurado — hoy `DOCUMENTS_ANTIVIRUS_COMMAND` sigue vacío en todos los ambientes, así que los 15 quedan `REVIEW-NEEDS-ANTIVIRUS` (bloqueante) hasta que se configure uno. El importador **reutiliza `scan_uploaded_file`** (el mismo gate que ya usa el formulario web) vía un adaptador de ruta real a archivo, no una segunda implementación — probado con antivirus simulado (mock) en ambos sentidos (acepta / rechaza), pendiente probar contra un ClamAV real cuando exista uno configurado. |
| R4.5 | ✅ | **PII: no entra a AeroControl, hecho 2026-08-10 (decisión de negocio 2026-08-07).** `is_sensitive_filename()` detecta por nombre de archivo (palabra completa, sin acentos, singular y plural: cédula/cedulas, rut/ruts, comprobante/s, transferencia/s, escritura/s, notarial/es) — verificado contra los 5 archivos reales con PII en `Z:` (cédula de identidad, 2 comprobantes de transferencia/pago, una escritura pública, una carpeta de transferencias con el nombre de una persona en el propio nombre del archivo). Clasificados `REVIEW-SENSITIVE` y **excluidos de forma permanente**: es la única categoría `REVIEW-*` que no bloquea `--apply` — es una decisión ya tomada por política, no una pendiente por resolver. |
| R4.6 | ⬜ | **"Documentos de la empresa" como repositorio real** (hoy vacío y sin filtros, búsqueda ni categorías): AOC, normativas DAN, procedimientos y manuales, con categoría y vigencia. Las **normativas DAN se saltan** como `Document`: son PDF públicos de la DGAC y entrarían a los informes de cumplimiento de la empresa como si fueran evidencia propia. Sigue sin empezar — `import_document_repository` (R4.1) **no camina `DOCUMENTOS BASES`**, a propósito: es un problema de forma distinta (sin aeronave a la que atar el documento). |
| R4.7 | ⬜ | **Licencia RPA del operador**: columna que avisa cuándo falta el PDF. El mecanismo ya existe (GFK + tipo `dgac-credential`); falta la señal de "información incompleta". |
| R4.8 | 🔄 | Tipo de documento nuevo **"Aviso Mensual de No Operación"**, más `aoc-certificate` y `company-procedure` (para R4.6) siguen sin crear. **`maintenance-certificate`, `flight-request` e `incident-investigation-record` ya se agregaron a `seed_document_types`** (adelantados desde acá el 2026-08-10, R4.1 no podía clasificar las subcarpetas `02.-`/`03.-`/`04.-` de `Z:` sin ellos) — **gotcha de despliegue LV-45/LV-64 sigue vigente: correr `seed_document_types` a mano en `p340`** (pasa de 10 a 13 tipos). |

> **Dónde corre el importador — decidido 2026-08-07: localmente, contra una copia
> restaurada del respaldo de producción.** `Z:` es una unidad mapeada en la máquina
> Windows del usuario y `p340` (Ubuntu) no la ve, así que el import no puede correr en
> la VM.
>
> **Esta decisión resuelve dos problemas de una vez.** Traer el respaldo de `p340`,
> restaurarlo local y trabajar sobre esa copia **es exactamente el ensayo de
> restauración de respaldos** que lleva semanas siendo la prioridad #1 del tablero
> (`docs/dev/ubuntu-vm-deploy.md` → Parte H). Se ejecuta como parte de `R4` y se
> registra su resultado en `docs/backend-follow-up.md`. Si la restauración falla, eso
> **detiene todo el bloque** — y sería la mejor noticia posible, porque significaría
> haber descubierto un respaldo inservible antes de necesitarlo de verdad.
>
> Flujo: respaldo de `p340` → restaurar local → correr el importador contra `Z:` en
> modo informe → revisar → `--apply` sobre la copia local → verificar → recién ahí
> llevar el resultado a producción.

### BLOQUE R5 — Trazabilidad y ciclo de vida `P1-P2`

| ID | Est. | Tarea |
|---|:--:|---|
| R5.1 | ⬜ | **Mantenimiento con flujo real**: `enviado → en taller → finalizado → en tránsito → casa matriz`, ligado al historial del equipo y cruzado con alertas. Hoy los estados son planos y el formulario mínimo. El usuario lo marcó como *"crítico para el futuro"*. |
| R5.2 | ✅ | **[bug] Atribución de movimientos, hecho 2026-08-10.** `RegistryCreate`/`RegistryUpdate.form_valid()` ahora setean `form.instance._changed_by_user = self.request.user` antes de guardar — cubre las 2 vistas CRUD del padrón que no lo hacían (crear/editar `AircraftAssignment`, editar `OperatorAssignment`) **y de paso un tercer caso no listado originalmente**: editar la ubicación de una `Aircraft` (`track_aircraft_location`, OPS-3) tampoco atribuía autor. `bulk_assign_operators` seguía siendo el único de los 3 sitios previos; ahora son 3 vistas más los que sí atribuyen. |
| R5.3 | ✅ | **Movimientos de recursos, hecho 2026-08-10.** Columna `detail` visible en la lista y su nuevo partial htmx (`_resourcemovementlog_rows.html`). Búsqueda (`?q=`) sobre `detail`/nombre de CC origen-destino/usuario **y además por matrícula de aeronave o nombre de operador** — `resource_id` es un UUID sin FK, así que la búsqueda resuelve primero qué aeronaves/operadores calzan y los cruza por `(resource_kind, resource_id)`, mismo mecanismo para el **scoping por tenant** (no puede usar `TenantScopedQuerysetMixin` con un `tenant_path` simple, por la misma razón — sin FK que seguir). Exportación CSV vía `CsvExportMixin`, mismo patrón que el resto del padrón. |
| R5.4 | ✅ | **Ficha de aeronave como expediente, hecho 2026-08-10.** Documentos y movimientos ya estaban (OPS-6); se agregó **historial de mantenciones completadas** (separado de las abiertas de LV-26, que ya tenían su propia tabla con botones de acción — evita mostrar el mismo registro dos veces) y **horas de vuelo acumuladas**. `FlightRecord.duration` es una `@property` (no una columna), así que el agregado se suma en Python (`apps/operations/selectors.py: total_flight_duration` + `format_duration`, esta última también reusada por `duration_display` para no duplicar el formato "1h 05min"). **Mismo agregado que pide R7.1** (horas de vuelo, cláusula ISO 7.1.3) — implementado una sola vez, sirve a los dos. Verificado en vivo contra el demo con datos de prueba descartables (creados y borrados en la sesión). |
| R5.5 | ⬜ | Selector de aeronaves con modelo y serie, no solo matrícula (absorbe LV-65). |
| R5.6 | ⬜ | Asignación múltiple de **aeronaves**: existe `OperatorBulkAssign` para operadores, no hay equivalente para aeronaves. |
| R5.7 | ✅ | **Seguimiento del trámite de seguro JAC, hecho 2026-08-10.** `Aircraft.insurance_status` (`pending`/`active`, default `active`) — mismo patrón que `CostCenter.contract_status` (R3.3b): campo de estado nuevo junto a un dato existente, no lo reemplaza. `clean()` fuerza `"active"` en cuanto existe un `insurance_expiry` real, así el campo no puede quedar diciendo "en trámite" después de que la póliza ya llegó. Columna "Seguro" de la lista: `—` (sin nada pedido) → **"En trámite"** (`insurance_status="pending"`, sin fecha aún) → fecha vigente/atrasada (una vez que llega `insurance_expiry`, sin cambios). **Bug real encontrado probando contra el demo, no contra la copia de restauración**: la migración `0028` (X.1) fallaba con `IntegrityError` al correr contra datos con aeronaves realmente en blanco (el demo tiene 6; la copia de restauración no tenía ninguna, así que el bug quedó silencioso ahí) — el orden de sus 2 operaciones estaba mal (intentaba poner `NULL` en una columna que todavía era `NOT NULL`). Corregido a 3 pasos: nullable → limpiar datos → `unique=True`. |
| R5.8 | ⬜ | **[observación en vivo 2026-08-10, capturar antes de implementar]** El usuario ve la sección **"Habilitaciones"** (sidebar, `qualification-list`) como redundante con Operadores y sin información útil de momento. Investigado: no es redundancia técnica pura — `Qualification` alimenta las alertas de vencimiento (`compliance.watchables`) y el aviso de compatibilidad operador-aeronave al asignar (B4.4, `views.py` ~L335). La redundancia real es de **contenido**: la ficha de Operador ya muestra `authorizations` (texto libre) vía la tabla genérica de campos, y la lista de Habilitaciones muestra lo mismo estructurado pero **sin fecha** en la mayoría de los casos (`seed_operator_qualifications` las creó sin `issue_date`/`expiry_date`), así que hoy no aporta un dato que el operador no tenga ya a la vista. **No borrar el modelo** (rompería las 2 alertas/avisos reales) — evaluar en cambio si debe seguir siendo sección de primer nivel del sidebar o integrarse en la ficha del operador (mismo movimiento que LV-7 hizo con Kanban). Propuesta de diseño antes de implementar. |

### BLOQUE R6 — Alertas y reportes `P2`

| ID | Est. | Tarea |
|---|:--:|---|
| R6.1 | ⬜ | **[bug] Cierre bidireccional alerta ↔ tarjeta.** Hoy resolver la alerta mueve la tarjeta, pero **completar la tarjeta no resuelve la alerta** — no hay señal que lo haga. |
| R6.2 | ⬜ | **Resolver con motivo**: ISO 10.2 exige causa raíz y verificación de eficacia; hoy "Resolver" no pide nada. |
| R6.3 | ⬜ | Agrupar alertas del mismo origen (dos aeronaves, misma póliza, misma fecha → una fila). |
| R6.4 | ⬜ | **Informe ejecutivo en la web** (hoy solo existe como correo programado) y **exportación PDF** (hoy no hay PDF en ningún reporte). |
| R6.5 | ⬜ | **Revisión del día 15** sobre el mes anterior, además del cierre de fin de mes que ya existe (`check_monthly_records`, LV-30). Lo exige el procedimiento interno. |

### BLOQUE R7 — Base para la auditoría ISO `P2`

Decisión del usuario: **dejar la base y el mapeo, no implementar completo.** Trazabilidad
cláusula por cláusula en [docs/auditoria-iso-trazabilidad.md](docs/auditoria-iso-trazabilidad.md).

| ID | Est. | Cláusula | Dónde aterriza |
|---|:--:|---|---|
| R7.1 | ✅ | 7.1.3 horas de vuelo | **Hecho 2026-08-10, junto con R5.4** (mismo agregado, un solo lugar de implementación: `apps.operations.selectors.total_flight_duration`). Se muestra en la ficha de aeronave. |
| R7.2 | ⬜ | 7.1.3 baterías y ciclos | Modelo nuevo. **Punto natural de AeroLink** (DJI reporta ciclos). Diseñar la forma, no llenarla a mano. |
| R7.3 | ⬜ | 7.1.5 calibración GNSS/RTK, GCP | Tipo de documento nuevo. Ya hay un `Certificado Calibración.pdf` en `Z:` esperando. |
| R7.4 | ⬜ | 8.5.1/8.6 calidad del entregable (RMSE, GSD) | Solo diseño. |
| R7.5 | ⬜ | 45001 IPER, baterías LiPo, jornada de vuelo | Solo diseño. |
| R7.6 | ⬜ | 10.2 no conformidades, re-vuelos | Parcial (LV-46 ya crea mantención desde incidente). Diseñar el resto. |
| R7.7 | ⬜ | 9.1.1 KPIs | Parcial (el informe ejecutivo ya compara `valid_pct`, `expired`, `due_30`). |

### BLOQUE R8 — Clima y contexto operacional `P3`

| ID | Est. | Tarea |
|---|:--:|---|
| R8.1 | ⬜ | Clima/viento tipo [UAV Forecast](https://www.uavforecast.com/) en el calendario y antes del vuelo (ISO 8.1 exige revisión meteorológica). **Hoy el proyecto tiene cero llamadas HTTP salientes** — es una decisión de arquitectura, no una feature: toca CSP, secretos, caché y degradación cuando el servicio no responde. Diseñar antes de elegir proveedor. |

### BLOQUE X — Contrato de coexistencia con AeroLink `P1`

Decisión completa en [docs/dev/adr-0002-coexistencia-aerolink.md](docs/dev/adr-0002-coexistencia-aerolink.md).
**Las dos apps siguen separadas en despliegue** (las razones del ADR-0001 de AeroLink se
sostienen: la ingesta MQTT es continua y asíncrona, y su falla no debe voltear el sistema
operacional). Lo que cambia es que el contrato deja de estar sin definir.

| ID | Est. | Tarea |
|---|:--:|---|
| X.1 | ✅ | **`Aircraft.serial_number` como llave de cruce — cerrado 2026-08-10.** `Aircraft.save()` limpia todo el whitespace (interno además de extremos — `"".join(serial.split())`, no `.strip()`) y la migración `0027` aplicó lo mismo a las 16 filas reales — resuelve las 2 discrepancias de espacio (`RPA-4401`, `RPA-4436`). Las otras 2 (`RPA-4647` ceros vs "OO", `RPA-4884` `1581` vs `1582`) **no eran de normalización** — ninguna fuente propia podía arbitrarlas — y quedaron **confirmadas por el usuario contra el registro físico**: en ambos casos el valor que ya tenía la app era el correcto; el nombre de carpeta equivocado en `Z:` lo corrige el usuario directamente ahí (no se toca `Z:` desde este repo). Con las 4 resueltas, el campo pasó a `null=True, unique=True` (migración `0028`, mismo patrón que `FlightPermission.permission_number` para que varias aeronaves sin serial no choquen en el índice). Ya no bloquea nada de `R4`. |
| X.2 | ⬜ | Declarar por escrito: **AeroControl es maestro del padrón** (aeronaves, operadores, centros de costo, permisos, documentos); **AeroLink es maestro de telemetría, sesiones de vuelo y evidencia**. Ninguno escribe en el dominio del otro; ninguno comparte base de datos ni filesystem. |
| X.3 | ⬜ | AeroControl expone el padrón como endpoint **de solo lectura** para AeroLink. Ya hay DRF, token auth y throttling: es un scope nuevo, no una app nueva. |
| X.4 | ⬜ | Más adelante: recibir sesiones de vuelo cerradas desde AeroLink y conciliarlas con `FlightRecord`. **Aquí es donde el proyecto paga**: horas de vuelo y ciclos de batería (R7.1/R7.2) dejan de depender de lo que escriba el operador. |
| X.5 | ⬜ | Identidad (Entra ID vs cuentas Django para las mismas ~8 personas) y retención cruzada. |

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
