<div align="center">

<img src="assets/aerocontrol-mark.svg" width="140" height="105" alt="Logo de AeroControl" />

# AeroControl

**Centro de operaciones para equipos RPA/UAS: flota, tripulación, cumplimiento y vuelo, en un solo lugar.**

[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-2EC4B6.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-1B2A4A.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-6.0-1B2A4A.svg)](https://www.djangoproject.com/)
[![Estado](https://img.shields.io/badge/estado-v0.5.0--beta-2EC4B6.svg)](#estado-actual)

Aplicaciones hermanas: **[AeroLink](https://github.com/DovaCrii/AeroLink)** (telemetría y evidencia de vuelo) · **[AeroPlanner](https://github.com/DovaCrii/AeroPlanner)** (planificación de misiones) — funcionan por separado, se comunican cuando conviene

</div>

---

## Qué es

AeroControl reemplaza las planillas sueltas por un solo sistema donde viven la
flota, los operadores, los permisos de vuelo, la documentación con vencimiento
y el trabajo diario del equipo. Es **local-first**: corre en un equipo o
servidor de la organización, con los datos bajo su control, sin depender de un
proveedor externo.

**Para quién.** Jefaturas de operaciones y encargados de cumplimiento que
necesitan saber, sin buscar en tres archivos distintos, qué habilitación vence
la próxima semana, quién puede volar qué aeronave, y si un permiso está al día
con su documentación DGAC.

## Qué resuelve

| Módulo | Qué hace |
| --- | --- |
| **Registro** | Centros de costo, aeronaves, operadores, asignaciones y habilitaciones — con estados visibles (activo, retirado, contrato cerrado) |
| **Cumplimiento** | Documentos con vencimiento, alertas automáticas y resumen diario/semanal por correo |
| **Operaciones** | Permisos de vuelo (folio, vigencia, zona poblada/no poblada) y registro de vuelos realizados |
| **Mantenimiento** | Programada y no programada, con historial de estados |
| **Planificación geoespacial** | Importa y versiona planes de vuelo KMZ/KML; editor interactivo en el mapa |
| **Tablero (Kanban)** | Seguimiento de tareas y alertas en vista tablero, lista y calendario unificado |

Todo con auditoría de cada cambio, permisos por rol y la interfaz completa en
español (con cambio directo a inglés).

## Aplicaciones hermanas

AeroControl es el registro: qué aeronaves y operadores hay, qué está al día y
qué vence. A su lado viven dos aplicaciones **independientes** — cada una con su
propia base de datos y su propio despliegue, ninguna escribe en el dominio de la
otra:

```
        AeroPlanner                AeroControl                 AeroLink
   planifica la misión    →     flota · operadores      ←    lo que pasó al volar
   geometría · terreno          permisos · documentos        telemetría · evidencia
   simulación · KMZ             centros de costo             sesiones con hash
```

- **[AeroPlanner](https://github.com/DovaCrii/AeroPlanner)** planifica y
  visualiza misiones; entrega el KMZ que se vuela. Se comunican por KMZ primero
  y por API después.
- **[AeroLink](https://github.com/DovaCrii/AeroLink)** recoge lo que DJI Pilot 2
  expone durante el vuelo y lo vuelve registro con evidencia verificable.
  Comparte con AeroControl un único contrato HTTP versionado y de sólo lectura,
  el inventario de baterías y payloads que AeroLink masterea — ver
  [docs/dev/plan-integracion-aerolink.md](docs/dev/plan-integracion-aerolink.md).

Las tres comparten la marca —el mismo dron, un motivo distinto por aplicación— y
nada más: **ninguna comparte base de datos con otra**.

## Estado actual

**`v0.5.0-beta`** — desplegada y operando con datos reales de la DGAC (flota,
operadores y centros de costo reales). 1440 pruebas automatizadas, revisadas
con Ruff, Bandit y pip-audit en CI.

El trabajo pendiente vive en dos documentos, no en este README:

- **[MASTER_PLAN.md](MASTER_PLAN.md)** — el tablero de lo que falta, ordenado
  por prioridad, con criterio de aceptación por ítem.
- **[HANDOFF.md](HANDOFF.md)** — el punto exacto de retome para quien siga el
  trabajo: qué se cerró, qué sigue abierto y por qué.

## Puesta en marcha

Requisitos: Python 3.12, PowerShell 7+, Git y [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/DovaCrii/AeroControl.git
Set-Location AeroControl
powershell -ExecutionPolicy Bypass -File ./scripts/setup.ps1
./.venv/Scripts/python.exe manage.py createsuperuser
powershell -ExecutionPolicy Bypass -File ./scripts/run.ps1
```

Abre `http://127.0.0.1:8000/`. El setup instala dependencias, compila
traducciones, aplica migraciones e inicializa los datos base.

Antes de usarlo con datos reales, crea un `.env` — ver
[docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md) para el
despliegue en servidor y [docs/compliance-setup.md](docs/compliance-setup.md)
para activar alertas y resúmenes.

### Comandos frecuentes

```powershell
uv run pytest                          # suite de pruebas
uv run ruff check . && uv run ruff format --check .   # lint y formato
powershell -File ./scripts/backup.ps1  # respaldo con manifiesto verificable
```

El detalle completo de comandos, respaldo/restauración y operación programada
está en [docs/scheduled-operations.md](docs/scheduled-operations.md) y
[docs/dev/backend-plan.md](docs/dev/backend-plan.md).

## Seguridad y datos

- Autenticación y permisos por modelo en cada vista; auditoría append-only de
  toda modificación.
- Cargas de archivos con validación de firma real (PDF, DOCX, XLSX, imágenes,
  KMZ/KML) y antivirus opcional.
- SQLite por defecto (con opción a PostgreSQL); los documentos y respaldos
  viven fuera del repositorio, bajo el control del operador.
- El aislamiento multi-organización (tenancy) y el CSP en modo *enforcing*
  están **avanzados pero no cerrados al 100%** — el detalle exacto está en
  `MASTER_PLAN.md`.

## Licencia

MIT. Ver [LICENSE](LICENSE).
