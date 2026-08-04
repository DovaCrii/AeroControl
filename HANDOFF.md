# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md); esto es el resumen de estado.
> Última actualización: **2026-08-04** (3ª tanda LV-44..49).

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
- **C · resto ESTÉTICO + D · modernización UX/UI (LV-24/LV-32 = LV-D1..D9)**
  ✅ **hecho en una pasada de diseño EN VIVO con el usuario** (2026-08-03, sobre
  el demo `:8011` con datos sembrados). Commits `8b51bc2` (pastillas legibles
  oscuro/claro, contraste botones/cabeceras, panel reordenado, buscador,
  calendario, Documentos fuera del menú, **+ fix del `.mo`**), `42720f6` y
  `a585b23` (columnas de listas compactas, una acción/fila, CC=código), `e1cf5a7`
  (grilla pareja de KPIs, pastillas menos opacas). Suite/guardias verdes.
  **Queda pendiente (no tocado):** LV-23 (grid de checkboxes del roster del
  permiso) y el pulido fino que el usuario pida en próximas revisiones.

**DEPLOY: HECHO 2026-08-03** (commit `6640f66`): migrate + collectstatic + seeds
+ `load_dgac_vigencias` (44 cargadas) + restart, con el usuario en la sesión SSH.
Gotcha resuelto: `/etc/aerocontrol.env` es 600 root → cargar con
`source <(sudo cat /etc/aerocontrol.env)` (no `. …`) para correr como el usuario
sin romper el dueño de la SQLite. **Opcional pendiente:** agregar los timers
`check_monthly_records` y `notify_expiring_credentials` (ver scheduled-operations.md).
Suite completa **618 verde** (2026-08-03). Kanban sigue en standby; T3.4/T4.1
diferidos.

### 2ª tanda de revisión en vivo (LV-33..40) — post-deploy 2026-08-03
Tras el primer deploy, el usuario siguió revisando y salieron LV-33..40, todos
**implementados y en `main`** (commits `72ac499`, `7545e01`, `c92ed86`,
`090da0e`, `62c1e04`, `2f9c876`): LV-33 (fallback Operadores/Flota del CC por
`cost_center`), LV-34 (responsable del CC por tipo Administrador/Operador/Externo,
JS en `app.js`), LV-35 (textareas medianas), LV-37 (pestaña "Equipo"→"Operadores"),
LV-38 (grilla de operadores/flota en el permiso), LV-39 (permiso: estado +
número opcional, **migración `operations 0011`**), LV-40 (cargar documento vuelve
a la ficha). Después (2026-08-04) se cerraron los últimos: **LV-41** (comentario
`{# %}` multilínea que se renderizaba literal en el calendario → `{% comment %}`,
`65554ca`), **LV-42** (pastillas grises se fundían con la tarjeta en oscuro →
borde a 3.64:1, `2453b7a`), **LV-36** (form del CC en secciones agrupadas
Identificación/Responsable/Notas, ambas vías full-page+modal; + fix de un
`#~ msgid` duplicado que rompía `compilemessages`, `5f11949`) y **LV-43** (timers
LV-29/30 cableados en `schedule_tasks.ps1`, `1e0d694`). **Ya no queda ningún LV
abierto** (LV-29..43 todos ✅).

> **2º DEPLOY CONSOLIDADO: HECHO 2026-08-04** (commit en VM = `2c7ad1b`, con el
> usuario por SSH). `git pull --ff-only` (fast-forward `5066ab3..2c7ad1b`, 12
> archivos) + `uv sync --frozen` + `migrate --no-input` ("No migrations to
> apply" — `operations 0011` ya estaba aplicada de un pull anterior) +
> `collectstatic --no-input` (1 archivo nuevo, `app.css` de LV-42; 365
> post-procesados) + `backfill_resource_assignments` (0 nuevos, idempotente) +
> `systemctl restart aerocontrol`. **Los 2 timers de LV-43 quedaron activos**:
> `aerocontrol-monthly.timer` (check_monthly_records, próxima 23:30 UTC) y
> `aerocontrol-credentials.timer` (notify_expiring_credentials, próxima 07:30
> UTC) — confirmado con `systemctl list-timers`. Ya no queda deploy pendiente
> de este batch. Gotcha nuevo: `. /etc/aerocontrol.env` da "Permission denied"
> (600 root) — usar `source <(sudo cat /etc/aerocontrol.env)` (ya documentado
> arriba, se repitió el error igual).
>
> **Pendiente (no bloqueante):** verificación visual en pantalla del permiso
> (grilla/estado, LV-38/39), responsable del CC (LV-34) y form del CC en
> secciones (LV-36) — no se hizo por el pane del navegador congelado en esta
> máquina. Y LV-D6-resto / capturas futuras si el usuario quiere seguir la
> revisión en vivo.

> **DESPLEGADO 2026-08-03** (commit `6640f66`): migrate + collectstatic + seeds +
> 44 vigencias cargadas + restart, verificado por el usuario. Ver "Estado de
> producción". Ya no queda deploy pendiente de este batch.

### 3ª tanda (LV-44..49) — 2026-08-04, aún NO desplegada en la VM
Tras el 2º deploy, siguieron apareciendo hallazgos y pedidos en la misma
ventana, todos **implementados y en `main`** (commits `a8a0d7d`, `3de71c8`,
`f2102b7`, `d56b7ad`, `037b2e9`, `46c41f4`, `3e31aee`):
- **LV-44**: ficha del CC mostraba "RESPONSIBLE CONTACT NAME/EMAIL" en inglés
  → `verbose_name` explícito en el modelo, reutiliza msgids del form.
  Migración `registry 0022` (solo `verbose_name`, sin cambio de esquema).
- **LV-45**: botón "Crear tarea" de `/compliance/alert/` fallaba (nunca se
  corrió `init_dgac_board`) — **corregido también en la VM** por el usuario
  ("Created board 'Cumplimiento DGAC'…"), esta parte YA está en prod.
- **LV-46**: nuevo estado `Aircraft.status="damaged"` ("Mal estado") + botón
  de un clic "Reportar accidente/daño" que abre una mantención de emergencia
  y cruza con la alerta "Mantenciones abiertas" ya existente. Migración
  `registry 0023` (solo `choices`, sin cambio de esquema).
- **LV-47**: botones "Anterior/Siguiente" del calendario no hacían nada
  (desconectados de FullCalendar) — quitados; unificado el respaldo sin-JS.
- **LV-48**: reapertura del standby de Kanban — el tablero se renombra a
  **"Seguimiento de alertas"** (ya no dice "Kanban" en ningún lado).
- **LV-49**: el Reporte de cumplimiento mostraba 0/0,0%/0 en todo CC porque
  nunca sumó las vigencias DGAC (LV-29) — ahora las integra (excluidas si hay
  filtro de tipo de documento).

**Pendiente: 3er deploy consolidado** (trae `registry 0022`+`0023` + CSS/JS
del calendario + plantillas nuevas + `.mo` recompilado): mismo patrón que las
veces anteriores —
```bash
cd /opt/aerocontrol && git pull --ff-only && uv sync --frozen
```
seguido de (recordar `source <(sudo cat /etc/aerocontrol.env)`, no `. …`):
```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py migrate --no-input && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```
Sin timers ni tableros nuevos que activar en esta tanda (LV-45's `init_dgac_board`
ya se corrió). Suite local **632/632 verde** (corrida completa 2026-08-04, tras
corregir dos fallas reales que este batch introdujo: el test de
`test_specific_modules_keep_spanish_labels[kanban-...]` que aún esperaba
"Tablero Kanban", y un `verbose_name=_(...)` de LV-44 con mayúscula
distinta a la del catálogo — ver LV-44 en MASTER_PLAN.md). Nada verificado aún
en la VM salvo LV-45.

## Estado de producción (VM `p340`)
- **Desplegado el batch LV-29..32 + la pasada de diseño (commit `6640f66`) el
  2026-08-03.** Migraciones aplicadas (`registry 0021`, `compliance 0011`),
  `collectstatic` OK (CSS nuevo), seeds corridos (`seed_document_types` = 9 tipos,
  `seed_alert_rules --with-optional` = 8 reglas), y **`load_dgac_vigencias`
  cargó 44 vigencias** (28 no coincidentes = registros del SIGO ausentes en
  AeroControl). El batch de **aislamiento por objeto** (`36acc76`) entró en el
  mismo pull. Suite completa **618 verde** (2026-08-03).
- Acceso: Tailscale + **público por Funnel** (`https://p340.tailccd107.ts.net`).
- **Login endurecido** (django-axes, 5 intentos/15 min).
- **Datos reales cargados**: 12 centros de costo, 41 operadores, 15 aeronaves,
  109 habilitaciones. **Vigencias DGAC cargadas** (credencial operador + seguro
  JAC aeronave, 44 fechas del SIGO). **Scaffolding de cumplimiento** ampliado
  (9 tipos de documento incl. registros operacionales; 8 reglas incl. las 2 de
  vigencias + cumplimiento mensual). Faltan **documentos con vencimiento**
  (decisión de negocio) para más alertas; y el timer opcional
  `check_monthly_records` / `notify_expiring_credentials` (ver scheduled-operations).
- **Tareas programadas** (systemd timers), **las 5 activas desde 2026-08-04**:
  `generate_alerts` 06:00, `send_alert_digest` 07:00, `backup` 22:00,
  `check_monthly_records` (diario 23:30, actúa solo el último día del mes) y
  `notify_expiring_credentials` (diario 07:30, LV-29 opcional — activado).
  Confirmado con `systemctl list-timers 'aerocontrol-*' --all`; aún sin `LAST`
  run (recién creados). Revisar en unos días con
  `journalctl -u aerocontrol-monthly.service -n 30 --no-pager` /
  `…-credentials.service…` que corrieron sin error.
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
- **El `.mo` está versionado y el deploy NO lo recompila.** Al tocar
  `locale/es/LC_MESSAGES/django.po` hay que **recompilar el `.mo` y commitearlo**,
  o los strings ES nuevos salen en inglés en prod. La VM/dev no tiene `gettext`
  (por eso la guardia `test_translations` lee el `.po`), así que compilar con
  `uv run python -c "import polib; polib.pofile('locale/es/LC_MESSAGES/django.po').save_as_mofile('locale/es/LC_MESSAGES/django.mo')"`.
- `manage.py dumpdata --output` en Windows escribe **cp1252** → usar
  `PYTHONUTF8=1` (rompió un `loaddata` con acentos).
- La suite completa tarda **~5 min**; correrla en background.
- Pegar bloques multilínea en la sesión SSH del usuario se corrompe con
  *bracketed paste* (`^[[200~`) → dar los bloques `sudo` en **una sola línea**.
- Sin datos de dominio no reproduce nada: `run` local usa `config.settings.dev`;
  la BD real de desarrollo está en `D:/I+D/AeroOpsDesk_Data/`.
