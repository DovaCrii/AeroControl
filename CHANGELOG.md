# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto usa versionado `alpha`/`beta`/semántico informal mientras
está en fase de estabilización (ver [MASTER_PLAN.md](MASTER_PLAN.md)).

## [Unreleased]

Nada todavía.

## [0.2.0-alpha] - 2026-07-24

Estabilización (`MASTER_PLAN.md` FASE 0 + higiene del Bloque 0), integración
Alertas⇄Kanban (BLOQUE 1, backend), notificaciones y operación programada
(BLOQUE 2), reportes ejecutivos (BLOQUE 6) y robustez de reglas (BLOQUE 4
parcial). Las dos líneas de trabajo paralelas (`codex/impeccable-ui-audit` y
`codex/stabilization-blocks-0-6`) quedaron fusionadas antes de este release.

### Added (BLOQUE 1 — Alertas ⇄ Kanban, backend)
- `AlertRule` puede generar una tarea Kanban: campos `create_kanban_task`,
  `target_board`, `target_stage` con validación de coherencia.
- `generate_alerts` crea una `KanbanTask` vinculada a la alerta
  (`source_object`), con prioridad por urgencia (vencida/≤7 días/resto),
  `due_date` del campo vigilado y responsable derivado cuando la entidad
  vigilada es o expone un operador. Idempotente.
- Al resolver una alerta —o al reemplazar el documento vencido— la tarea
  vinculada se mueve automáticamente a la etapa "completada" del tablero,
  registrando el movimiento en `AuditEvent`.
- Comando `init_dgac_board`: tablero "Cumplimiento DGAC" con sus etapas y
  etiquetas de trámite (idempotente).

### Added (BLOQUE 2 — Notificaciones y operación programada)
- Modelo `JobRun`: cada ejecución de `generate_alerts`, `send_alert_digest` y
  `backup` queda registrada con inicio, fin, resultado y resumen, así que se
  puede comprobar si las tareas programadas realmente corrieron. Visible en el
  admin en modo solo lectura.
- Comando `send_alert_digest`: envía a cada responsable de centro de costo un
  resumen de documentos y habilitaciones agrupados por urgencia (vencidos, 7,
  15 y 30 días), con `--dry-run` para revisar sin enviar. Si un centro de costo
  no tiene destinatario, lo informa y continúa con los demás.
- Configuración de correo por entorno (`EMAIL_*`, `DEFAULT_FROM_EMAIL`,
  `SITE_BASE_URL`). Sin `EMAIL_HOST` el correo se imprime en consola.
- Campo **Operador responsable** en centro de costo: destinatario de los
  resúmenes. El campo de texto anterior no permitía contactar a nadie.
- `scripts/schedule_tasks.ps1` para registrar los tres trabajos diarios en el
  Programador de tareas de Windows, y `docs/scheduled-operations.md` con el
  procedimiento completo y su equivalente en cron.

### Added (BLOQUE 6 — Reportes ejecutivos)
- **Reporte de estado documental** (`/compliance/report/`, enlazado en el panel
  lateral): porcentaje de documentos vigentes por centro de costo, vencimientos
  a 7/15/30 días, vencidos, alertas abiertas con su antigüedad y tiempo medio
  entre la detección de una alerta y su resolución. Filtros por centro de costo,
  tipo de documento y rango de fechas, con exportación a Excel, Word y CSV
  presentable ante jefatura o DGAC.
- Comando `compliance_report` con las mismas cifras, que además puede escribir
  el Excel en una carpeta indicada.
- Comando `send_executive_report --period week|month`: envía el informe
  ejecutivo comparando el período con el anterior (marcando si cada indicador
  mejoró o empeoró) y adjunta el Excel. Destinatarios del grupo *Dirección* o
  indicados con `--to`; `--dry-run` permite revisar antes de enviar. Registrado
  como tarea semanal.
- `bootstrap_roles` crea también el grupo *Dirección* (vacío y sin permisos: es
  una lista de destinatarios, no un rol), para que montar un entorno no dependa
  de leer el código del comando para descubrir que el grupo debe existir.

### Added (BLOQUE 4 parcial — Robustez de reglas y deuda de datos)
- Las reglas de alerta ya no aceptan texto libre: la entidad y el campo a
  vigilar se eligen de una lista validada contra los modelos reales, así que una
  regla mal escrita se rechaza al crearla en vez de fallar en silencio cada
  noche. Las reglas existentes se normalizaron automáticamente; las que no se
  pudieron resolver quedaron archivadas con una nota explicando el motivo.
- Comando `find_duplicate_operators`: lista los operadores que parecen ser la
  misma persona ingresada dos veces, con sus diferencias campo a campo y cuántos
  registros apuntan a cada uno. Con `--apply --group` fusiona un grupo: mueve
  todas las referencias al registro que se conserva, archiva el duplicado con
  nota y deja constancia en la auditoría. No borra nada y no tiene modo masivo.

### Changed
- `on_delete` de `Document`/`Alert`/`AlertRule`/`PermissionHistory`/
  `MaintenanceHistory` cambiado de `CASCADE` a `PROTECT`: el historial de
  cumplimiento ya no se puede perder por borrado en cascada.
- La vista de detalle ya no muestra columnas internas (identificador UUID,
  fechas de auditoría, marca de archivado, tenant) al usuario final.

### Fixed (legibilidad y contraste, revisión en vivo)
- Alertas y tarjetas Kanban mostraban `Qualification object (uuid)` por falta
  de `__str__` en varios modelos; ahora muestran la entidad legible.
- Lista de alertas rediseñada: entidad, regla y badge de vencimiento/atraso
  en lugar del UUID y el mensaje repetido.
- Contraste de los títulos de grupo del panel lateral: 3.79 → 8.06:1 (AA).
- El contador de alertas ya no desaparece al contraer el panel lateral.
- Badges de etapa del Kanban (las clases existían en las plantillas pero no
  en el CSS) y énfasis visual para tareas atrasadas, con icono además de color.
- Gráficos del panel: paleta ilegible en modo oscuro (1.16 → 5.03:1), etiquetas
  con valores crudos de base de datos, y conteos que incluían registros
  archivados. Los gráficos ahora recolorean al cambiar de tema.
- Calendario: los eventos del mes ya no se cortan a media palabra; etiqueta
  completa en el tooltip y colores adecuados en modo oscuro.
- Icono de "Vuelos" diferenciado del de "Aeronaves".
- Traducciones faltantes (~19 cadenas) y dos cadenas que no seguían la
  convención de idioma del proyecto.

### Fixed
- Dashboard: `TemplateSyntaxError` por bloque `extrahead` duplicado que
  causaba un 500 en toda sesión tras el login.
- Mantenimiento: el flujo de cierre (`in_progress → completed`) quedaba en
  un callejón sin salida porque `record_detail.html` nunca renderizaba
  `completion_form`; ahora se puede completar una mantención desde la UI.
- `scripts/verify.ps1` no comprobaba el código de salida de cada paso y
  podía reportar éxito con la suite de pruebas en rojo.

### Added
- Umbral de cobertura real (`fail_under=83` en `pyproject.toml`), reemplazando
  la medición sin consecuencias que tenía CI.
- Test que compila las 43 plantillas HTML (`apps/core/test_templates.py`)
  para atrapar errores de sintaxis que `manage.py check` no detecta.
- Pruebas para `apps/maintenance` (antes sin ninguna) y para
  `generate_alerts` (antes 0% de cobertura).
- Índices en `Alert(is_resolved, is_active)`, `Document(expiry_date,
  is_current_version)` y `KanbanTask(board, stage, order)`.
- Log JSON estructurado (`compliance.alerts`) cuando `generate_alerts`
  descarta una regla inválida.
- `AUDIT_CLAUDE.md` (auditoría técnica) y `MASTER_PLAN.md` (tablero de
  bloques de trabajo, fuente de verdad del roadmap).
- `AGENTS.md` ampliado: precedencia documental, contrato de permisos de
  lectura, Definition of Done por tipo de cambio, convención de ramas.

### Changed
- `docs/` reorganizado: documentación de producto en la raíz
  (`SECURITY.md`, `chapter1-import.md`, `frontend-boundary.md`,
  `postgresql-readiness.md`); notas internas y bitácoras de desarrollo
  movidas a `docs/dev/`.
- Rutas de ejemplo en `README.md`, `.env.example`, `ARCHITECTURE.md` y
  `docs/chapter1-import.md` genericizadas (ya no exponen la ruta personal
  del equipo de desarrollo original).
- `openspec/config.yaml` y `docs/dev/03-Roadmap.md` sincronizados con el
  estado real del proyecto (afirmaban falsamente que no había runner de
  tests configurado).
- Código reformateado con `ruff format` (sin cambios de comportamiento).

### Removed
- `.agents/skills/impeccable/` (tooling de terceros vendorizado, ~62.700
  líneas sin relación con el producto), `prompts/` (instrucciones
  obsoletas) y `.atl/skill-registry.md` (rutas absolutas de una máquina
  personal).

## [0.1.0-alpha] - 2026-07-23

Primera fase de estabilización, según `BACKLOG.md`. Estado del repo:
`main` en el merge del PR #9 ("resource planning, calendar and action
plan").

### Added
- Flujo de permisos de vuelo y bitácora de vuelos, con validación cruzada
  de aeronave, operador, fecha y horas.
- Calendario unificado de operaciones y mantenimientos; historial
  automático de cambios de estado.
- Tablero Kanban con arrastrar y soltar, prioridades, asignación a
  operadores y filtros persistidos en URL.
- Dashboard con gráficos (Chart.js) y exportación CSV con neutralización
  de fórmulas.
- Tema claro/oscuro, iconografía semántica, marca AeroControl e interfaz
  bilingüe ES/EN.
- Flujo de documentos: creación, versionado, reemplazo y descarga
  autenticada.
- Roles estándar (`bootstrap_roles`) con permisos por operación; pruebas
  de autorización (403) en escritura.
- Respaldo local con manifiesto, checksum SHA-256 y verificación;
  restauración con protección contra sobrescritura accidental.
- Entorno reproducible con `uv`, `pytest`, `ruff`, `bandit`, `pip-audit`,
  CI (GitHub Actions) y Dependabot.
- Importación validada de datos oficiales (Capítulo 1): centros de costo,
  aeronaves y operadores, con vista previa y reversión transaccional.
- API DRF de solo lectura + escritura acotada para tareas Kanban, con
  autenticación por token y documentación OpenAPI.

[Unreleased]: https://github.com/DovaCrii/AeroControl/compare/v0.2.0-alpha...HEAD
[0.2.0-alpha]: https://github.com/DovaCrii/AeroControl/compare/v0.1.0-alpha...v0.2.0-alpha
[0.1.0-alpha]: https://github.com/DovaCrii/AeroControl/releases/tag/v0.1.0-alpha
