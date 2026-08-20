# Configuración inicial del monitoreo de cumplimiento

Guía para dejar operativo el monitoreo de vencimientos en una operación RPAS
bajo DGAC. Complementa la importación de datos ([chapter1-import.md](chapter1-import.md))
y la operación programada ([scheduled-operations.md](scheduled-operations.md)).

El monitoreo tiene tres piezas: **documentos con fecha de vencimiento**,
**reglas de alerta** que los vigilan, y **destinatarios** por centro de costo
que reciben el resumen. `generate_alerts` crea las alertas (y opcionalmente
tarjetas Kanban); `send_alert_digest` envía el resumen agrupado.

## Qué se puede vigilar

Una `AlertRule` vigila un **modelo + un campo de fecha** (o el `status`), no un
tipo de documento. Los modelos vigilables y sus campos útiles:

| Entidad (`entity_type`) | Campo (`field_to_watch`) | Qué vence |
| --- | --- | --- |
| `compliance.document` | `expiry_date` | Cualquier documento con vencimiento |
| `operations.flightpermission` | `valid_until` | Vigencia del permiso de vuelo DGAC |
| `registry.qualification` | `expiry_date` | Habilitaciones del operador |
| `maintenance.maintenancerecord` | `scheduled_date` | Mantenimiento programado |

> **La credencial DGAC del operador se vigila como `Document`, no como campo del
> operador.** `Operator.dgac_credential` es texto, no una fecha; el vencimiento
> se modela cargando la credencial como documento con `expiry_date`. (El modelo
> dedicado de habilitaciones es B4.3 en el MASTER_PLAN, diferido.)

## Paso 1 — Destinatarios por centro de costo

En cada centro de costo (`/registry/costcenter/<id>/edit/`) define quién recibe
el resumen:

- **Operador responsable** si es alguien del padrón (usa su correo), o
- **Contacto externo** (nombre + correo) si es un administrativo/SSO ajeno al
  padrón RPA.

Si ambos existen se prefiere el operador; el contacto externo se usa cuando el
operador no tiene correo o quedó archivado. Un CC con vencimientos pero sin
destinatario se informa y el digest continúa con los demás.

Para ver de una vez qué centros de costo **aún no tienen destinatario alcanzable**
(sin esperar a que haya vencimientos), corre el reporte de preparación:

```bash
uv run python manage.py check_digest_recipients
```

Lista cada CC activo como `OK`/`MISSING` con el motivo, y un resumen. Es de solo
lectura y usa la misma lógica (`CostCenter.notification_email`) que el digest.

## Paso 2 — Tipos de documento

```bash
uv run python manage.py seed_document_types
```

Siembra el catálogo estándar (idempotente, no duplica si ya corriste antes):

| Tipo de documento | Se adjunta a | Vence | Otro |
| --- | --- | --- | --- |
| Credencial DGAC | Operador | Sí | — |
| Certificado médico / aptitud | Operador | Sí | — |
| Registro / matrícula de aeronave | Aeronave | **No** | LV-121: el "Certificado del Registro Nacional de RPA" de la DGAC **no trae fecha de término**. Exigirla obligaba a inventar un vencimiento, y esa fecha inventada después generaba alerta |
| Certificado de aeronavegabilidad | Aeronave | Sí | — |
| Seguro de responsabilidad civil | Aeronave o centro de costo | Sí | `is_insurance` (LV-4: su vencimiento aparece como columna en la lista de aeronaves) |
| Solicitud de aprobación de seguro RPA (a la JAC) | Aeronave | No | LV-121: el formulario que va **a** `segurosjac@jac.gob.cl`. Par con la fila siguiente, igual que la carta y la autorización DGAC (LV-64) |
| Resolución Exenta JAC (aprueba seguro RPA) | Aeronave | Sí | LV-117: el papel con que la JAC aprueba la póliza, y que **vuelve**. **No** lleva `is_insurance` — la fecha canónica del seguro es `Aircraft.insurance_expiry` (LV-29) |
| Autorización DGAC (carta de permiso) | Permiso de vuelo | Sí | — |

Si necesitas un tipo adicional, créalo desde la app (`/compliance/documenttype/new/`).

**Elige bien la categoría** (LV-95). Es lo que agrupa el selector de tipo en las
pantallas de carga —*documentos del personal*, *de la aeronave*, *presentaciones
y autorizaciones DGAC*, *registros operacionales*, *mantención y calibración*,
*documentos de la empresa*— y un tipo sin categoría queda bajo **"Otro"**, que es
donde nadie lo va a buscar. Los tipos del catálogo estándar ya vienen
clasificados, incluidos los de instalaciones que existían antes de LV-95 (la
migración `compliance/0019` los clasifica por su `code`).

## Paso 3 — Reglas de alerta

**Una sola regla sobre `compliance.document` / `expiry_date` cubre todos los
tipos de documento de arriba**, porque la regla vigila el campo, no el tipo. Y
como el digest ya agrupa en *vencidos / 7 / 15 / 30 días*, **no hace falta una
regla por umbral**: con 30 días alcanza.

Conjunto recomendado:

| Nombre de la regla | `entity_type` | `field_to_watch` | `days_before_expiry` |
| --- | --- | --- | --- |
| Documentos por vencer | `compliance.document` | `expiry_date` | 30 |
| Permisos de vuelo por vencer | `operations.flightpermission` | `valid_until` | 30 |
| Habilitaciones por vencer *(opcional)* | `registry.qualification` | `expiry_date` | 30 |
| Mantenimiento programado *(opcional)* | `maintenance.maintenancerecord` | `scheduled_date` | 15 |

Siembra las **dos esenciales** de una vez (idempotente por nombre, igual que
`seed_document_types`):

```bash
uv run python manage.py seed_alert_rules
```

Agrega `--with-optional` para sembrar también las dos opcionales
(habilitaciones y mantenimiento). El comando deja la creación *automática* de
tarea Kanban apagada al inicio (el flag `create_kanban_task` de cada regla).

Un rerun no duplica ni pisa reglas que hayas ajustado en la UI. También puedes
crear o afinar reglas a mano desde `/compliance/alertrule/`.

> **No corras `init_dgac_board`** (LV-78, 2026-08-13). El tablero se **dio de
> baja** el 2026-08-12 y hoy está congelado: sin menú, sin botones, sin gráfico
> en el panel, sin carril en el calendario y fuera del buscador. El comando sigue
> existiendo, pero **recrearía justo lo que se está retirando**, así que también
> se sacó del procedimiento de despliegue.

> **La creación automática de tarjetas salió del formulario de reglas** (LV-78).
> Ya no se puede encender desde la interfaz. Una regla que **ya** la tenía
> encendida sigue funcionando igual, y `generate_alerts` la nombra en su salida
> para que se vea. Para saber si hay alguna en producción:
>
> ```bash
> uv run python manage.py shell -c "from apps.compliance.models import AlertRule; print(list(AlertRule.objects.filter(create_kanban_task=True).values_list('name', flat=True)))"
> ```

## Cómo se resuelve una alerta

**La regla de oro: arreglar el dato primero, resolver después.**

`generate_alerts` corre a diario (06:00) y crea una alerta por cada registro en
ventana. **Sólo evita duplicar contra alertas abiertas**, así que:

> Resolver una alerta cuya condición sigue vigente la hace **reaparecer a la
> mañana siguiente**. No es un defecto — impide barrer un vencimiento bajo la
> alfombra — pero explica por qué "Resolver" puede parecer que no funciona.

**Se cierran solas, sin tocar la alerta:**

| Acción | Mecanismo |
|---|---|
| Actualizar la vigencia a una fecha fuera de riesgo (seguro JAC, credencial DGAC, habilitación, permiso) | Señal de LV-71 — deja el motivo *"Vigencia renovada al AAAA-MM-DD (cierre automático)"* |
| Reemplazar un documento por una versión nueva | `Document.resolve_related_alerts` |
| Completar una mantención | `resolve_open_alerts_for` |
| Firmar la revisión mensual | `resolve_open_alerts_for` |
| Completar la tarjeta del tablero | señal de R6.1 |

**Flujo normal, ejemplo con un seguro JAC vencido:**

1. Renovar la póliza con la aseguradora.
2. Ficha de la aeronave → **Editar** → actualizar "Vencimiento seguro JAC".
3. **Listo**: la alerta se cierra sola y queda registrado por qué.

**Cuándo hay que resolver a mano** (`/compliance/alert/` → "Resolver", con
motivo obligatorio): cuando la alerta se cierra por una razón que **no** es una
fecha nueva — se dio de baja la aeronave, la alerta se generó por un dato
equivocado, o se decidió aceptar el riesgo con justificación. Ahí el motivo lo
escribe una persona, que es justo lo que ISO 10.2 pide para esos casos.

**Si borrás la fecha en vez de renovarla**, la alerta **queda abierta** a
propósito: una vigencia ausente es un estado peor que una por vencer.

Todo cierre es reversible con **Deshacer**, que limpia el motivo y reabre.

## Paso 4 — Cargar documentos

Sube documentos con **fecha de vencimiento real**, colgando del operador /
aeronave / permiso correspondiente. Eso es lo que las reglas vigilan.

### Dónde vive cada documento

Cada documento se sube **desde la ficha de la entidad a la que pertenece**, no
desde una bandeja suelta — así el expediente queda completo en un solo lugar:

| Documento | Dónde subirlo |
| --- | --- |
| Carta / autorización DGAC de un permiso | Ficha del **permiso de vuelo** → "Subir documento" |
| Área de vuelo (KMZ/KML) | *Planificación geoespacial* → **Importar** (elige el CC y el permiso); queda listada en la ficha del permiso |
| Resolución JAC, registro/matrícula, aeronavegabilidad, seguro | Ficha de la **aeronave** → "Subir documento" |
| Credencial DGAC, certificado médico del operador | Ficha del **operador** → "Subir documento". Al renovar, usa **Reemplazar**: guarda el histórico y la versión vigente es la que se vigila |
| AOC de la empresa, procedimientos, checklists, plantillas | **Documentos de la empresa** (sidebar *Cumplimiento* o el botón del panel) |
| Documentos del contrato/centro de costo | Ficha del **centro de costo** → pestaña *Documentos* |

El tipo de documento se elige del catálogo (Paso 2); crea los que falten
(p. ej. "Resolución JAC", "Procedimiento interno") desde
`/compliance/documenttype/new/`. Todo documento con **fecha de vencimiento**
queda vigilado por la regla de alertas, sin importar a qué entidad cuelga.

### Registros operacionales y cierre mensual (LV-30)

Los **registros por vuelo** —bitácora (REG-015), checklist RPA (LVE-003),
inspección de dron (LVE-002)— son otra categoría: no vencen, pero deben existir
uno por vuelo. No se confunden con los procedimientos (esos van a *Documentos de
la empresa*) ni con la resolución JAC (esa va a la ficha de la aeronave).

- **Dónde viven**: *Cumplimiento → Registros operacionales*
  (`/compliance/operational-records/`). Se cuelgan de un **centro de costo** con
  la **fecha del vuelo** como fecha de emisión; se filtran por CC, mes y tipo, y
  se suben con "Subir registro" (prellena el CC elegido).
- **Cierre de mes**: el comando `check_monthly_records` (timer diario, actúa el
  último día del mes) crea una **revisión de cumplimiento** pendiente por cada
  centro de costo que voló y avisa al grupo **Dirección** con la tabla vuelos vs
  registros. Cada revisión pendiente es una **alerta viva** hasta que Dirección
  la marca **Cumple** o **No cumple** en *Cumplimiento → Cumplimiento mensual*
  (`/compliance/monthly-review/`, con export CSV). Marcarla cierra la alerta.
- **Quién revisa**: solo el grupo *Dirección* (permiso
  `change_monthlycompliancereview`); el resto la ve en modo lectura.

## Paso 5 — Probar

En la VM (con el entorno cargado):

```bash
uv run python manage.py generate_alerts
uv run python manage.py send_alert_digest --dry-run
```

`--dry-run` imprime destinatarios y conteos sin enviar. Con datos cargados,
`generate_alerts` debe reportar alertas > 0 y el digest, a quién llegaría.

## Paso 6 — Correo real

Sin `EMAIL_HOST` en el entorno se usa el backend de consola: el resumen se
imprime en el log en vez de enviarse. Configura `EMAIL_*` (ver `.env.example`)
para envío real. Nunca se versionan credenciales SMTP.

## Paso 7 — Dejar que corra solo

Programa `generate_alerts` y `send_alert_digest` (y el respaldo) según
[scheduled-operations.md](scheduled-operations.md). En la VM `p340` ya quedaron
como *systemd timers* (alerts 06:00, digest 07:00, backup 22:00).
