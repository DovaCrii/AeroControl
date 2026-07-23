<div align="center">

<img src="assets/aerocontrol-mark.svg" width="160" height="120" alt="Logo de AeroControl" />

# AeroControl

**Centro de operaciones local para equipos RPA/UAS**

Registro de flota, tripulación, cumplimiento normativo, mantenimiento y flujo de trabajo operativo en una aplicación Django local-first.

[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-2EC4B6.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-1B2A4A.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-6.0-1B2A4A.svg)](https://www.djangoproject.com/)
[![Estado](https://img.shields.io/badge/estado-alpha%20%2F%20estabilización%20activa-orange.svg)](#estado-y-próximos-pasos)

</div>

---

## Tabla de contenidos

- [Qué es AeroControl](#qué-es-aerocontrol)
- [Qué incluye](#qué-incluye)
- [Arquitectura y estructura](#arquitectura-y-estructura)
- [Puesta en marcha local](#puesta-en-marcha-local)
- [Comandos operativos](#comandos-operativos)
- [Seguridad y cumplimiento](#seguridad-y-cumplimiento)
- [Carga del Capítulo 1](#carga-del-capítulo-1)
- [Flujo operativo Kanban](#flujo-operativo-kanban)
- [Estado y próximos pasos](#estado-y-próximos-pasos)
- [Licencia](#licencia)

## Qué es AeroControl

AeroControl centraliza la operación de equipos RPA/UAS: flota, operadores,
habilitaciones, documentos, permisos de vuelo, mantenimiento, alertas y trabajo
Kanban.

> **Estado:** alpha y estabilización activa. Es apto para evaluación local
> controlada. Antes de producción se requiere una política de respaldos,
> antivirus, retención de datos y control de accesos.

## Qué incluye

| Área | Alcance actual |
| --- | --- |
| Registro | Centros de costo, responsables, aeronaves, operadores, asignaciones y cualificaciones |
| Cumplimiento | Documentos, tipos, alertas y reglas de vencimiento |
| Operaciones | Permisos de vuelo, historial y registros de vuelo |
| Mantenimiento | Registros programados/no programados e historial de estados |
| Tablero | Kanban, Lista y Calendario; etapas, etiquetas, checklists, prioridades y responsables |
| Administración | Centro operativo y Django Admin técnico separado |
| Seguridad | Autenticación, permisos, auditoría, aislamiento y cargas seguras |
| Localización | Español por defecto y cambio directo ES/EN |

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
├── scripts/          # setup.ps1, run.ps1 y backup.ps1
├── docs/             # documentación técnica y operativa
├── openspec/         # especificaciones y cambios
└── manage.py
~~~

## Puesta en marcha local

### Requisitos

Python 3.12.x, PowerShell 7+, Git y uv.

Crea un archivo .env en la raíz:

~~~dotenv
SECRET_KEY=reemplazar-por-un-secreto-largo-y-aleatorio
DEBUG=True
DB_PATH=D:/I+D/AeroOpsDesk_Data/db/aero_ops.sqlite3
DOCUMENTS_DIR=D:/I+D/AeroOpsDesk_Data/documents
LOGS_DIR=D:/I+D/AeroOpsDesk_Data/logs
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

uv run python manage.py cleanup_documents --older-than-days 3650
uv run python manage.py cleanup_documents --older-than-days 3650 --execute
~~~

Cada respaldo incluye un manifiesto JSON con origen, fecha, tamaño y hash SHA-256.
La restauración verifica el manifiesto y no sobrescribe destinos existentes salvo
que se indique force.

## Seguridad y cumplimiento

### Autenticación y permisos

- Las páginas operativas requieren autenticación y permisos según la operación.
- Las exportaciones CSV respetan el mismo límite de autorización.
- La búsqueda no devuelve entidades sin permiso de vista.
- KanbanBoardAccess soporta roles visor, editor y gestor por tablero.
- OperationalTenant y TenantMembership ofrecen un límite multi-organización opcional.

### Auditoría y monitoreo

- /health/ informa el estado de la base y del almacenamiento; responde 200 si está saludable y 503 si está degradado.
- Cada respuesta incluye X-Request-ID.
- Las solicitudes se registran como JSON lines en LOGS_DIR sin cuerpos ni credenciales.
- Las modificaciones autenticadas quedan en AuditEvent append-only y se revisan desde Django Admin.

### Cargas de archivos

- Se aceptan PDF, DOCX, XLSX, PNG, JPG y JPEG hasta 20 MB.
- Se valida la firma real, se normaliza la ruta y se usa un archivo temporal.
- El antivirus se integra mediante DOCUMENTS_ANTIVIRUS_COMMAND, por ejemplo clamscan.

### Endurecimiento web

- Content-Security-Policy-Report-Only se controla con CSP_REPORT_ONLY.
- SortableJS está fijado con validación SRI y crossorigin.

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
uv run python manage.py chapter1_docx_import --source "D:/ruta/1 Capítulo 1 202607_R16.docx" --cost-centers "D:/I+D/AeroOpsDesk_Data/imports/20260723_centros_costo.csv" --export-dir "D:/I+D/AeroOpsDesk_Data/imports/chapter1-YYYYMMDD"
~~~

Revisa el informe JSON y los duplicados antes de aplicar:

~~~powershell
uv run python manage.py chapter1_docx_import --source "D:/ruta/1 Capítulo 1 202607_R16.docx" --cost-centers "D:/I+D/AeroOpsDesk_Data/imports/20260723_centros_costo.csv" --apply
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

- UI en español con cambio ES/EN.
- Tema claro/oscuro y panel lateral contraíble.
- Formularios con controles de fecha y hora.
- Kanban Tablero, Lista y Calendario.
- Centro de administración operativo.
- Importación validada del Capítulo 1 vigente.
- 116 pruebas automatizadas verdes en la base de modernización.

Próximas prioridades:

- Resolver los cuatro grupos de operadores duplicados.
- Asignar oficialmente aeronaves y operadores a centros de costo.
- Modelar habilitaciones DGAC con vigencia, evidencia y alertas.
- Añadir compatibilidad operador-aeronave antes de autorizar vuelos.
- Ejecutar ensayo real de PostgreSQL cuando exista servidor y datos de despliegue.

La frontera frontend está documentada en docs/frontend-boundary.md. Una SPA
separada queda postergada hasta que existan requisitos de API independiente,
uso offline o clientes móviles.

## Licencia

MIT. Ver LICENSE.
