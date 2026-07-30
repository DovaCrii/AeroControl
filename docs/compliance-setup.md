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

## Paso 2 — Tipos de documento

Crea los `DocumentType` que uses, con vencimiento activado. Se adjuntan a la
entidad que corresponda:

| Tipo de documento | Se adjunta a | Vence |
| --- | --- | --- |
| Credencial DGAC | Operador | Sí |
| Certificado médico / aptitud | Operador | Sí |
| Registro / matrícula de aeronave | Aeronave | Sí |
| Certificado de aeronavegabilidad | Aeronave | Sí |
| Seguro de responsabilidad civil | Aeronave o centro de costo | Sí |
| Autorización DGAC (carta de permiso) | Permiso de vuelo | Sí |

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

Las **dos primeras** cubren lo esencial. Deja *crear tarea Kanban* apagado al
inicio; si luego lo activas, siembra antes el tablero con `init_dgac_board`.

## Paso 4 — Cargar documentos

Sube documentos con **fecha de vencimiento real**, colgando del operador /
aeronave / permiso correspondiente. Eso es lo que las reglas vigilan.

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
