<div align="center">

<img src="assets/aerocontrol-mark.svg" width="160" height="120" alt="Logo de AeroControl" />

# AeroControl

**Centro de operaciones local para equipos RPA/UAS**

Registro de flota, tripulación, cumplimiento normativo, mantenimiento y flujo de trabajo operativo en una aplicación Django local-first.

[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-2EC4B6.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-1B2A4A.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-6.0-1B2A4A.svg)](https://www.djangoproject.com/)
[![Estado](https://img.shields.io/badge/estado-v0.3.0--alpha-orange.svg)](#estado-y-próximos-pasos)

</div>

---

## Tabla de contenidos

- [Qué es AeroControl](#qué-es-aerocontrol)
- [Qué incluye](#qué-incluye)
- [Arquitectura y estructura](#arquitectura-y-estructura)
- [Puesta en marcha local](#puesta-en-marcha-local)
- [Comandos operativos](#comandos-operativos)
- [Operación programada](#operación-programada)
- [Seguridad y cumplimiento](#seguridad-y-cumplimiento)
- [Carga del Capítulo 1](#carga-del-capítulo-1)
- [Flujo operativo Kanban](#flujo-operativo-kanban)
- [Estado y próximos pasos](#estado-y-próximos-pasos)
- [Licencia](#licencia)

## Qué es AeroControl

AeroControl es una aplicación de gestión operativa para equipos que operan
aeronaves no tripuladas (RPA/UAS). Reúne en un solo sistema el registro de la
flota y la tripulación, el cumplimiento documental y normativo, los permisos de
vuelo, el mantenimiento y la coordinación del trabajo diario, de modo que la
información operativa deje de vivir dispersa en planillas y carpetas sueltas.

Está construida como aplicación **local-first**: corre en el equipo de la
organización, con la base de datos y los documentos bajo su control directo y sin
dependencia de servicios en la nube. Eso la hace apta para entornos con
conectividad limitada o con requisitos de custodia de los datos.

**Para quién.** Jefaturas de operaciones, encargados de cumplimiento y equipos de
terreno que necesitan trazabilidad de habilitaciones, vencimientos y permisos —con
alertas y un registro de auditoría— sin montar infraestructura pesada.

> **Estado:** `v0.3.0-alpha`. La estabilización inicial y una revisión completa de
> seguridad, estabilidad, desempeño y UX están **cerradas**; es apto para evaluación
> local controlada. Antes de producción se requiere una política de respaldos,
> antivirus, retención de datos y control de accesos, más el endurecimiento aún
> diferido (tenancy estricto, CSP enforcing).
>
> 📋 **El trabajo pendiente se sigue por bloques en [MASTER_PLAN.md](MASTER_PLAN.md)**,
> con la evidencia técnica en [AUDIT_CLAUDE.md](AUDIT_CLAUDE.md). La siguiente pieza
> grande de producto es el **editor geoespacial KMZ/KML** (BLOQUE GEO, propuesta en
> [docs/dev/geo-editor-plan.md](docs/dev/geo-editor-plan.md)). DJI Cloud API sigue
> diferida.

## Qué incluye

| Área | Alcance actual |
| --- | --- |
| Registro | Centros de costo, responsables, aeronaves, operadores, asignaciones y cualificaciones |
| Cumplimiento | Documentos, tipos, alertas y reglas de vencimiento |
| Operaciones | Permisos de vuelo, historial y registros de vuelo |
| Mantenimiento | Registros programados/no programados e historial de estados |
| Tablero | Kanban, Lista y Calendario; etapas, etiquetas, checklists, prioridades y responsables |
| Planificación geoespacial | Importa KMZ/KML de planificación de vuelo (original preservado), interpreta carpetas y geometrías, y versiona de forma inmutable. El editor de mapa interactivo está **en construcción** (BLOQUE GEO) |
| Administración | Centro operativo y Django Admin técnico separado |
| Seguridad | Autenticación, permisos por modelo, auditoría append-only y cargas con validación de firma |
| Localización | Español por defecto y cambio directo ES/EN |

> El **aislamiento multi-organización (tenancy)** está sentado como base opcional pero
> aún no es estricto: hoy se aplica en Workboard, asignaciones y el calendario, no en
> todos los módulos. Fijarlo es un bloque prioritario del plan ([MASTER_PLAN.md](MASTER_PLAN.md), FASE 3).

## Arquitectura y estructura

| Capa | Detalle |
| --- | --- |
| Backend | Python 3.12, Django 6.0 y plantillas renderizadas en servidor |
| UI | Bootstrap 5, crispy-forms, HTMX y static/css/app.css |
| Persistencia | SQLite por defecto mediante DB_PATH; PostgreSQL queda como opción de escalamiento |
| Datos | Documentos, respaldos y logs fuera del repositorio mediante DOCUMENTS_DIR, BACKUPS_DIR y LOGS_DIR |
| Operación | Scripts PowerShell, uv, GitHub Actions, Ruff, pytest, Bandit y pip-audit |

~~~text
AeroControl/
├── apps/             # core, registry, compliance, operations, maintenance,
│                     # workboard y dashboard
├── config/settings/  # configuración base
├── templates/        # interfaz renderizada en servidor
├── static/           # CSS y recursos visuales
├── assets/           # recursos de documentación, incluido el logo
├── scripts/          # setup.ps1, run.ps1 y backups locales
├── docs/             # documentación técnica y operativa
├── openspec/         # especificaciones y cambios
└── manage.py
~~~

## Puesta en marcha local

### Requisitos

Python 3.12.x, PowerShell 7+, Git y uv.

Crea un archivo .env en la raíz (las rutas son un ejemplo; usa cualquier
directorio fuera del repositorio):

~~~dotenv
SECRET_KEY=reemplazar-por-un-secreto-largo-y-aleatorio
DEBUG=True
DB_PATH=C:/AeroControl_Data/db/aero_ops.sqlite3
DOCUMENTS_DIR=C:/AeroControl_Data/documents
LOGS_DIR=C:/AeroControl_Data/logs
# DOCUMENTS_ANTIVIRUS_COMMAND=clamscan
# DB_ENGINE=postgresql
# DB_NAME=aerocontrol
# DB_USER=aerocontrol
# DB_PASSWORD=reemplazar
# DB_HOST=127.0.0.1
# DB_PORT=5432
~~~

Clona e instala:

~~~powershell
git clone https://github.com/DovaCrii/AeroControl.git
Set-Location AeroControl
powershell -ExecutionPolicy Bypass -File ./scripts/setup.ps1
./.venv/Scripts/python.exe manage.py createsuperuser
powershell -ExecutionPolicy Bypass -File ./scripts/run.ps1
~~~

Abre http://127.0.0.1:8000/. El setup instala dependencias bloqueadas, compila
traducciones, aplica migraciones, inicializa roles y crea configuraciones
iniciales de cumplimiento.

## Comandos operativos

~~~powershell
uv run python manage.py check
uv run python manage.py check --deploy
uv run pytest --cov=apps --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run bandit -q -c pyproject.toml -r apps config
uv run pip-audit

powershell -ExecutionPolicy Bypass -File ./scripts/backup.ps1
uv run python manage.py verify_backup <ruta-al-backup.sqlite3>
uv run python manage.py restore_backup <backup.sqlite3> <destino.sqlite3>

# Snapshot local de base + documentos (fuera del repositorio)
$env:AEROCONTROL_BACKUP_ROOT='D:/AeroControl-Backups'
powershell -ExecutionPolicy Bypass -File ./scripts/backup-local.ps1
powershell -ExecutionPolicy Bypass -File ./scripts/verify-local-backup.ps1 `
  -Snapshot 'D:/AeroControl-Backups/aerocontrol_YYYYMMDD_HHMMSS'
powershell -ExecutionPolicy Bypass -File ./scripts/restore-local.ps1 `
  -Snapshot 'D:/AeroControl-Backups/aerocontrol_YYYYMMDD_HHMMSS' `
  -DestinationRoot 'D:/AeroControl-Restore-Drill/YYYYMMDD'
powershell -ExecutionPolicy Bypass -File ./scripts/register-backup-task.ps1 `
  -DestinationRoot 'D:/AeroControl-Backups' -DayOfWeek Sunday -At '18:00'

uv run python manage.py cleanup_documents --older-than-days 3650
uv run python manage.py cleanup_documents --older-than-days 3650 --execute
~~~

Cada respaldo incluye un manifiesto JSON con origen, fecha, tamaño y hash SHA-256.
La restauración verifica el manifiesto y no sobrescribe destinos existentes salvo
que se indique force.

## Operación programada

Tres trabajos deben ejecutarse solos: `generate_alerts` (detecta vencimientos y
crea sus tareas de seguimiento), `send_alert_digest` (envía el resumen por
correo a cada responsable de centro de costo) y `backup`. Cada ejecución queda
registrada en `JobRun`, así que se puede comprobar después si corrieron.

~~~powershell
# Registrar los tres trabajos diarios en el Programador de tareas de Windows
./scripts/schedule_tasks.ps1 -EnvFile "C:/AeroControl_Data/.env"

# Horas personalizadas / desregistrar
./scripts/schedule_tasks.ps1 -AlertsAt "06:30" -DigestAt "07:15" -BackupAt "22:00"
./scripts/schedule_tasks.ps1 -Unregister

# Probar el resumen sin enviar correo
uv run python manage.py send_alert_digest --dry-run
~~~

`-EnvFile` es necesario porque una tarea programada no hereda las variables de
la sesión interactiva. El destinatario del resumen es el **Operador responsable**
del centro de costo, o su **Contacto externo** (nombre y correo) cuando el
responsable no está en el padrón de operadores — un administrador, secretaría o
un SSO; si no hay ninguno, el comando lo informa y continúa con los demás. Sin
`EMAIL_HOST` configurado el correo se imprime en consola en lugar de enviarse.

El equivalente en cron para Linux y el detalle completo están en
[docs/scheduled-operations.md](docs/scheduled-operations.md).

## Seguridad y cumplimiento

### Autenticación y permisos

- Las páginas operativas requieren autenticación y permisos de modelo según la operación.
- Las exportaciones CSV respetan el mismo límite de autorización.
- La búsqueda no devuelve entidades sin permiso de vista.
- KanbanBoardAccess soporta roles visor, editor y gestor por tablero (aplicado en la API).
- OperationalTenant y TenantMembership ofrecen un límite multi-organización **opcional y aún no estricto**: se aplica en Workboard, asignaciones y calendario, no en todas las vistas de detalle/lista. Endurecerlo es un bloque prioritario ([MASTER_PLAN.md](MASTER_PLAN.md), FASE 2-3).

### Auditoría y monitoreo

- /health/ informa el estado de la base y del almacenamiento; responde 200 si está saludable y 503 si está degradado.
- Cada respuesta incluye X-Request-ID.
- Las solicitudes se registran como JSON lines en LOGS_DIR sin cuerpos ni credenciales.
- Las modificaciones autenticadas quedan en AuditEvent append-only y se revisan desde Django Admin.

### Cargas de archivos

- Se aceptan PDF, DOCX, XLSX, PNG, JPG, JPEG, KMZ y KML hasta 20 MB.
- Se valida la firma real, se normaliza la ruta y se usa un archivo temporal.
- El antivirus se integra mediante DOCUMENTS_ANTIVIRUS_COMMAND, por ejemplo clamscan.

### Endurecimiento web

- Content-Security-Policy-Report-Only se emite según CSP_REPORT_ONLY (modo report-only; el enforcing todavía no está disponible — ver [MASTER_PLAN.md](MASTER_PLAN.md), T2.5).
- SortableJS está fijado con SRI y crossorigin. Las demás dependencias de front (Bootstrap, HTMX, Chart.js, FullCalendar) se cargan por CDN y aún no llevan SRI (bloque T5.9).

### API y reportes

- La API de tareas está en /api/v1/workboard/tasks/ y exige autenticación y permiso de vista.
- PATCH en /api/v1/workboard/tasks/<uuid>/ exige permiso de cambio y rechaza cambios cruzados no permitidos.
- If-Unmodified-Since evita sobrescrituras obsoletas y responde 409 ante conflictos.
- Existen reportes Kanban CSV, XLSX y Word.
- La documentación OpenAPI está disponible para usuarios autenticados.

### Límites conocidos

SQLite y los archivos cargados son locales: la aplicación no los replica ni cifra
automáticamente. El respaldo y el control de acceso al directorio de datos son
responsabilidad del operador.

## Carga del Capítulo 1

La correspondencia canónica está documentada en docs/chapter1-import.md y puede
consultarse con:

~~~powershell
uv run python manage.py chapter1_mapping --json
~~~

Valida y exporta el documento oficial DOCX fuera del repositorio:

~~~powershell
uv run python manage.py chapter1_docx_import --source "C:/ruta/1 Capítulo 1 202607_R16.docx" --cost-centers "C:/AeroControl_Data/imports/20260723_centros_costo.csv" --export-dir "C:/AeroControl_Data/imports/chapter1-YYYYMMDD"
~~~

Revisa el informe JSON y los duplicados antes de aplicar:

~~~powershell
uv run python manage.py chapter1_docx_import --source "C:/ruta/1 Capítulo 1 202607_R16.docx" --cost-centers "C:/AeroControl_Data/imports/20260723_centros_costo.csv" --apply
~~~

La carga no inventa relaciones con centros de costo. Si la fuente no trae esa
relación, aeronaves y operadores quedan pendientes y
validate_operational_data informa unassigned_cost_center.

La fuente vigente revisada contiene 14 aeronaves y 50 fichas permanentes. La
carga local incorporó 11 centros de costo, 14 aeronaves y 41 operadores sin
conflicto. Se consolidó un duplicado exacto y cuatro grupos contradictorios
quedaron pendientes de confirmación.

## Flujo operativo Kanban

La vista de tablero está en /workboard/, la lista en /workboard/list/ y el
calendario unificado en /calendar/.

- Las etapas son la fuente de verdad del estado.
- Las etiquetas están acotadas a un tablero.
- Las tareas admiten checklists y progreso calculado.
- El detalle se abre en un panel lateral.
- El archivado es reversible.
- El arrastre se desactiva cuando los filtros hacen ambiguo el orden.
- El calendario cruza permisos, mantenimiento y vencimientos Kanban.

## Estado y próximos pasos

Completado:

- UI en español con cambio ES/EN, tema claro/oscuro y panel lateral contraíble.
- Formularios con controles de fecha y hora; Kanban Tablero, Lista y Calendario.
- Centro de administración operativo e importación validada del Capítulo 1 vigente.
- Notificaciones y operación programada (`generate_alerts`, resumen por correo,
  informe ejecutivo semanal, respaldos), con registro en `JobRun`.
- **FASE 0 (estabilización) cerrada** y una **revisión completa de seguridad,
  estabilidad, desempeño y UX** (V.1–V.39): scoping del Workboard, throttling del
  endpoint de token, SQLite en WAL, atomicidad alerta⇄tarea, N+1 e índices,
  archivar/restaurar desde la UI, y zona horaria coherente (America/Santiago).
- Estáticos con hash de contenido en producción (WhiteNoise) y catálogo de
  traducciones vigilado por un test de deriva.
- Suite de ~308 pruebas con Ruff, Bandit, pip-audit y CI (cobertura ~89%).

> **El seguimiento vivo del trabajo pendiente vive en [MASTER_PLAN.md](MASTER_PLAN.md)**
> (tablero de bloques, con estado, prioridad y criterio de aceptación). La
> auditoría técnica que lo respalda está en [AUDIT_CLAUDE.md](AUDIT_CLAUDE.md).

Próximas prioridades (ver el detalle y el orden en el plan maestro):

- **Cargar datos reales de cumplimiento** — documentos con vencimiento y una
  regla de alerta; el dashboard guía los tres pasos. Es lo que enciende el
  resumen diario y el informe ejecutivo, hoy construidos pero sin datos.
- **BLOQUE GEO — editor geoespacial KMZ/KML** (en curso): la capa de datos ya
  está construida y probada —parser endurecido, formato canónico, generador con
  round-trip verificado, modelos con versiones inmutables e importación desde la
  UI—; falta el editor de mapa interactivo (isla JavaScript con Leaflet). Diseño
  y estado en [docs/dev/geo-editor-plan.md](docs/dev/geo-editor-plan.md).
- **Endurecimiento diferido:** tenancy estricto (aislamiento por organización en
  todas las vistas), CSP enforcing y vendorización con SRI de las dependencias
  de front.
- **Operación:** modelar habilitaciones DGAC con vigencia, evidencia y alertas.
- **Diferido (YAGNI):** PostgreSQL en producción, DJI Cloud API y telemetría.

La frontera frontend está documentada en docs/frontend-boundary.md. Una SPA
separada queda postergada; el editor geoespacial será una **isla JavaScript**
acotada (módulos ES sin build) dentro del shell server-rendered, no una SPA.

El plan de backend local-first y el runbook de snapshots están en
`docs/dev/06-Plan-Local-First.md`, `docs/dev/backend-plan.md` y
`docs/dev/local-backup.md`. La raíz de `docs/` queda solo con documentación
de producto (`SECURITY.md`, `chapter1-import.md`, `frontend-boundary.md`,
`postgresql-readiness.md`); notas internas y bitácoras de desarrollo viven
en `docs/dev/`.

## Licencia

MIT. Ver LICENSE.
