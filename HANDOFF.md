# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md); esto es el resumen de estado.
> Última actualización: **2026-07-31**.

## Estado de producción (VM `p340`)
- Corriendo en `origin/main` = **`9beab4c`**, servicio `active`, `/health/` 200.
- Acceso: Tailscale + **público por Funnel** (`https://p340.tailccd107.ts.net`).
- **Login endurecido** (django-axes, 5 intentos/15 min).
- **Datos reales cargados**: 12 centros de costo, 41 operadores, 15 aeronaves,
  109 habilitaciones. Documentos/alertas/reglas siguen en 0 (activación de
  cumplimiento = decisión de negocio, pendiente).
- **Tareas programadas** (systemd timers): `generate_alerts` 06:00,
  `send_alert_digest` 07:00, `backup` 22:00.
- Runbook de despliegue: [docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md).
  Deploy = `git pull --ff-only` + `uv sync --frozen` (los hago yo por SSH, sin
  sudo) + un bloque `sudo` (migrate/collectstatic/restart) que **corre el
  usuario**. Ese bloque pide contraseña de sudo — no manejarla.

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
