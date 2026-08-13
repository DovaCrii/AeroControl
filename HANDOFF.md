# HANDOFF — AeroControl

> **Resumen de estado, no bitácora.** La historia detallada vive en `git log`,
> `CHANGELOG.md` y las filas del tablero. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) → sección **"Rumbo a 1.0"**.
> Si este archivo vuelve a crecer a cientos de líneas de cierres de ventana,
> podarlo: se hizo el 2026-08-11 (de 900 a ~110) y el contenido no se perdió,
> se movió a donde correspondía.

## Estado al 2026-08-12

- **Versión:** `v0.5.0-beta` (etiquetada). `main` = `origin/main` (pusheado
  2026-08-12).
- **Gate:** `pwsh scripts/verify.ps1` verde (1095 tests, ruff, bandit, pip-audit).
- **Desplegado en `p340` el 2026-08-12** ✅. Las 7 migraciones aplicaron limpio
  (`registry.0031`/`0032`, `operations.0016`, `compliance.0015`/`0016`/`0017`,
  `geo.0004`), `bootstrap_roles` corrió, y los 2 timers nuevos quedaron
  habilitados — **son 10**. Respaldo previo tomado **y verificado**
  (`aero_ops_20260812_182936`).
- **`audit_serial_case` en producción: limpio** — 16 aeronaves, cero seriales en
  minúscula, cero colisiones. Por eso `registry.0032` no tuvo nada que
  normalizar; si hubiera habido una colisión, esa migración aborta a propósito y
  frena el `migrate` entero.
- **Bloques completos:** R1, R2, R3, R5, R6 · **R7 completo salvo el IPER
  estructurado de R7.5** · R8.1-R8.2 · X.1-X.3.
- **Parcial:** R4 (importador listo, `--apply` nunca corrido).
- **AOC cargado en producción** ✅ (2026-08-11, por el usuario).
- **`p340` al día con `main`** ✅ (2026-08-12, incluye el arreglo P0 de `LV-73`).

### Qué corre solo en `p340`

**8 timers de systemd**, todos verificados corriendo: `alerts` (06:00),
`digest` (07:00), `credentials` (07:30), `executive` (lunes 07:30),
`backup` (22:00), `snapshot` (23:00), `monthly` (23:30, último día del mes),
`monthly-deadline` (08:00, día 15).

Verificar: `systemctl list-timers 'aerocontrol-*' --no-pager`

Notificaciones a `Dirección`: `aortega@jej.cl` + `cmunoz@jej.cl`.

## Pendientes inmediatos — empezar por acá

**1. Cargar 10 vigencias que faltan (LV-74).** Es lo único con impacto de
cumplimiento hoy. **No es un bug** — se verificó contra el respaldo que nunca
estuvieron cargadas. Importa porque **un `NULL` no genera alerta** (decisión
correcta de LV-29: un nulo significa "nunca se ingresó"), así que estos 10 son
invisibles para las alertas, el calendario y el reporte: el hueco no se anuncia.

- Sin `insurance_expiry` (seguro JAC): `RPA-2019`, `RPA-3696`, `RPA-7126`.
- Sin `credential_expiry` (credencial DGAC): René Herrera Molina, Natalia Ramos
  Mora, Jimmy Patricio Andrade Muñoz, David Vidal Vidal, Jose Luis Ogalde
  Henríquez, Luis Piña Tapia, Alberto Jesus Angel Milla.

Se cargan desde la ficha de cada aeronave/operador, o re-corriendo
`load_dgac_vigencias` con una captura completa.

**2. Dos variables que faltan en `/etc/aerocontrol.env`.** Las dos son código ya
desplegado que **no se ve hasta activarlas**:

- ~~**`WEATHER_ENABLED=True`**~~ — **activado el 2026-08-12 y funcionando en
  `p340`**. Ojo para el futuro: la tarjeta sólo aparece si el plan geo tiene
  **área** y un **permiso enlazado con fecha**; sin eso no hay día que consultar,
  y la ausencia se lee como un despliegue fallido.
- **`CSP_REPORT_ONLY=False`** — CSP a *enforcing*, verificado en demo con cero
  violaciones. Criterio de salida de `beta`.

**3. R4, bloqueado del lado del usuario**: corregir 2 nombres de carpeta en `Z:`
(`RPA-4647`, `RPA-4884`) y configurar un antivirus real
(`DOCUMENTS_ANTIVIRUS_COMMAND` está vacío en todos los ambientes) antes de correr
el importador con `--apply`.

**4. ~~Desplegar lo del 2026-08-12.~~ Hecho ese mismo día** — 7 migraciones,
roles y los 2 timers nuevos. Todo lo de esa tanda ya corre en `p340`.

**5. ~~El clima, más visible (`R8.4`).~~ Hecho el 2026-08-13**, con la decisión
del usuario tomada: **(a) faena + (c) centro de costo**, no la geolocalización
del navegador. El panel muestra el clima del próximo vuelo, con temperatura,
viento en **m/s** e icono de la condición del día; el filtro por centro de costo
que ya existía cambia la ubicación. Verificado en el demo contra Open-Meteo real.
**Sin desplegar todavía** — ver abajo.

**6. Lote nuevo del 2026-08-13: `LV-81` y `LV-82` hechos, `LV-83` a `LV-89` capturados.**
El usuario pidió "tomarlo de a poco" e investigar antes de programar, y marcó
`LV-81` (el seguro) como lo clave: **está hecho** — cuatro estados, escalera y
trazabilidad, más el bloqueo que impide marcar "autorizado" sin fecha de
vigencia. Quedó `LV-81b` para el certificado/endoso como registro, que es lo que
se dejó fuera a propósito.

`LV-82` también está hecho: la escalera de mantención dibuja **el camino que el
registro tomó** (casa o taller), decidido por su propio historial, y de paso se
corrigió que el historial mostraba códigos crudos en inglés.

Lo que sigue, con el diagnóstico ya verificado contra el código en cada fila:
cierre automático de permisos vencidos
(`LV-83`, y ojo: *caducado* y *completado* no son lo mismo, mezclarlos rompe un
KPI), la pantalla de carga de documentos (`LV-84`), preview de PDF (`LV-85`,
compatible con la CSP actual porque el archivo es del mismo origen), carga masiva
(`LV-86`), la columna propia de credencial adjunta (`LV-87`), movimientos de
recursos (`LV-88`) y la revisión del panel (`LV-89`, que incluye **un gráfico de
un tablero Kanban dado de baja** todavía dibujándose en producción).

### Estado de la Sesión B (avanzada el 2026-08-12)

| Ítem | Estado |
|---|---|
| Verificación de eficacia (R7.6a) | ✅ Hecho — 30 días, decidido por el usuario |
| Revisión meteorológica como evidencia (R8.2) | ✅ Hecho |
| Los **5** KPI operacionales (R7.7a + R7.7b) | ✅ Hecho — completos. **Sólo la meta de flota (90%) está acordada**; los otros 4 muestran su valor sin marcar incumplimiento |
| Límite de jornada de vuelo (R7.5a) | ✅ Hecho — 8 horas |
| LV-72 (trazabilidad estilo SIGO) | ✅ Hecho — permiso **y** plan geoespacial. La ficha de aeronave se dejó fuera a propósito (su estado no es una progresión) |
| Decidir si el tablero Kanban se elimina | ✅ **Decidido: se da de baja** (usuario, 2026-08-12). Queda la limpieza, ver `LV-78` |

**Con esto la Sesión B está cerrada.** Lo que queda del tablero es limpieza con
migración (`LV-78`), y **no urge**: ya está fuera del menú y sin botones, así que
nadie lo alcanza. Lo que hay que decidir antes de borrar es el alcance — sobre
todo si la migración puede borrar el registro de qué tarjeta cerró qué alerta.

**Lo único que le falta a la cláusula 9.1.1 son las metas restantes** (precisión
de levantamientos, tasa de re-vuelos, cumplimiento de plazos). Son decisiones de
la dirección, no de código: fijarlas es cambiar una constante en
`apps/compliance/kpis.py`, y con eso el indicador empieza a marcar "Bajo la
meta" cuando corresponde.

### La Sesión C ya no está bloqueada por los umbrales

`R7.4` (`Deliverable`) figuraba como "el más bloqueado, sin los umbrales del
contrato no se puede cerrar". **Era un diagnóstico equivocado**, y conviene que
no vuelva: los umbrales viven en el **contrato** (`CostCenter`), no en el
entregable, así que la estructura se construye sin conocerlos y **cada contrato
activa su propio control al cargar los suyos**. Hecho el 2026-08-12.

Lo que sí queda esperando los números reales es el **uso**: mientras un contrato
no tenga umbrales, sus entregables se registran "Sin evaluar" y se pueden
liberar sin control. Cargarlos es un formulario (ficha del centro de costo), no
un cambio de código.

~~Queda de `R7.4`/`R7.6`: **`NonConformity`**.~~ **Hecho el 2026-08-12**: existe
el registro, cerrar exige causa raíz y acción correctiva, y **rechazar un
entregable abre la no conformidad solo**. Con eso **`R7` queda cerrado salvo el
IPER estructurado** (`R7.5`), que el diseño deja último y sólo a pedido
explícito por ser el que más se arriesga a sentirse como burocracia nueva.

**Números que el usuario ya fijó (2026-08-12), para no volver a preguntarlos:**
verificación de eficacia **30 días** (ya implementado como
`Alert.EFFECTIVENESS_DAYS`), meta de disponibilidad de flota **90%**, límite de
jornada de vuelo **8 horas** (R7.5, aún sin implementar).

### AeroLink (Sesión D): verificado el 2026-08-12, **X.4 todavía no se puede**

No por falta de trabajo de este lado. Leyendo el repo (`D:\I+D\AeroLink`,
`main` sin divergencia, `d05abe1`): está en **M0**, las sesiones de vuelo son
**M3**, el modelo `FlightSession` existe pero **ningún endpoint lo expone**, y
su propio README dice que no se integra con AeroControl todavía. Su bloqueo es
de red: Tailscale Funnel sirve HTTPS pero no MQTTS.

Construir el receptor de **sesiones de vuelo** ahora sería inventar el contrato
de un productor que aún no decidió. Quedaron registrados en
[adr-0002](docs/dev/adr-0002-coexistencia-aerolink.md) los **tres huecos del
contrato** que ya se ven en su modelo real — la sesión no lleva el serial (lleva
un UUID interno no resoluble desde acá), **no hay llave de cruce para el
piloto**, y "sesión cerrada" no está definida. Conviene cerrarlos con ellos
*antes* de que construyan el endpoint, no después.

**Pero las baterías sí avanzaron (`X.4b`, hecho).** No dependían de las sesiones:
AeroLink ya modela las baterías como `Device` con serial único. El comando
`sync_batteries` llena `registry.Battery` y **se puede probar hoy** con
`--from-file`; el contrato que esperamos quedó escrito en el ADR.

**Lo que hay que pedirle a AeroLink** es un endpoint que exponga el inventario
de dispositivos. Revisado su plan maestro: **no está** — `AL-203` cubre el
registro de topología y seriales, `AL-304` un dashboard de inventario, pero
ninguno publica una API para un consumidor externo. Es un ítem nuevo para su
plan, y es chico al lado de M2/M3: los datos ya los tienen modelados.

**El plan de integración era una precondición, no una formalidad**: el
`AGENTS.md` de AeroLink dejaba la integración *"fuera de alcance hasta crear un
plan separado"*, y su `ADR-0001` dice que ese plan vive en este repo. Escrito y
aprobado el 2026-08-12:
[docs/dev/plan-integracion-aerolink.md](docs/dev/plan-integracion-aerolink.md).

**Con eso, el endpoint se implementó** (`X.4d`) en la rama
`codex/api-inventario-dispositivos` de AeroLink, **pendiente de PR** — su `main`
está protegido y exige uno. Verificado de punta a punta: AeroControl sincroniza
baterías contra el endpoint real y las enlaza por serial.

**Antes del primer sync contra datos reales**, correr en `p340`:

```bash
uv run python manage.py audit_serial_case
```

`X.4c` alineó la normalización de seriales con el ADR (mayúsculas), pero cambiar
el guardado **no reescribe filas ya almacenadas**. La migración `registry/0032`
las normaliza y **aborta si dos sólo difieren en mayúsculas** — eso lo resuelve
el certificado RPAS de la DGAC, no una migración.

## Sin desplegar: `R8.4` + `LV-81` + `LV-82`

**Tres migraciones, ninguna riesgosa, pero dos tocan datos:**

- `registry/0033` (`R8.4`): dos columnas nulas en `CostCenter`. Sin backfill, sin
  restricción; no puede fallar sobre datos reales.
- `registry/0034` (`LV-81`): amplía las opciones de `insurance_status`, crea
  `InsuranceHistory` y **corrige filas** — las aeronaves que dicen `active` sin
  ninguna fecha de vencimiento pasan a `missing`. En producción eso son las **3
  del pendiente 1** (`RPA-2019`, `RPA-3696`, `RPA-7126`), que hoy se ven
  "Vigente" sin fecha al lado. No toca las marcadas a mano como en trámite.
  Reversible: al revertir vuelven a decir `active`.
- `maintenance/0008` (`LV-82`): agrega `sequence` al historial de mantención y
  **numera las filas existentes** por orden de creación. Sin ese backfill todas
  empatarían en cero y la ficha imprimiría su historial en orden arbitrario.

Ninguna necesita `bootstrap_roles` (no hay permisos nuevos: las transiciones del
seguro usan `change_aircraft`, que ya existe). El `.mo` está recompilado y
versionado, así que no hace falta `compilemessages` en la VM.

**Ojo con lo que no se ve solo:** la tarjeta de clima del panel sólo aparece si
hay un permiso vigente **con coordenadas** o un centro de costo con coordenadas
de faena, y en `p340` hoy probablemente **no hay ninguno** — tras desplegar hay
que cargar al menos una faena para verla, o su ausencia se lee como un despliegue
fallido (igual que pasó con `WEATHER_ENABLED`).

## Despliegue del 2026-08-12 — hecho

Aplicado en `p340` el mismo día. Queda como registro de la secuencia, porque la
próxima tanda con migraciones repite estos pasos:

- Respaldo **y `verify_backup`** antes de migrar. No es ceremonia: eran 7
  migraciones sobre datos reales.
- `manage.py bootstrap_roles` cuando hay permisos nuevos. Sin él las secciones
  nuevas no aparecen en el menú de nadie y parece que el despliegue falló.
- **No correr `init_dgac_board`**, aunque la Parte D del runbook siga
  listándolo: el tablero Kanban se dio de baja (`LV-78`).
- Los timers se agregan con el bloque `mkjob` de
  [docs/scheduled-operations.md](docs/scheduled-operations.md), que es
  autocontenido y hay que pegar entero.
## Cómo desplegar

Secuencia completa y corregida en
[docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md) → Parte D.
Lo esencial y los dos errores que costaron tiempo el 2026-08-11:

- **El merge/push va en Windows** (`D:\I+D\AeroControl`); las ramas sólo existen
  ahí. El **deploy va dentro de la sesión SSH**: `/opt/aerocontrol` es ruta
  Linux y PowerShell la resuelve como `C:\opt\aerocontrol`.
- **El nombre DNS `p340.tailccd107.ts.net` no resuelve bien** (apunta a una IP
  pública ajena). Usar la IP de Tailscale: `ssh levdigital01@100.121.16.118`.
- **`set -a` no es opcional** al cargar el entorno, o `manage.py` cae a
  `config.settings.dev` y muere con `SECRET_KEY not found`:
  ```bash
  cd /opt/aerocontrol && git pull
  set -a; source <(sudo cat /etc/aerocontrol.env); set +a
  echo "settings=$DJANGO_SETTINGS_MODULE  db=$DB_PATH"   # debe decir prod
  uv sync && uv run python manage.py migrate --no-input
  uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
  ```
- Antes de una migración que imponga una restricción, **chequear los datos
  reales primero** con `values_list` (no `.all()`, que hace `SELECT *` de
  columnas que aún no existen). Ejemplo vigente en la Parte D del runbook.
- Tomar un respaldo (`manage.py backup`) y **verificarlo**
  (`verify_backup <ruta>`) antes de migrar.

## Punteros

| Para | Ir a |
|---|---|
| Trabajo pendiente y orden | `MASTER_PLAN.md` → "Rumbo a 1.0" |
| Contrato de trabajo + gotchas verificados | `AGENTS.md` |
| Cómo se resuelve una alerta (operación) | `docs/compliance-setup.md` |
| Diseño de las cláusulas ISO abiertas | `docs/dev/iso-r7-design-plan.md` |
| Contrato con AeroLink | `docs/dev/adr-0002-coexistencia-aerolink.md` |
| Plan de integración con AeroLink | `docs/dev/plan-integracion-aerolink.md` |
| Runbook de la VM | `docs/dev/ubuntu-vm-deploy.md` |
| Trabajos programados | `docs/scheduled-operations.md` |
| Qué cambió y cuándo | `CHANGELOG.md`, `git log` |

## Ramas `claude/*` — resueltas 2026-08-12

Las dos están **cerradas**: lo que valía se rescató a `main` pieza por pieza, no
por merge (son anteriores a los bloques R y `main` ya había reimplementado parte
de su contenido por otro camino). **Ya se pueden borrar.**

| Rama | Qué se hizo |
|---|---|
| `claude/beautiful-curie-4193f1` | **Rescatada** (`9d2c7ba`): huecos de exportación CSV. |
| `claude/amazing-bouman-1b3d09` | **Parcialmente rescatada** (`4cb5dd8`): la ubicación estructurada de `OPS-4` y el barrido de traducciones. Lo demás, descartado. |

Lo descartado, y por qué — para que nadie lo vuelva a "rescatar":

- **Quitar el campo `order` de los formularios Kanban:** `main` ya lo tenía.
- **Pulido visual del onboarding** (rastreador de pasos con badges): `main`
  rediseñó esa sección después con otro lenguaje visual (`LV-D4`, tira de
  pastillas). Aplicarlo sería un retroceso.
- **Su versión de los tests de i18n:** es anterior al soporte de `msgctxt` y
  reportaba como duplicado el par legítimo de `LV-61` ("Registry"); las
  aserciones de `test_detail_labels` esperaban redacciones que `main` ya no usa.

Lección que quedó: **medir antes de rescatar.** Correr los tests de la rama
contra `main` separó en una corrida lo que era hueco real (18 etiquetas en
inglés) de lo que era premisa vencida.
