# ADR-0002: Coexistencia AeroControl ↔ AeroLink

**Estado:** Aceptado (contrato definido, implementación por fases — bloque `X` de `MASTER_PLAN.md`)
**Fecha:** 2026-08-07
**Decisor:** usuario (dueño del producto)
**Contraparte:** [`DovaCrii/AeroLink`](https://github.com/DovaCrii/AeroLink) y su ADR-0001

---

## Contexto

AeroLink es un gateway independiente que recibe datos de DJI Pilot 2 por HTTPS/MQTTS,
reconstruye sesiones de vuelo y conserva telemetría y evidencia con hash SHA-256. Está
en fase M0 (scaffold).

Su ADR-0001 decidió **separación total**: repositorio y despliegue propios, sin
modificar, consumir ni sincronizar con AeroControl, y con la integración futura
declarada explícitamente fuera de alcance.

El motivo por el que existe es concreto y vale registrarlo: **extraer los datos del RPA
sin depender de que el operador los escriba**, porque la evidencia escrita a mano no
siempre es confiable. Eso lo convierte, a futuro, en la fuente natural de dos cosas que
la auditoría ISO 7.1.3 exige y que hoy AeroControl no puede sostener: **horas de vuelo
por aeronave y ciclos de batería**.

El problema es que "sin integración de ningún tipo" ya está costando:

- **Inventario duplicado.** AeroLink modela `Device`/`DeviceTopology` (aeronaves,
  controles, payloads, baterías). AeroControl ya tiene las 16 aeronaves reales con su
  centro de costo, su seguro y su documentación DGAC. Sin contrato, en M2 ("registro de
  topología y seriales") nacen dos inventarios divergentes de los mismos drones.
- **Dos identidades.** AeroLink usa Microsoft Entra ID; AeroControl usa cuentas Django
  locales. Para las mismas ~8 personas, son dos logins.
- **Ninguna llave compartida definida.** AeroLink dice que "cada sesión conserva un
  identificador externo inmutable para permitir una integración futura", pero no dice
  externo *a qué*.

## Decisión

**Las dos aplicaciones siguen separadas en repositorio y despliegue. Lo que cambia es
que el contrato entre ellas deja de estar sin definir.**

### 1. La separación se mantiene, y las razones del ADR-0001 de AeroLink se sostienen

No se fusionan. Meter un consumidor MQTT permanente dentro de un monolito Django sobre
SQLite sería un retroceso real: la ingesta es continua y asíncrona, DJI exige ingreso
público con credenciales propias, y una falla de ingesta no debe voltear el sistema
operacional que hoy usa la operación todos los días.

**Se prohíbe explícitamente:** compartir base de datos, y que un sistema lea el
filesystem del otro.

### 2. `Aircraft.serial_number` es la llave de cruce

Es la única llave presente en los **tres** mundos:

- la **reporta DJI** nativamente en el enlace con Pilot 2;
- está **embebida en el repositorio documental** (`Z:\01-116 OPERACIONES_RPA_JEJ`, con
  carpetas `CC{centro}-{serie}-{modelo}`, p. ej. `CC633-1581F5FHC245700D181D-M3E`);
- es lo que **registra la DGAC** en el certificado RPAS de cada aeronave.

Hoy el campo es `CharField(max_length=100, blank=True)`: opcional, no único y sin
normalizar. Debe pasar a ser obligatorio, único y normalizado.

**Estado real verificado en producción el 2026-08-07** (16 aeronaves, todas con serial
poblado), cruzado contra las 16 carpetas de `Z:`:

| Situación | Cuántas | Detalle |
|---|:--:|---|
| Calce exacto | 11 | — |
| Espacio espurio en la app | 2 | `RPA-4401` y `RPA-4436` traen un espacio a mitad del serial |
| Discrepancia de carácter | 2 | `RPA-4647`: `B00D` (app) vs `BOOD` (carpeta) — confusión `O`/`0`. `RPA-4884`: `1581…` (app) vs `1582…` (carpeta) |
| Centro de costo distinto | 1 | `RPA-2019`: la app dice CC110, la carpeta dice CC717 |
| Sin contraparte en `Z:` | 1 | `RPA-2198` (Wingtra ONE GEN2, serial `2832`, sin centro de costo) — no es DJI |
| Carpeta sin aeronave | 1 | `CC633/1581F5FHD231500C2Z48` ("M3E Revisión") |

**Consecuencia operativa:** la unicidad **no** se impone de entrada. Primero se
normaliza (quitar espacios, mayúsculas), luego se resuelven las 4 discrepancias
**contra el certificado RPAS de la DGAC** —que es la fuente autoritativa, no la app ni
el nombre de carpeta— y recién entonces se agrega la constraint. Ver `X.1`.

Nota: la aeronave Wingtra no es DJI y nunca aparecerá por AeroLink. El contrato no debe
asumir que todo el padrón es alcanzable por telemetría.

### 3. Quién es maestro de qué

| Dominio | Maestro | El otro sistema |
|---|---|---|
| Aeronaves, operadores, centros de costo | **AeroControl** | AeroLink lee, no escribe |
| Permisos de vuelo, documentos, vigencias, alertas | **AeroControl** | AeroLink no participa |
| Telemetría, sesiones de vuelo, evidencia con hash | **AeroLink** | AeroControl recibe, no escribe |
| Inventario de baterías y payloads | **AeroLink** (lo ve DJI) | AeroControl lo refleja para ISO 7.1.3 |

Ninguno escribe en el dominio del otro.

### 4. Cómo se comunican

Contratos versionados sobre HTTP, en la red interna de `p340`. Nada de acceso directo a
datos.

- **Fase 1 (`X.3`) — implementada 2026-08-11.** AeroControl expone el padrón como
  endpoint **de solo lectura**: `GET /api/v1/registry/aircraft/` (lista) y
  `.../<uuid>/` (detalle), con `?serial=<serial>` como la búsqueda que AeroLink
  realmente usa — tiene un serial de DJI y necesita la aeronave que le
  corresponde. Detalles del contrato:
  - **Solo lectura de verdad**: no hay ruta de escritura que proteger. Un
    superusuario recibe `405` en POST/PUT/PATCH/DELETE, así que esto no se puede
    "aflojar" después repartiendo un permiso.
  - **Serial exacto, nunca parcial**: un prefijo que calce atribuiría telemetría
    a la aeronave equivocada, peor que no resolverla. El valor entrante se
    normaliza igual que `Aircraft.save()` (sin espacios, X.1), así el llamador no
    tiene que saber esa regla.
  - **Campos mínimos**: matrícula, serial, fabricante, modelo, tipo, estado y
    centro de costo. Las fechas de seguro, pesos, VLOS y el resto de la ficha
    **no se exponen** — son asunto de cumplimiento de AeroControl, no de un
    gateway de telemetría, y cada campo expuesto es un campo que hay que
    mantener funcionando para un consumidor externo.
  - **Acotado por tenant y por permiso** (`view_aircraft`), igual que las vistas
    HTML: un token no es un bypass de ninguno de los dos. Verificado en ambos
    sentidos (un miembro del otro tenant ve lo suyo y no lo ajeno), y que la
    búsqueda por serial tampoco cruza el límite.
  - **Throttle propio** (`padron`, 120/min por defecto): generoso para un
    consumidor máquina que puede recuperar un lote tras un corte, pero con techo
    para que un bucle de reintentos del otro lado no sature la app operacional
    que comparte la VM.
  Reusó la infraestructura existente (DRF, token auth, throttling): fue un scope
  nuevo, no una aplicación nueva, como este ADR anticipaba.
- **Fase 2 (`X.4`)** — AeroLink entrega sesiones de vuelo cerradas; AeroControl las
  concilia con `FlightRecord`. Es el punto donde el proyecto paga: las horas de vuelo y
  los ciclos de batería dejan de depender de la planilla del operador.

  **Estado real de AeroLink, verificado el 2026-08-12** leyendo el repo
  (`D:\I+D\AeroLink`, `main` sin divergencia con `origin/main`, commit `d05abe1`):

  - Está en **M0** (descubrimiento y viabilidad). Las sesiones de vuelo son
    **M3** (`AL-301`…`AL-306`); faltan M1 (plataforma) y M2 (DJI Pilot 2)
    completos. Su propio README lo dice: *"no se integra con AeroControl
    todavía"*.
  - El modelo `FlightSession` **ya existe** (`src/aerolink/models.py`), pero
    **no hay endpoint que lo exponga**: `main.py` sólo publica `/health`,
    `/ready`, `/metrics`, `/pilot2/diagnostic` y `/api/v1`.
  - Bloqueo declarado por ellos: `p340` se expone por Tailscale Funnel, que
    sirve HTTPS pero **no MQTTS (8883)**; sin resolverlo, M1 no avanza.

  **Conclusión: `X.4` no se puede implementar todavía**, y no por falta de
  trabajo de este lado — no existe aún de dónde leer. Construir el receptor
  ahora significaría inventar el contrato de un productor que todavía no tomó
  sus decisiones, que es exactamente lo que este ADR evitó para la Fase 1.

  **Tres huecos del contrato que se ven ya en el modelo real**, y que conviene
  cerrar *antes* de que AeroLink construya el endpoint:

  1. **La sesión no lleva el serial**, lleva `aircraft_device_id` (FK interna a
     `Device`). La llave de cruce acordada es el **serial** (§2), así que el
     endpoint debe exponer el serial del dispositivo, no su UUID interno: un
     UUID de AeroLink no es resoluble desde AeroControl.
  2. **No hay llave de cruce para el piloto.** La sesión trae `pilot_subject`
     (identidad Entra); AeroControl identifica al operador por `employee_id`.
     §2 resolvió la llave de la aeronave y **dejó ésta sin definir**. Sin ella,
     una sesión se puede atribuir a una aeronave pero no a quién la voló.
  3. **"Sesión cerrada" no está definida.** `FlightSession.status` es texto
     libre con default `"detected"`; el contrato dice "sesiones cerradas" sin
     decir qué valor lo significa. Hay que fijar el vocabulario, del mismo modo
     que `R3.1` cerró el de `purpose`.

  Además, `summary_json` no está tipado: si de ahí salen las horas de vuelo y
  los ciclos de batería, esas claves son parte del contrato y no un detalle de
  implementación del otro lado.

La conciliación **no** es sustitución: un `FlightRecord` tiene datos que DJI no conoce
(el permiso de vuelo bajo el que se voló, el propósito). La sesión de AeroLink aporta la
medición; AeroControl aporta el encuadre normativo.

## Consecuencias

**A favor:**

- Un solo padrón. Las 16 aeronaves se mantienen en un lugar y AeroLink las resuelve por
  serial.
- Horas de vuelo y ciclos de batería quedan con un camino real hacia la evidencia
  automática (ISO 7.1.3), que es el motivo por el que AeroLink existe.
- La separación de fallas se conserva: si la ingesta se cae, AeroControl no se entera.

**En contra / costos aceptados:**

- AeroLink queda con una dependencia de red hacia AeroControl para resolver seriales.
  Mitigación: cachear el padrón localmente y degradar a "dispositivo desconocido" en vez
  de rechazar telemetría — **una sesión de vuelo nunca se descarta por no poder resolver
  la aeronave**; se guarda con el serial crudo y se concilia después.
- Hay que normalizar los seriales antes de que sirvan de llave (`X.1`).

**Pendientes que este ADR abre y no cierra:**

- **Identidad** (`X.5`): Entra ID vs cuentas Django para las mismas personas. O
  AeroControl migra, o AeroLink acepta un modo local, o se convive con dos logins.
- **Retención**: AeroLink promete 5 años para evidencia y 90 días para telemetría
  detallada. AeroControl no tiene política de retención escrita.
- **Respaldo**: AeroLink irá a la **misma VM** cuyo respaldo nunca se restauró. Hereda
  el riesgo (prioridad #1 de `MASTER_PLAN.md`) y lo agrava, porque promete conservar
  evidencia con valor probatorio a 5 años.
- **PostgreSQL**: AeroLink lo levanta en `p340`. La migración de AeroControl desde
  SQLite estaba diferida por costo; con Postgres ya en la VM, esa decisión merece
  reabrirse — un solo motor y un solo respaldo.

## Alternativas descartadas

**Fusionar las dos aplicaciones.** Rechazada: pondría un consumidor MQTT 24/7 dentro de
un monolito Django request/response sobre SQLite, acoplaría el ciclo de vida de un
sistema experimental al de uno en producción diaria, y haría que una falla de ingesta
DJI pudiera dejar sin sistema a la operación.

**Seguir sin contrato hasta que AeroLink madure.** Rechazada: el costo no es futuro, es
inmediato. M2 de AeroLink construye el registro de topología y seriales; si arranca sin
saber que AeroControl es el maestro del padrón, nace el segundo inventario y después
hay que reconciliarlos con datos ya acumulados — exactamente el error que la auditoría
técnica original marcó sobre la tenancy (F-08: "barato ahora, irrecuperable con datos
acumulados").

**Que AeroControl consuma directamente la base PostgreSQL de AeroLink.** Rechazada por
el ADR-0001 de AeroLink y correctamente: acopla esquemas y convierte cualquier
migración de un lado en una rotura del otro.

---

*Relacionado:* `MASTER_PLAN.md` → bloque `X`; `docs/auditoria-iso-trazabilidad.md`
(cláusula 7.1.3); ADR-0001 de AeroLink.
