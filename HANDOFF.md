# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md); esto es el resumen de estado.
> Última actualización: **2026-08-03**.

## PRÓXIMA VENTANA — empezar acá
El batch **LV-29..32** se implementó (parte funcional) en la ventana del
2026-08-03. Estado por bloque (fuente del plan:
`C:\Users\cmunoz\.claude\plans\temporal-stirring-rivest.md`):
- **A · Vigencias DGAC (LV-29)** ✅ commit `09a091e`. Credencial operador + seguro
  JAC aeronave como campos: columna/alerta/calendario/dashboard, `load_dgac_vigencias`
  y `notify_expiring_credentials`. **Falta que el usuario entregue la transcripción
  de las capturas SIGO** para poblar `load_dgac_vigencias` (hoy corre con `--file`
  CSV; el fixture embebido va vacío).
- **B · Registros operacionales + cumplimiento mensual (LV-30)** ✅ commit `abd16d9`.
  Repositorio `/compliance/operational-records/`, `MonthlyComplianceReview`,
  `check_monthly_records` (timer fin de mes → avisa a Dirección), página
  `/compliance/monthly-review/`, tarjeta de panel.
- **C · Pasada ejecutiva — parte FUNCIONAL (LV-31/LV-25)** ✅ commit `cd042e3`.
  Columnas reales en asignaciones operador/aeronave, colapso de permisos
  multi-día en el calendario, VLOS/paracaídas como lista (LV-25).
- **C · resto ESTÉTICO + D · modernización UX/UI (LV-24, chips, LV-23, LV-32)**
  ⬜ **diferido a revisión con capturas del usuario** (decisión confirmada
  2026-08-03: no adivinar estética a ciegas; el propio plan D pide un "commit de
  propuesta" para evaluar con capturas). Es la pasada de tokens `--ac-*`/tablas/
  paleta/panel; se hace con el usuario mirando la app desplegada.

**DEPLOY PENDIENTE (lo revisa/dispara el usuario):** el batch trae migraciones
(`registry 0021`, `compliance 0011`) → `git pull` + bloque sudo `migrate` +
`collectstatic` + restart, más seeds (`seed_document_types`,
`seed_alert_rules --with-optional`, `load_dgac_vigencias` cuando estén los datos)
y, opcional, el timer `check_monthly_records` (ver scheduled-operations.md).
Suite completa **618 verde** (2026-08-03). Kanban sigue en standby; T3.4/T4.1
diferidos.

> Nota: quedó pendiente de despliegue además el batch de **aislamiento por
> objeto** (`36acc76`, no-op hoy, sin migraciones → `pull` + restart), previo a
> este batch. Ver "Estado de producción".

## Estado de producción (VM `p340`)
- Prod desplegado hasta el batch grande (documentos en fichas, empresa, LV-20/26,
  búsqueda, dashboard, F-13, etc.; deploy confirmado por el usuario). **`origin/main`
  va adelante en `36acc76`** — **pendiente de despliegue, esperando revisión**:
  aislamiento por objeto (F-03/F-06/F-05, `TenantScopedQuerysetMixin` en todas las
  fichas/ediciones) — **no-op con un solo tenant, sin migraciones → `pull` +
  restart**. Suite completa **590 verde** (2026-08-03).
- Acceso: Tailscale + **público por Funnel** (`https://p340.tailccd107.ts.net`).
- **Login endurecido** (django-axes, 5 intentos/15 min).
- **Datos reales cargados**: 12 centros de costo, 41 operadores, 15 aeronaves,
  109 habilitaciones. **Scaffolding de cumplimiento sembrado en prod**
  (`seed_document_types` = 6 tipos, `seed_alert_rules` = 2 reglas esenciales).
  Faltan **documentos con vencimiento** (decisión de negocio) para que
  `generate_alerts` produzca alertas; hoy sigue en 0 alertas.
- **Tareas programadas** (systemd timers): `generate_alerts` 06:00,
  `send_alert_digest` 07:00, `backup` 22:00.
- Runbook de despliegue: [docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md).
  Deploy = `git pull --ff-only` + `uv sync --frozen` (los hago yo por SSH, sin
  sudo) + un bloque `sudo` (migrate/collectstatic/restart) que **corre el
  usuario**. Ese bloque pide contraseña de sudo — no manejarla.

## Cerrado (2ª ventana, 2026-07-31)
- **Scaffolding de cumplimiento** (elegido "activar cumplimiento"): comando
  nuevo `seed_alert_rules` (idempotente, `--with-optional`) + tests; guía
  `docs/compliance-setup.md` Paso 3 apunta al comando. Sembrado y verificado en
  **local** (BD de dev migrada a `main` con respaldo) y **prod** (2 reglas
  creadas; 0 alertas porque faltan documentos con vencimiento). Commit `8f688f4`.
- **LV-15** (`ceb0a70`): chips de "Equipos habilitados" con color estable por
  `QualificationType` (`chip_class`, hash `crc32` → paleta Bootstrap *subtle*).
- **LV-17 + LV-18** (`14854fe`): fechas fuera del form de asignación de operador
  (autollenado `start_date=hoy`); **asignación masiva** de operadores a un CC
  (`OperatorBulkAssign` + `services.bulk_assign_operators`, semántica *un
  operador = un CC* con mover/cerrar la previa). Aclarado con el usuario: el
  pedido era agilizar, no un bloqueo.
- **LV-19** (`6e21930`): el `name` del CC vuelve al `CostCenterForm` como
  **opcional** (LV-16 lo había quitado y quedaba congelado); ahora se nombran/
  corrigen CC desde la app. La confusión inicial era con `responsible` ("Nombre
  de administrador de contrato"), que siempre fue editable.
- **i18n + CHANGELOG** (`0d4992a`, `71f9121`): 3 strings ES nuevos al catálogo
  (los introdujeron LV-17/18/19 y el guard `test_translations` los cazó) +
  CHANGELOG `[Unreleased]` al día. **Todo desplegado; suite 561 verde.**
- **Refactor Kanban rescatado** (`05b34f2`): el campo técnico "Orden" sale de los
  4 formularios Kanban (se asigna server-side, append al final). Reaplicado
  limpio desde la rama varada `amazing-bouman` en vez de mergearla (61 commits
  atrás, migraciones en conflicto).
- **Negocio — reporte de destinatarios** (`630f870`): comando
  `check_digest_recipients` (read-only) lista cada CC como OK/MISSING para el
  digest. En local, 11/12 sin destinatario. Falta que el usuario asigne
  responsable/contacto por CC y cargue documentos con vencimiento (datos).
- **Higiene TL.6 hecha (rescate + poda)** (`a27391b`): al podar los 3 worktrees
  fusionados se hallaron 2 fixes sin commitear → **rescatados a `main`**: bug de
  auditoría DRF (`set_audit_context` unwrap `_request` + test) e i18n "Unassigned"
  en la lista de aeronaves. Worktrees `eager-hofstadter`/`elegant-ishizaka`/
  `suspicious-boyd` **eliminados**. Quedan `main` y `amazing-bouman` (podable a
  futuro, su valor ya extraído).
- **Cluster UX T5.2–T5.5 (cara al usuario, recomendado por prioridad):**
  - **T5.2/T5.3** (`be6383f` + `1125d88`): búsqueda global — antes
    **inalcanzable** — ahora con caja en el navbar y resultados que abren la
    **ficha** (no la lista). Botón **"Importar"** en las listas de
    CC/aeronaves/operadores (bloque `list_actions` en `generic/list.html`).
  - **T5.4** (`bdb9403`): dashboard — tiles ahora enlazan a sus listas; el panel
    de vencimientos unifica habilitaciones + **documentos + permisos** (antes
    solo habilitaciones), cada uno con enlace a su ficha (`upcoming_expirations`).
  - **T5.5** (`bdb9403`): registrar vuelo desde la ficha del permiso prellena el
    permiso y **acota piloto/aeronave al roster** del permiso.
  - **Cluster UX restante (no tomado):** T5.6 (paginación HTMX + búsqueda en
    vivo), T5.7 (exportar en todas las listas), T5.8 (i18n/accesibilidad).
- **Dependabot resuelto** (`6b86970`): de 8 PRs, solo 2 vivos aplicados directo
  a `main` — `django-crispy-forms` 2.7 y `gunicorn <27` (suite verde). Los otros
  5 ya estaban en `main` (checkout/setup-uv v7, crispy-bootstrap5 2026.3,
  crispy-forms 2.6, ruff base vieja) → cerrar en GitHub. **`ruff` NO subido a
  0.16.0**: cambia el set de reglas por defecto (+224 issues de orden de
  imports); adoptarlo es un cleanup aparte (`ruff check --fix`). Quedan 3 PRs
  `origin/codex/*` sin atender (GitHub). **El deploy de crispy exige `uv sync`.**
- **Pendiente para el usuario (negocio, no código)**: crear **CC110 Casa Matriz**
  en prod (desde *Centros de costo → + Nuevo*, con el campo Nombre; ya está en
  local), asignar destinatarios por CC, y **cargar documentos con vencimiento**.

## Cerrado esta sesión (2026-07-31)
- **Puesta en producción + seguridad**: axes, Funnel, systemd timers, fix SRI de
  estáticos versionado, guía de cumplimiento y de Funnel en `docs/`.
- **Revisión en vivo LV-1..LV-16** (ver sección "Revisión en vivo 2026-07-30" en
  el plan): catálogo de documentos, título autogenerado, notas, columna de
  seguro en aeronaves, indicador de progreso al importar KMZ, sidebar reagrupado
  + icono, habilitaciones desde `authorizations`, lista de habilitaciones por
  operador, form de CC simplificado. **LV-6 (Gantt Kanban) en standby** y su
  enlace oculto (LV-7). LV-15 (colores de chips) futuro.
- **BLOQUE 4 completo** (B4.3 habilitaciones DGAC estructuradas, B4.4 aviso de
  compatibilidad operador–aeronave).
- **B5.5** (panel de usuarios y roles, solo lectura).
- **FASE 4 testing**: T4.3 (dashboard/maintenance/generate_alerts a 100%),
  T4.4 (neutralización de fórmulas en reportes workboard).
- **R.10/T5.1** verificado ya hecho (un solo `:root` de tokens `--ac-*`).
- **T3.2 TENANCY COMPLETO** (Fases 0-4). Ver
  [docs/dev/adr-0001-tenancy.md](docs/dev/adr-0001-tenancy.md): esquema
  (`tenant` en raíces + Document/AlertRule; el resto deriva), `visible_tenant_ids`,
  fix de la fuga F-08 (OR → ruta canónica `cost_center__tenant`), constraints
  únicas por tenant, y matriz de aislamiento (`apps/core/test_tenancy.py`).
  Behavior-preserving hoy (un solo tenant "default"), listo para centralizar.

## Próximo (elige en la próxima ventana)
- **Datos/negocio** (sin código): activar monitoreo de cumplimiento (cargar
  documentos con vencimiento + reglas), asignar **operador responsable** en los
  12 CC, configurar `EMAIL_*` en `/etc/aerocontrol.env`, agregar usuarios al
  grupo *Dirección*. Guía: [docs/compliance-setup.md](docs/compliance-setup.md).
- **Opcional, F-03/F-06 (IDOR)**: scoping por objeto en vistas de *detalle* para
  que no se pueda abrir por URL un registro de otro tenant. Irrelevante con un
  solo tenant; hacer si se centraliza.
- **Bloques diferidos (requieren propuesta de diseño primero)**: LV-6 (Gantt),
  B5.3 (acciones rápidas del centro de admin), B6.3 (asistente IA),
  GEO-12b/13b/14 (bloqueados hasta tener KMZ con ExtendedData / misión DJI real).
- **Higiene**: TL.6 (poda de ramas viejas), TL.11 (tags de CHANGELOG), T4.5.
- **Arquitectura mayor restante**: FASE 1 (partir `core`), FASE 3 restante
  (T3.3/T3.4/T3.5). DJI (T6.7) sigue diferido tras estabilizar.

## Gotchas de esta base (ver también memoria del proyecto)
- `manage.py dumpdata --output` en Windows escribe **cp1252** → usar
  `PYTHONUTF8=1` (rompió un `loaddata` con acentos).
- La suite completa tarda **~5 min**; correrla en background.
- Pegar bloques multilínea en la sesión SSH del usuario se corrompe con
  *bracketed paste* (`^[[200~`) → dar los bloques `sudo` en **una sola línea**.
- Sin datos de dominio no reproduce nada: `run` local usa `config.settings.dev`;
  la BD real de desarrollo está en `D:/I+D/AeroOpsDesk_Data/`.
