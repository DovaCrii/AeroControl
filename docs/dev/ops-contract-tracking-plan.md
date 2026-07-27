# Seguimiento de contratos, recursos y permisos (BLOQUE OPS) — propuesta técnica

> **Estado:** propuesta 2026-07-27, **no aprobada / no implementada**. El trabajo
> arranca en `OPS-1` solo con el "go" explícito del usuario. Este documento es la
> fuente de verdad del diseño; el tablero de tareas vive en `MASTER_PLAN.md`
> (sección "BLOQUE OPS").
>
> Nace del feedback de producto del equipo operativo (2026-07-27), contrastado
> con una autorización DGAC real (N°5808, J.E.J. Ingeniería) y la plataforma
> **SIGO** de la DGAC como referencia de lo que el usuario ya conoce.

## Objetivo

Que AeroControl sirva de verdad para **dar seguimiento a un contrato** (centro de
costo): qué personal y qué aeronaves tiene asignados hoy, dónde está físicamente
cada nave, qué permisos de vuelo lo cubren, qué documentos lo respaldan, y —
sobre todo — **un log inmutable de cada movimiento** (reasignación de operador,
traslado de nave, cambio de estado de permiso). Hoy el sistema guarda el estado
actual pero olvida cómo se llegó a él; el equipo pide trazabilidad.

No es rehacer la app: es cerrar las brechas entre el modelo actual y cómo opera
realmente una empresa RPAS bajo DGAC.

## Brechas detectadas (modelo actual vs. realidad operativa)

| Necesidad del equipo | Estado hoy | Archivo |
|---|---|---|
| Permiso con **varios** operadores y aeronaves (la autorización 5808 lista 4 operadores y 2 naves) | `FlightPermission` con FK único a un operador y una aeronave | `apps/operations/models.py:8` |
| Permiso con **rango de vigencia** (18/07→18/09) | `flight_date` fecha única | `apps/operations/models.py:20` |
| Ubicación estructurada (región, comuna, faena, coordenadas) | `location` texto libre 250 chars | `apps/operations/models.py:21` |
| Log de movimiento de personal/aeronaves y reasignaciones | `Assignment` es un par operador+aeronave, sin historial | `apps/registry/models.py:151` |
| Anclar la asignación al **centro de costo** (no al operador), N naves por centro | `cost_center` opcional; una nave por fila | `apps/registry/models.py:164` |
| Ficha del contrato (equipo asignado, flota, permisos, historial) | El centro de costo es una fila de lista, sin detalle | `apps/registry/views.py` |
| Ubicación física de la nave (casa matriz / faena / mantenimiento) | `Aircraft.status` mezcla estado operativo, sin ubicación | `apps/registry/models.py:75` |
| Log de asociación plan geo ↔ permiso, con fechas | FK `SET_NULL` sin registro de cuándo | `apps/geo/models.py:45` |
| Historiales **separados por entidad** | — (SIGO los mezcla todo junto; es justo lo que el usuario critica) | — |
| Cartas Word/PDF asociadas al permiso | `Document` genérico ya lo soporta; falta la UI | `apps/compliance/models.py` |

## Investigación — cómo lo resuelven los competidores

Referencias de mercado (RPAS/UAS fleet management, 2026), para adoptar patrones
probados y descartar los que no aplican a la realidad DGAC/Chile:

- **[Aloft](https://www.aloft.ai/tag/drone-fleet-management-software/)** —
  *Fleet Overview Dashboard* con estado de cada aeronave y asignación de pilotos;
  *Team Management* para asignar misiones y monitorear actividad. **Adoptar:** el
  tablero de flota con estado+ubicación por nave y la vista de equipo por
  contrato. **Descartar:** su integración LAANC (autorización de espacio aéreo
  automática de la FAA) — en Chile la autorización es el trámite manual DGAC/SIGO.
- **[DroneLogbook](https://www.dronelogbook.com/)** — foco en cumplimiento y
  reportes por operación, amplio soporte de formatos de archivo. **Adoptar:** la
  idea de adjuntar documentos heterogéneos (las cartas Word/PDF) al registro que
  corresponde.
- **[Airdata UAV](https://www.webfactoryltd.com/blog/4-drone-fleet-management-saas-tools-that-track-flight-logs-and-maintenance/)** —
  seguimiento por aeronave/piloto y agenda de mantenimiento a partir del log de
  vuelo. **Adoptar:** el cruce nave ↔ mantenimiento ↔ ubicación como un solo hilo
  de vida del equipo.

Denominador común: **cada recurso (nave, piloto) tiene una línea de tiempo
propia**; el estado actual es solo la última entrada de esa línea. Eso valida el
diseño de logs append-only por entidad de abajo.

Fuentes: [Aloft](https://www.aloft.ai/tag/drone-fleet-management-software/) ·
[DroneLogbook](https://www.dronelogbook.com/hp/1/index.html) ·
[Airdata (webfactory)](https://www.webfactoryltd.com/blog/4-drone-fleet-management-saas-tools-that-track-flight-logs-and-maintenance/) ·
[SafetyCulture — Best Drone Management Software 2026](https://safetyculture.com/apps/drone-management-software)

## Decisiones tomadas (2026-07-27, confirmadas por el usuario)

| Decisión | Elección | Motivo |
|---|---|---|
| Prioridad | Escribir la propuesta ahora; **GEO-6 sigue su curso**; OPS no se implementa sin go | No frenar el bloque GEO en marcha |
| Modelo de asignación | **Separado por recurso**: operador→CC y aeronave→CC, cada uno con fechas y log | Un operador rota de contrato sin arrastrar una nave; N naves por CC sin duplicar operadores |
| Permiso de vuelo | **Espejo DGAC**: rango de vigencia + multi-operador + multi-aeronave + ubicación estructurada | La autorización real (5808) es así; hoy no cabe |
| Fuente de verdad del vínculo recurso↔contrato | La **asignación vigente**; `Operator.cost_center`/`Aircraft.cost_center` quedan como denormalización que mantiene una señal | Un solo lugar decide, el resto lee |
| Logs | Append-only, patrón `AuditEvent`/`PermissionHistory`, señal en `apps/core/signals.py` | Ya es la convención del repo; nunca se borra, se archiva |

## 1. Modelo propuesto

### 1.1 Asignaciones por recurso (reemplazan `Assignment`)

```python
class OperatorAssignment(BaseModel):     # uuid, created/updated, is_active
    operator     FK(Operator, PROTECT, related_name="cc_assignments")
    cost_center  FK(CostCenter, PROTECT, related_name="operator_assignments")
    start_date; end_date (null)          # end_date null = vigente
    status       planned|active|ended|cancelled
    purpose      CharField(blank)
    índice: (cost_center, is_active), (operator, end_date)

class AircraftAssignment(BaseModel):
    aircraft     FK(Aircraft, PROTECT, related_name="cc_assignments")
    cost_center  FK(CostCenter, PROTECT, related_name="aircraft_assignments")
    start_date; end_date (null); status; purpose
    índice: (cost_center, is_active), (aircraft, end_date)
```

- **Regla de negocio (en `clean()` + constraint):** no dos asignaciones activas
  solapadas para el mismo recurso; `end_date >= start_date`; recurso `is_active`.
- **Fuente de verdad:** una señal `post_save`/`post_delete` recalcula
  `Operator.cost_center` / `Aircraft.cost_center` desde la asignación vigente (la
  de `end_date` nulo más reciente). Los campos FK actuales **se conservan** como
  denormalización de solo lectura para las vistas y el calendario que ya los usan.

### 1.2 Log de movimientos — `ResourceMovementLog`

Un solo modelo append-only para operador y aeronave (evita dos tablas gemelas):

```python
class ResourceMovementLog(BaseModel):    # append-only (manager como AuditEvent)
    RESOURCE = operator | aircraft
    MOVEMENT = assigned | reassigned | released | location_changed | status_changed
    resource_kind; resource_id (uuid)    # apunta a Operator o Aircraft
    movement
    from_cost_center FK(CostCenter, SET_NULL, null)
    to_cost_center   FK(CostCenter, SET_NULL, null)
    detail           CharField           # ej. "casa matriz → faena Chuquicamata"
    changed_by_user  FK(user, SET_NULL, null); created_at
    índice: (resource_kind, resource_id, -created_at)
```

Lo escribe la misma señal que mantiene la denormalización: toda alta, cierre o
reasignación deja rastro. Es el "log de movimiento de documentación y asignación
de personal" que pide el equipo.

### 1.3 Ubicación física de aeronaves (distinta de `status`)

`Aircraft.status` (active/maintenance/retired) describe la **condición**; la
ubicación es **dónde está**:

```python
# en Aircraft
current_location  headquarters | on_site | maintenance   # denormalizado
current_site      FK(CostCenter, SET_NULL, null)          # faena si on_site
```

Los cambios de ubicación entran por `ResourceMovementLog` (`location_changed`),
con badge visual claro y distinguible (color por ubicación) en listas, ficha de
contrato y tablero de flota. Referencia visual: el badge de vencido de SIGO
(punto rojo) — mismo lenguaje visual, aplicado a ubicación y a vigencias.

### 1.4 `FlightPermission` espejo DGAC

```python
# FlightPermission — cambios
operators      M2M(Operator, through=PermissionOperator)   # varios
aircraft_fleet M2M(Aircraft,  through=PermissionAircraft)   # varias
valid_from; valid_until (null)          # rango DGAC; migra flight_date→valid_from
# ubicación estructurada (opcional, además del texto libre que se conserva)
region; commune; area_name              # "Área industrial Mina Chuquicamata"
latitude; longitude; radius_km; max_altitude_ft
```

- Through-models con `PROTECT` (convención de FKs operativos).
- `operator`/`aircraft` FK actuales **se conservan** por compatibilidad y se
  llenan con el primero de cada M2M (denormalización); la migración de datos crea
  la primera fila M2M desde los FK existentes.
- La ubicación estructurada no reemplaza `location`: lo complementa, y habilita
  el cruce con la planificación geoespacial (mismo punto/área que el KMZ).

### 1.5 Adjuntos del permiso (cartas Word/PDF)

`compliance.Document` **ya es genérico** (`content_type`/`object_id`, igual que
GEO-4 lo usa para el KMZ fuente). No requiere modelo nuevo: solo
- un `DocumentType` dedicado (`FLIGHT_PERMISSION_LETTER`), y
- UI de adjuntar/listar/descargar en el detalle del permiso, reutilizando el
  pipeline de subida endurecido (firmas + antivirus, `apps/compliance/security.py`).

### 1.6 Vínculo plan geo ↔ permiso con log

Registrar en un evento de historial (extensión del patrón `GeoPlanHistory` o un
`AuditEvent` dedicado) **cuándo** se asocia/desasocia `GeoPlan.flight_permission`
y desde qué fecha, para el seguimiento pedido en planificación geoespacial.

## 2. Vistas nuevas

### 2.1 Ficha del contrato — `CostCenterDetailView` con pestañas

Referencia: la pantalla SIGO "Editar Empresa" (Información / Personal Operativo /
Aeronaves / Historial), **pero corrigiendo su defecto**: el historial de SIGO
mezcla aeronaves, permisos y operadores en una sola tabla. Aquí van **separados**:

- **Resumen** — datos del contrato, responsable, conteos.
- **Equipo** — operadores asignados vigentes, con vigencia de credenciales y
  badge de vencido (como SIGO).
- **Flota** — aeronaves asignadas + ubicación actual (badge) + estado.
- **Permisos** — permisos de vuelo que cubren el contrato, por vigencia.
- **Documentos** — documentos colgados del centro de costo.
- **Historial** — timeline de movimientos del contrato (`ResourceMovementLog`
  filtrado por CC), no un volcado global.

### 2.2 Timelines por entidad (`OPS-6`)

Operador, aeronave, permiso y contrato: cada uno con su línea de tiempo propia,
reutilizando `ResourceMovementLog`, `PermissionHistory`, `AuditEvent`. Nunca un
historial global mezclado.

### 2.3 Dashboard (`OPS-8`)

- **Filtro global por centro de costo** en el panel de operaciones.
- Pase de mejoras visuales: jerarquía tipográfica, fuentes y densidad de la UI
  actual (cruzar con `docs/frontend-boundary.md` y los tokens de `app.css` —
  ojo con las dos generaciones de tokens stackeadas, ver hazards del repo).

## 3. Contrato de permisos y lectura (obligatorio)

Toda vista nueva respeta `AGENTS.md`:
- Vistas de lectura → `view_*` explícito + scope por tenant si aplica; prueba 403.
- Vistas mutantes → `add_*`/`change_*`; validación en `clean()`/constraint **y**
  formulario; auditoría vía `set_audit_context`.
- FKs operativos `PROTECT`; nada se borra, se archiva (`is_active=False`).
- Logs con manager append-only (mismos 4 cerrojos que `AuditEvent`).

## 4. Migraciones de datos (riesgo principal)

Tres migraciones de datos, cada una idempotente y con prueba de regresión:
1. `Assignment` → `OperatorAssignment` + `AircraftAssignment` (misma fecha/CC);
   el modelo viejo se marca deprecado, no se borra.
2. `FlightPermission.operator/aircraft` → primera fila de cada M2M; `flight_date`
   → `valid_from`.
3. `Aircraft.current_location` inicial = `headquarters` para todas.

Regla: ninguna migración destruye dato operativo; ante duda, se conserva y se
deja constancia en el PR.

## 5. Tablero (en MASTER_PLAN)

`OPS-0` (esta propuesta) .. `OPS-8`. Orden y dependencias en `MASTER_PLAN.md`.
Cada tarea: rama `codex/ops-N`, migración con nombre descriptivo + test de
constraint, 403 por vista nueva, strings al catálogo `es`, cobertura ≥83,
`verify.ps1` verde.

## 6. Riesgos

1. **Migración de datos de producción** — el usuario tiene 14 aeronaves y 41
   operadores reales cargados. Mitigación: migraciones idempotentes, backup
   previo (`scripts/`), pruebas con copia de `aero_ops.sqlite3`.
2. **Denormalización que se desincroniza** — la señal es el único escritor de
   `Operator.cost_center`/`Aircraft.cost_center`; prueba de que una reasignación
   actualiza ambos.
3. **Alcance** — el bloque es grande; se entrega tarea por tarea, cada una
   desplegable, empezando por OPS-1 (el log, que es el pedido central).
4. **Deuda F-08 (tenancy incompleta)** — las vistas nuevas por contrato tocan el
   scope por tenant; no ampliar el hueco, acotarlo donde se pueda.

## Verificación (al implementar cada tarea)

- `uv run pytest` — modelos (constraints de solape, denormalización), señales
  (el log se escribe), vistas (403 por rol), migraciones de datos (regresión).
- Navegador: ficha de contrato con equipo/flota/permisos/historial reales sobre
  la instancia demo (`aerocontrol-demo`, :8011), nunca sobre la BD real sin backup.
- Gate existente completo (`scripts/verify.ps1`).
