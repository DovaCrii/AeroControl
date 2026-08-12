# Plan de integración AeroControl ↔ AeroLink

**Fecha:** 2026-08-12
**Estado:** propuesta, pendiente de aprobación del usuario y de AeroLink.

## Por qué existe este documento

No es burocracia: **es una precondición escrita en el repo de AeroLink**.

> `AeroLink/AGENTS.md`: *"La integración con AeroControl está fuera de alcance
> **hasta crear un plan separado** en su propio repositorio."*

Y el ADR-0001 de AeroLink dice dónde debe vivir:

> *"La futura integración se diseña como un proyecto aparte en
> `DovaCrii/AeroControl`, con contratos versionados y sin compartir base de
> datos."*

Este documento es ese plan. Mientras no exista y se apruebe, cualquier trabajo
de integración del lado de AeroLink **viola su propia guía de trabajo**.

El **diseño técnico** del contrato ya está resuelto en
[ADR-0002](adr-0002-coexistencia-aerolink.md); acá no se repite, se planifica su
ejecución.

## Qué está hecho y qué no (verificado 2026-08-12)

| Fase | Qué | Estado |
|---|---|---|
| `X.1` | `serial_number` como llave única de cruce | ✅ AeroControl |
| `X.3` | Padrón de aeronaves como API de sólo lectura | ✅ AeroControl |
| `X.4b` | **Baterías**: consumidor + contrato | ✅ AeroControl · ✅ **productor implementado** (rama `codex/api-inventario-dispositivos`, pendiente de PR) |
| `X.4c` | Normalización de seriales alineada con el ADR §2 | ✅ AeroControl |
| `X.4` | **Sesiones de vuelo**: conciliación con `FlightRecord` | ⬜ Bloqueado |

**AeroLink está en M0.** Su `FlightSession` existe como modelo pero ningún
endpoint lo expone, y su bloqueo declarado es de red (Tailscale Funnel sirve
HTTPS pero no MQTTS/8883, sin lo cual M1 no avanza).

## Lo que este plan pide, en orden

### 1. ~~Endpoint de inventario~~ — **implementado el 2026-08-12**

Está en la rama `codex/api-inventario-dispositivos` de AeroLink, **pendiente de
PR** (su `main` está protegido y exige uno). Incluye lo que su `AGENTS.md` exige
para toda API nueva: autenticación (token de servicio, `ADR-0003`), autorización
(*allowlist* de `kind`; pedir aeronaves responde `403` citando `AL-R4`),
auditoría (el primer escritor de `AuditEvent` del repo) y 51 pruebas.

**Verificado de punta a punta el 2026-08-12**: levantado local, AeroControl
sincronizó 2 baterías **contra el endpoint real** y enlazó una a `RPA-2002` por
número de serie. Con token equivocado y sin URL, el comando falla ruidosamente
en vez de reportar cero.

El detalle de lo que sigue vale como registro de por qué se pidió así:



**Es lo único que falta para que las baterías funcionen de punta a punta.** El
consumidor está implementado y probado en AeroControl (`sync_batteries`), y el
contrato está escrito en el ADR-0002. Los datos ya están modelados en AeroLink
(`Device` con `kind="battery"` y `serial_number` único).

```
GET /api/v1/devices/?kind=battery
```

Requisitos que impone el propio `AGENTS.md` de AeroLink —*"Toda API nueva
requiere autenticación, autorización, auditoría y pruebas"*— así que **no es un
endpoint trivial**: token, alcance por workspace, registro en `AuditEvent` y
pruebas. Estimación honesta: pequeño comparado con M2/M3, no de una tarde.

**No está en su plan maestro.** `AL-203` cubre el registro de topología y
seriales y `AL-304` un dashboard de inventario; ninguno publica una API para un
consumidor externo. **Es un ítem nuevo que hay que agregarles.**

### 2. Cerrar los 3 huecos del contrato de sesiones (antes de construir nada)

Detectados leyendo su modelo real, detallados en el ADR-0002:

1. **La sesión no lleva el serial**, lleva `aircraft_device_id` (UUID interno).
   La llave acordada es el serial: un UUID de AeroLink no es resoluble desde
   AeroControl.
2. ~~**No hay llave de cruce para el piloto.**~~ **Resuelto 2026-08-12**: el
   `employee_id`, guardado por AeroLink junto a su `pilot_subject` de Entra
   (ver "Decisiones ya tomadas").
3. **"Sesión cerrada" no está definida.** `FlightSession.status` es texto libre
   con default `"detected"`.

Cerrarlos cuesta una conversación; descubrirlos después de que ambos lados
construyeron cuesta rehacer los dos.

### 3. Sesiones de vuelo (`X.4`) — sólo cuando AeroLink llegue a M3

Depende de M1 y M2 completos, y de que su bloqueo de red esté resuelto. **No
tiene sentido empezarlo antes**: escribir el receptor ahora sería inventar el
contrato de un productor que aún no decidió, que es exactamente lo que el
ADR-0002 evitó para la Fase 1.

## Decisiones ya tomadas (2026-08-12)

- **La llave del piloto es el `employee_id`, y lo guarda AeroLink.** Cierra el
  hueco 2 del contrato de sesiones. Motivo: carga el trabajo en quien **ya**
  consulta el padrón por `X.3` — pide el operador y guarda su `employee_id`
  junto a la identidad Entra. La alternativa (que `Operator` guarde el `subject`
  de Entra) obligaría a un modelo del padrón a saber de un sistema de identidad
  que hoy no toca, y a que alguien mantenga ~8 valores sincronizados a mano.
  **No prejuzga `X.5`**: es una llave de cruce, no una decisión de federación.
- **Se agrega el endpoint de inventario al plan de AeroLink** como `AL-107`.

## Decisiones que siguen abiertas (usuario)

- **`X.5` (identidad)**: son ~8 personas en dos sistemas de cuentas. Decidir si
  se unifican vale más que cualquier automatización de sincronización.
- **PostgreSQL**: AeroLink lo instala en la misma VM. Reabrir la decisión de
  motor con un ADR propio significaría un motor y un respaldo en vez de dos.

## Precondición del primer sync real (X.4c, hecho 2026-08-12)

Explorar ambos repos destapó un defecto cruzado que habría fallado **en
silencio**: el ADR-0002 §2 manda normalizar el serial a *mayúsculas y sin
espacios*, y AeroControl sólo implementaba la mitad de los espacios. Con AeroLink
normalizando como dice el ADR, un serial con minúsculas dejaba de calzar en el
`filter(serial_number=...)` exacto: la batería nunca encontraba su aeronave, y
una batería cargada a mano se duplicaba en vez de actualizarse.

Corregido: `normalize_serial()` compartida por `Aircraft.save()`,
`Battery.save()`, el padrón `X.3` y el sync. Hay migración de datos
(`registry/0032`) que **se niega a correr si dos seriales sólo difieren en
mayúsculas** — la columna es única y cuál es el correcto lo dice el certificado
RPAS de la DGAC, no una migración. `manage.py audit_serial_case` los lista.

**Antes del primer sync contra datos reales hay que correr ese comando en
`p340`.** Cambiar `save()` no reescribe filas ya guardadas.

## Lo que este plan NO propone

- **Compartir base de datos.** Descartado en ambos ADR y no se reabre.
- **Que AeroControl escriba en AeroLink.** El flujo es de lectura: AeroLink es
  maestro de telemetría y baterías, AeroControl del padrón y el cumplimiento.
- **Sustituir `FlightRecord` por sesiones.** La sesión aporta la medición;
  AeroControl aporta el encuadre normativo (bajo qué permiso se voló, con qué
  propósito), que DJI no conoce.

---

*Relacionado:* [ADR-0002](adr-0002-coexistencia-aerolink.md) (contrato técnico),
`AeroLink/docs/adr/0001-standalone-boundary.md` (por qué están separados),
`AeroLink/docs/MASTER_PLAN.md` (sus milestones M0–M4).
