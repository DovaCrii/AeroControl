# HANDOFF — AeroControl

## 🟡 Plan de mejora en curso — Fases 0 y 1 hechas, la 2 a medias; nada desplegado

El 2026-09-23 el usuario pidió, en cinco mensajes seguidos, marcar lo vencido en
rojo en tres pantallas, revisar el informe mensual y un plan general de mejora. Se
aprobó un plan en cuatro fases, en este orden, con sus decisiones tomadas:

| Fase | Qué | Estado |
|---|---|---|
| **0** | `LV-246`: faenas sin permiso primero y en rojo, «⚠ Caducado» en la lista y ficha de permisos, «⚠ Permiso vencido» en los planes geo, reparto de la lista de permisos | ✅ hecha, **sin desplegar** |
| **1** | Informe: 4 defectos (1a, `LV-247` ✅), más corto (1b, `LV-248` ✅: permisos de producción en **una** hoja, 5 + anexo), **bloques editables** portada/fases/matriz (1c, `LV-249` ✅, **con migración**), **borrador automático el día 1** (1d, `LV-250` ✅ — **falta instalar el timer en `p340`**, bloque en `docs/scheduled-operations.md`), ver cambios entre revisiones (1e, `LV-251` ✅) | ✅ hecha, **sin desplegar** |
| **2** | `LV-252`: los errores en rojo (`MESSAGE_TAGS`), N+1 de mantención, «y N más» real · `LV-253`: una sola marca de vencido (`badge sev-critical` + ⚠) en nueve sitios, y la credencial DGAC vencida en la ficha del operador · `LV-254`: reparto de columnas en planes, vuelos, no conformidades, documentos y mantención (que pasa a la tabla de trabajo compartida), y **el reparto de permisos de la Fase 0 corregido** · alertas quedan fuera del reparto (9 columnas no caben en los anchos del sistema; ya tienen ocultar columnas y filas-tarjeta) | 🟡 hecho eso, **sin desplegar**; faltan las fichas (encabezado único `UX-04`, «Archivar» con peso de acción destructiva, `table-responsive`) |
| **3** | `pytest-xdist` para acortar el gate, tests que dependen del reloj, alinear `AGENTS.md` sobre el squash | ⬜ |

**Decisiones del usuario que acotan la Fase 1**: del informe se recorta **sólo** la
nómina de operadores por permiso (la dotación, los textos fijos y la hoja del plan se
quedan); las plantillas se resuelven con **bloques editables en la app**, no con Word;
y la emisión se automatiza como **borrador el día 1**, sin PDF.

⚠️ **`LV-249` trae migraciones (`reporting.0004` y `0005`)**. El despliegue que la
incluya lleva `migrate`; la `0005` siembra los textos de la portada, las fases y la
matriz, así que después de migrar el informe sale igual que antes. Comprobar con
`showmigrations reporting | tail -3` que las dos quedaron `[X]`.

⚠️ **Lección de la 1b, para no repetirla**: el recorte se le ofreció al usuario con
una premisa que no se había medido ("la nómina es la causa de las hojas de más"), y
con los datos de producción era falsa — sumaba una hoja en vez de quitarla. La
segunda opción que se le recomendó **tampoco** estaba medida. Lo que de verdad
alargaba la tabla era un defecto de CSS (el folio partido). **Antes de ofrecer un
recorte como solución, correr el reparto con la forma real de producción**: son
diez líneas en `manage.py shell` sobre `pagination.paginate`.

⚠️ **Lección de la Fase 2, la misma forma**: el reparto de permisos de `LV-246` se
dio por bueno con el `colspan` exacto y una columna por encabezado, y **la columna
de operadores medía 0 px** — los porcentajes sumaban 90 % más los 110 px de
acciones. Ningún guardián miraba anchos, sólo cuentas. Ahora
`test_lv162_table_column_widths` calcula el sobrante de la columna flexible en
cada lista, desde los anchos de `app.css`.

🔶 **Observado y no diagnosticado**: `test_lv200_step2_the_file_is_reused` falló
**una vez** (dos tests de `TestCleanupDoesNotTakeTheSharedFile`) en una corrida de
`apps/compliance` + `apps/dashboard`, y pasó aislado y en la corrida siguiente de
`apps/compliance` completa. Ninguno de los archivos que toca esta tanda está en su
camino. Usa `cleanup_documents --older-than-days 0`, un borde de reloj que es
**sospecha, no causa comprobada**.

### Pendiente de desplegar ahora

`d5ebac0` (dependencias), `57f8be5` (CI), la Fase 0, la Fase 1 y la Fase 2. Lleva
**`uv sync --no-dev`** (cambian dependencias), **`migrate`** (`reporting.0004` y
`0005`) y **`collectstatic`** (cambian `app.css` y `report-a4.css`). Después,
instalar el timer del informe (bloque en `docs/scheduled-operations.md`).

## ✅ Lo vencido se contaba mal, y las cifras no llevaban a ninguna parte

**Desplegado** en `89a211d` el 2026-09-23, con `LV-240`, `LV-241` y `LV-242`.
Respaldo previo tomado **y verificado**: `aero_ops_20260923_105302.sqlite3`. Sin
migraciones, y `collectstatic` copió **0** archivos —ninguna de las tres filas tocó
un estático—, que es lo que se esperaba.

### `LV-242` — el panel decía cuántos faltan y no dejaba llegar a ellos

La continuación de `LV-241`: contabilizar y marcar ya estaba, faltaba **poder
seguirlo**. Cuatro caminos que no llevaban a nada: la tarjeta de seguros enlazaba
al padrón completo (el filtro por vigencia **no existía** en ninguna de las dos
listas), «Abrir» en la bandeja iba a `alert-list` para las veinte filas, la lista
de vencimientos se cortaba en diez sin decirlo, y la tabla por faena **tiraba** la
fecha del próximo vencimiento que ya calculaba.

⚠️ **Lo delicado no era el filtro sino el criterio.** Si la lista filtrara por su
cuenta, una aeronave con póliza vencida pero **dada de baja** saldría ahí y no en
la tarjeta: cinco filas donde el panel dijo cuatro. Las exclusiones se mudaron a
`registry.selectors` y las leen los dos. 🆕 **Lo cazaron dos tests escritos antes
de que el filtro existiera**, que fallaron exactamente por ese caso.

Dos tropiezos que vale tener a mano: el techo de consultas de `LV-237` volvió a
saltar con la consulta nueva de `LV-241` (48 → 49, subido a propósito), y
**`ruff check apps/` no alcanza** — el gate corre `ruff check .` y cazó una
variable sin usar que la corrida acotada no vio.

## 🟡 Lo vencido se contaba mal, y el correo avisaba de 2 de 6

**Hecho el 2026-09-22.** Dos filas, y las dos son la misma forma de defecto: **un
contador que no puede contar lo que dice contar**.

### `LV-241` — el panel se veía limpio teniendo permisos vencidos

Pedido del usuario con captura: *"el dashboard debe contabilizar y marcar y dar el
seguimiento completo sobre todo lo que hoy está vencido"*. En su pantalla `CC684`
tenía **dos documentos atrasados** arriba y la fila de la tabla de permisos
**entera en guiones**.

⚠️ **La causa no era un rótulo.** La columna «Vigencia pasada» contaba sólo los
permisos `approved` con fecha pasada, y `expire_permissions` los mueve a `expired`
cada noche: **el permiso vencido salía del conjunto antes de que nadie lo viera**, y
la faena cuyo único permiso caducó desaparecía de la tabla. El docstring de
`permit_counts` lo tenía escrito sin sacar la conclusión — *"`lapsed` normalmente
vale cero porque `expire_permissions` los cierra cada noche"*. **Un contador que en
régimen normal vale cero no mide el vencimiento: mide si corrió el cron.**

Los dos hechos quedan separados: `lapsed` es la anomalía (nadie lo cerró, visible a
cualquier edad) y `expired_this_month` es el trabajo de renovar.

**Dos decisiones del usuario, preguntadas antes de tocar:**
- La ventana es **el mes en curso** — es el período en que esto se rinde.
- 🔶 **El porcentaje no baja.** El denominador sigue siendo los permisos vivos, así
  que la cifra que va firmada a la DGAC mide lo mismo y los informes emitidos no se
  mueven. Lo vencido se ve **al lado**, no dentro.

🆕 **Y el número mudo de la misma tarjeta**: *"13/14 · **1** · 2 vencen en 30
días"*. **Tres de las cuatro filas no declaraban `shortfall_label`**, así que
cuando el faltante no era ninguno de los términos con nombre, la plantilla escribía
la cifra sola. Ese 1 era un permiso **aprobado que aún no empieza**, calculado desde
`LV-233` y nunca dibujado. Comprobado en pantalla que no era sólo de permisos:
seguros escribía *"0/1 · 1 · 1 vence en 30 días"*.

### `LV-240` — el correo diario recorría 2 de las 6 fuentes

Seguro JAC, credencial DGAC, prueba de conocimientos y vigencia de permiso salían en
el panel y **no** en el correo. ⚠️ **La que se quedaba corta era la única que va a
buscar a la persona.** No se nota hoy porque `EMAIL_HOST` está vacío: **se habría
notado el día de encender el SMTP.**

La causa era una dependencia al revés —`digest` no puede importar de
`dashboard.views`, que lo importa a él— así que el arreglo es una **mudanza**:
`upcoming_expirations` vive ahora en `apps/compliance/expirations.py`, en el dominio.
Con ella el correo hereda tres reglas que no tenía: esconde lo ya resuelto
(decisivo en algo que llega **cada mañana**), descarta estados terminales, y toma
sólo la última prueba de conocimientos de cada operador.

### Pasos de despliegue

`collectstatic` no hace falta (no cambió ningún estático) pero tampoco estorba; **no
hay migraciones**. El `.mo` cambió: cinco cadenas nuevas.

## ✅ El panel deja de pagar por trabajo que nadie mira

**Desplegado** en `bb391df` el 2026-09-22. Respaldo previo tomado **y verificado**:
`aero_ops_20260922_165049.sqlite3` (*"restorable"*). Sin migraciones;
`collectstatic` copió **2** archivos con 396 post-procesados — exactamente los dos
que cambiaron (`dashboard.js` y `geo/map.js`).

⚠️ **`python` pelado no existe en la VM**, y el primer intento murió ahí: es
`uv run python manage.py`. El comando iba encadenado con `&&`, así que se cortó en
el respaldo y no dejó nada a medias — pero conviene tenerlo escrito, porque el
error se lee como si faltara Python y lo que falta es el alias.

Sale de la revisión de brechas
que pidió el usuario: *"revisar el estado de las mejoras pendientes […] buscar
brechas de mejoras principalmente del dashboard o en general flujos que no estén
bien"*. De todo lo que salió eligió esta mitad — la misma pantalla, más liviana.

**Medido: 58 consultas por carga antes, 48 después** (59 → 49 con faena elegida).

⚠️ **El hallazgo que hay que llevarse, porque va a repetirse**: tres de las cuatro
cosas son la misma historia — **una sección se retira de la pantalla y su cálculo se
queda vivo**, porque mirando la pantalla no se nota. `LV-216` borró la tarjeta del
clima de la plantilla y la vista siguió calculándola **un mes entero**. `LV-89`
retiró dos gráficos y sus agregaciones siguieron viajando al navegador, sostenidas
por un test que las leía como evidencia.

Lo que se fue: el camino completo del clima (`panel_forecast` y sus tres ayudantes,
más el `<input type="hidden" name="weather">` que colgaba de una variable que la
vista ya no ponía), las dos series de `LV-89`, la segunda vuelta de `permit_counts`,
y la cota que le faltaba a `resolved_alert_keys` — que traía **toda la historia de
alertas resueltas** a memoria en cada login para filtrar una lista de diez filas.

**Lo que NO se tocó**: `apps/core/weather.forecast_for` y la revisión meteorológica
de la ficha del plan geo (`R8.1`/`R8.2`), que es donde el pronóstico **queda como
evidencia** — y era el único camino real desde `LV-216`.

🆕 Y de paso lo contrario del mismo defecto: `longest_wait` se calculaba, tenía
pruebas y **ninguna plantilla lo dibujaba**. Ahora la tarjeta de SIGO dice *"la más
antigua: 42 días"*, sin costar una consulta.

**Queda un guardián**: `apps/dashboard/test_lv237_panel_query_budget.py` fija el
techo de la **vista entera** —había techos sobre funciones sueltas y ninguno sobre
el panel—, en sus dos formas y con una prueba de que no crece con la operación.
⚠️ **El techo se mide con el proceso caliente**: Django cachea
`ContentType.get_for_model` por proceso, así que sin una carga de calentamiento el
número mide el orden de la suite y no el panel (daba 57 aislado y 49 en la suite
completa, midiendo lo mismo).

**Y el plan geoespacial abre en satélite** (`LV-239`), pedido del usuario en la
misma sesión. Lo interesante no es la capa sino que dejó de depender del **orden**
de `GEO_TILE_PROVIDERS`: ahora hay una marca `"default": True` explícita, porque
reordenar ese literal por prolijidad cambiaba en silencio lo que ve el operador.

### Lo que la revisión encontró y NO se hizo

El usuario eligió el alcance; esto quedó levantado, con su evidencia:

- **Callejones sin salida del panel.** «4 seguros vencidos» lleva a la lista
  completa, porque el filtro por vigencia **no existe** en `AircraftList` ni en
  `OperatorList`. «Abrir» en la bandeja va a `alert-list` y no a la alerta
  (`apps/core/tray.py`), mientras las otras tres fuentes sí usan
  `get_absolute_url()`. La lista de vencimientos se corta en 10 sin decirlo y sin
  «ver todos». La tabla por faena **calcula** `next_expiry` y `days_remaining` y no
  los dibuja — justo el dato que dice cuál renovar primero.
- ⚠️ **El correo diario avisa de 2 de 6 fuentes.** `build_digest` sólo recorre
  habilitaciones y documentos; seguro JAC, credencial DGAC, prueba de conocimientos
  y vigencia de permiso salen en el panel y **no** en el correo. Hoy no se nota
  porque `EMAIL_HOST` está vacío: **el día que se encienda SMTP, avisa mal.**
- **Una faena sin flota dice «todo al día»**, afirmando cumplimiento sobre un
  conjunto vacío en la tarjeta que existe para contestar «¿puedo operar?».
- **El prevuelo sólo puede firmarse después de volar** (`LV-238`, anotado por
  decisión del usuario): `PreflightCheck` cuelga de `FlightRecord`, que se escribe
  al volver. Y nada persigue un vuelo sin chequeo.
- ✅ **Un pendiente que ya no lo era**: `HANDOFF` pedía averiguar si `LV-186`
  escondía documentos por vencer. **No los esconde** — era el guard de onboarding, y
  `LV-187` lo cerró; el test de punta a punta lo fija.

## ✅ El informe mensual: paginado y con lo escrito marcado

**Desplegado** en `eb62b0a` el 2026-09-08. `collectstatic` copió **1** archivo —
`report-a4.css`, el único estático que cambió— y no hubo migraciones.

⚠️ **Queda sin comprobar la impresión real.** Los tests afirman que la regla
`@media print` existe y que la marca de «escrito» lleva `.no-print`, pero
imprimir a PDF no es algo que se pueda ejercitar desde el navegador integrado. Un
`Ctrl+P` sobre un informe con más de nueve permisos confirma las dos cosas que
faltan: que cada hoja sale en su página y que la marca no aparece en el papel.


Sale de dos preguntas del usuario el 2026-09-08 sobre el informe: si lo de
generarlo estaba resuelto, y una forma más clara de editarlo y revisarlo.

**Lo variable: estaba resuelto.** Las cifras se calculan y los estados se
reconstruyen al corte (`LV-233`), así que generarlo fuera de la aplicación ya no
tiene sentido: sacarlo perdería justamente el corte reconstruido.

⚠️ **Lo que no estaba resuelto era el formato, y era pérdida de datos.** La hoja
mide 1123 px fijos y el pie estaba en posición absoluta contra ellos, con el
cuerpo sin tope. Medido con 15 permisos: el cuerpo terminaba en **1487 px**, o
sea 427 px encima del pie y 364 px fuera de la hoja, recortados por
`overflow: hidden`. **El informe perdía permisos en silencio** en un papel que va
firmado a la DGAC diciendo «detalle permiso a permiso». Con los 11 de producción
ya colisionaba.

Dos arreglos, y el segundo existe porque el primero estuvo mal:

1. **La hoja es una columna flex** y el pie va en el flujo. El traslape pasa a
   ser imposible por construcción, sin importar el contenido.
2. **El reparto en hojas** (`apps/reporting/pagination.py`): la sección de
   permisos pide tantas hojas como necesite y «Página X de N» se calcula — antes
   el pie decía «de 5» literal. ⚠️ El primer reparto usaba un alto de fila único
   de 45 px, medido sobre filas de uno o dos operadores; con **cuatro** —lo que
   tiene producción— la celda envuelve y la fila mide 60, así que volvía a
   recortar. Ahora se reparte por presupuesto de píxeles estimando cada fila por
   su contenido, y el rótulo **declara el total** («14 vigentes») para que un
   recorte residual sea contable por quien revisa.

**Y lo escrito se distingue de lo calculado**: los tres bloques que redacta quien
firma —observación, hallazgos, acciones— llevan una marca «✎ Escrito · editar»
con su enlace al formulario. ⚠️ **No se imprime**: un rótulo de «editable» sobre
el papel entregado afirmaría que el lector puede cambiarlo.

Queda pendiente de lo que el usuario pidió: **ver los cambios** (comparar
revisiones, y contra el mes anterior). Se eligió dejarlo para después.

## ✅ Incidente del 2026-09-08, cerrado el mismo día

**Resuelto y desplegado**: `d7c06da` en `p340`, con el interruptor confirmado en
la VM (`curl /sw.js | grep -c unregister` → `1`). Desde ahí, cada navegador que
abre la aplicación desinstala solo el worker roto y borra su caché.

**Gate verde sobre el arreglo**: 3169 pruebas, 97,43 % de cobertura, 27m55s. Son
15 más que antes de la caída, y las 15 son guardianes de esto: seis del
interruptor y del camino de la respuesta, ocho del cruce permiso ↔ persona ↔
aeronave, y una del reparto plural del aviso.

Después de desplegar `b4a7d9e`, producción devolvió `ERR_FAILED` en el navegador
con el servidor sano. **La causa fue el service worker de `UX-26`**, escrito ese
mismo día: `cache.put` estaba dentro del camino de la respuesta y al rechazar
—una 206, una redirigida, la cuota— hacía que `respondWith` rechazara. La red
estaba bien; lo que mató la página fue el intento de guardarla.

⚠️ **Un service worker roto sobrevive a un `git revert`**: el navegador conserva
la copia que ya guardó. Por eso el arreglo no es revertir, es **servir bytes
nuevos en `/sw.js`** que lo desinstalen. Con `SERVICE_WORKER_ENABLED=False` —el
defecto ahora— esa ruta sirve un worker que se desinstala solo, borra la caché y
recarga las pestañas que estaba rompiendo.

⚠️ **Recuperar una pestaña con `Ctrl+Shift+R` no arregla producción**: esquiva el
worker en ese navegador y deja la ruta sirviendo el roto para todos los demás.

El análisis completo, con los guardianes que quedaron puestos y el procedimiento
para volver a encender la copia sin conexión, está en
[docs/dev/postmortem-2026-09-08-service-worker.md](docs/dev/postmortem-2026-09-08-service-worker.md).
La regla que queda —*nada que intercepte navegaciones se despliega habilitado por
defecto*— está en `AGENTS.md`, § Lecciones operativas.

**El mismo día y por la misma causa de fondo**, el usuario encontró que
«¿Puedo volar?» contestaba **Sí** para una persona que el permiso no nombra: la
comprobación se quedaba en *"¿la faena tiene algún permiso vigente?"* y nunca
miraba `FlightPermission.operators` / `aircraft_fleet`. Sus ocho tests pasaban
porque **la fixture creaba el permiso con el padrón vacío** — el test compartía
el punto ciego del código que probaba. Arreglado: ahora bloquea, y dice qué mitad
falta y en qué folio.

## ✅ Qué corre en `p340`

| | |
|---|---|
| Último commit de **código** | **`0ebb52f`** (2026-09-23) |
| Desplegado en `p340` | **`0ebb52f`** ✅ el 2026-09-23 |
| Migraciones pendientes | **ninguna** |
| Diferencia con `origin/main` | sólo documentación (este archivo) — **no requiere desplegar** |
| Copia sin conexión (`UX-26`) | ⛔ **apagada** — `SERVICE_WORKER_ENABLED=False`; ver el incidente de abajo antes de encenderla |

Respaldo previo tomado **y verificado**: `aero_ops_20260908_094134.sqlite3`
(*"restorable"*). `operations.0029` aplicó limpio —la única que faltaba—,
`bootstrap_roles` reconfiguró los cinco roles y el grupo `Dirección`, y
`collectstatic` copió **9** archivos con 403 post-procesados: exactamente los
nueve que cambiaron. `uv sync` no instaló nada, porque esta tanda no trae
dependencias nuevas.

⚠️ **Queda pendiente en la VM, y no lo hace ningún comando: crear la lista de
chequeo prevuelo** en `/admin/operations/preflightchecklist/`. Hasta que exista,
`UX-29` dice *"no hay ninguna lista configurada para el modelo X"* — que es
correcto y deliberado, pero significa que la fila no hace nada. **Su contenido es
una decisión de la empresa y por eso no viene precargada**: un chequeo que
alguien firma es una declaración sobre el estado de una aeronave, y sembrar
puntos inventados haría que la primera firma afirmara algo que nadie acordó.

⚠️ **Esta tabla se actualiza en el momento de desplegar, no después.** La
respuesta a *"¿qué corre en `p340`?"* se perdió tres veces por dejarla para
luego, y cada vez costó una sesión reconstruirla.

### ⚠️ La faena cerrada sale del indicador — **una cifra del informe cambia**

Pedido del usuario el 2026-09-14 mirando el panel: *"cuando el centro de costo
cierra no es necesario que lo muestre el panel"*. Eran siete faenas cerradas
ocupando la tabla con «Ninguno».

**No era sólo ruido de pantalla.** Esas filas son el universo del indicador que va
firmado a la DGAC: `cost_centres_with_operation` es su denominador y
`cost_centres_without_permit` su numerador. Una faena cerrada no tiene permisos
vigentes —ya no opera— así que cada una empeoraba una cifra de cumplimiento por
una operación terminada.

**Qué cambia en el papel**: los informes **ya congelados no se tocan** —guardan su
payload, y por eso lo guardan—. Cambian las vistas previas en vivo y los informes
que se congelen de aquí en adelante: el «X de N Centros de Costo con permiso
vigente» pasa a contar sólo las faenas que operan. En producción bajan numerador
y denominador, así que la cifra **mejora** y pasa a medir lo que corresponde.

🔶 **La regla no admite excepción, por decisión del usuario**: *"independiente que
tenga permiso o no, si está cerrado no cuenta"*. Se propuso dejar visible la
faena cerrada que conserva un permiso vivo —una contradicción que alguien debería
cerrar— y se descartó. Lo que se pierde: ese permiso ya no sale en **esa** tabla;
sigue en la lista de permisos y en los vencimientos.

🔶 **Y no se reconstruye al corte**, a diferencia de la población y el estado de
los permisos (`LV-233`): `contract_status` no guarda **cuándo** se cerró, igual
que `is_active`. Un informe aún no congelado de un mes en que la faena sí operaba
la deja fuera.

### 🔶 Pendientes de mantenimiento, vistos en el despliegue del 2026-09-14

- ⏳ **Dos ramas de Dependabot esperando**: `dependabot/pip/django-6.1.1` y
  `dependabot/pip/ruff-0.16.6`. La de Django es la que corre: un `6.1.1` sobre
  `6.1` es un parche, y los parches de Django suelen ser de seguridad. Conviene
  mirar su nota de versión antes de mezclar, y pasar el gate — `pip-audit` está
  en él, así que un CVE conocido saldría solo.
- ✅ **Las 40 actualizaciones del sistema se aplicaron y la VM se reinició** esa
  misma tarde: `26.04` → `26.04.1`, y el banner ya no pide reinicio.

#### ✅ La VM creció, y se comprobó que los datos siguen ahí

En el mismo reinicio el volumen pasó de **47 GB a 342 GB** y la IPv4 interna de
`eth0` cambió (`172.22.10.51` → `172.22.10.143`; la de Tailscale no, por eso el
SSH siguió funcionando). Un volumen que cambia de tamaño bajo los pies de una
base de datos merece comprobarse antes de dar nada por hecho, y se comprobó:

| | |
|---|---|
| `aero_ops.sqlite3` | 3,1 MB, modificada ese mismo día |
| Volumen | el mismo LVM `ubuntu--vg-ubuntu--lv`, ampliado — 13 GB usados |
| Respaldos | diarios y al día (19:00) |
| **Padrón** | **15 faenas · 45 operadores · 16 aeronaves** |

Fue una **ampliación**, no un volumen nuevo. Una base vacía pesaría ~200 KB.

🔶 **Ese conteo queda escrito a propósito**: es la referencia contra la que
comparar la próxima vez que haya que comprobar si una base es la de siempre. Un
"parece que está todo" no se puede contrastar; tres números sí.

⚠️ **Y al dictar esa comprobación se repitió el error que esta guía documenta
dos veces**: el comando de conteo se dio sin `cd /opt/aerocontrol` y sin cargar
el entorno, así que murió con *"can't open file '/home/levdigital01/manage.py'"*.
Falló limpio, pero con el `cd` puesto y sin el entorno habría corrido contra
`config.settings.dev` — que es la forma silenciosa del mismo error. **Entorno
primero, siempre**, también para una consulta de lectura.

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

## Cierre del 2026-08-31 — **empezar por acá**

Se fue a cerrar **un pendiente anotado en un test** y la jornada terminó en
**ocho filas**, tres de ellas defectos que nadie había pedido arreglar porque
nadie sabía que existían — uno de seguridad y dos que llegaban al cálculo de
cumplimiento y al padrón. Más cuatro pedidos del usuario, todos con captura.

**La cadena, porque importa cómo se encontró cada cosa:** el pendiente del test
de `LV-186` decía que un documento vigente salía del panel; al escribir el test
resultó que el ítem sí llegaba y lo tapaba un guard de plantilla (`LV-187`); al
verificar *eso* con filtro por faena apareció un defecto de atribución que llega
al informe de cumplimiento (`LV-188`); y al arreglar el guard, **el gate cayó en
un test cuyo nombre era el diagnóstico** y destapó una fuga de datos personales
en el panel (`LV-191`). Ninguno de los cuatro se buscó.

### Estado exacto

- **`origin/main` = `4acc1e6` + el commit de este cierre** (mirar `git log`).
  **`p340` sigue en `22f379f`**: ahora le faltan **`LV-184` a `LV-195`**.
- El paso de despliegue no cambió: **`migrate` + `bootstrap_roles` +
  `collectstatic`**, y sin `bootstrap_roles` media fila de `LV-184` queda sin
  efecto. Después, el rol `Compliance` a Ariel y a Cristóbal.
- **Ninguna de las filas nuevas trae migración.** La única de la tanda que
  migraba sigue siendo `LV-184` (`registry.0039`, sólo el permiso).

### Lo que se cerró

- **`LV-186` no tenía fila ni entrada de `CHANGELOG`** aunque su commit sí.
  Escritas. **Una fila fantasma es el espejo de un despliegue fantasma** — el
  trabajo hecho y el registro sin hacer, y sólo se descubre si alguien busca la
  fila. Anotado en `AGENTS.md`.
- **`LV-187`**: el panel envolvía todo su contenido en un guard de primera
  pantalla que no miraba los vencimientos y sí respetaba el filtro por faena, así
  que **elegir una faena sin flota ni padrón reemplazaba el panel entero por
  "Comienza tu operación"** y se comía vencimientos reales de esa faena. De paso,
  su cuarto término (`stages`) no existía en el contexto: condición muerta.
- **`LV-191`, `P1` y de seguridad**: la lista de vencimientos del panel **nunca
  filtró por los permisos del usuario**. Cada fila nombra su sujeto, así que se
  filtraban folios de permisos, matrículas y **nombres de personas junto a su
  credencial DGAC por vencer**, en la pantalla que se abre en cada inicio de
  sesión. El guard de `LV-187` lo tapaba sólo con la base vacía, o sea en los
  tests y nunca en producción: **estaba haciendo de control de acceso sin ser
  uno**, y por eso dos tests pasaban por la razón equivocada. Cerrado con el
  permiso de lectura del modelo de cada fuente, en un único punto de control.
- **`LV-190`, `P1`**: el importador del Capítulo 1 podía **duplicar una persona**
  en el padrón que la DGAC espeja, y nada lo habría detenido — cruzaba sólo por
  número de empleado, creaba con `create()` (que no pasa por `clean()`, donde vive
  la comprobación de RUT repetido) y `Operator.rut` no tiene índice único. Salió
  al preparar el cruce del manual que pidió el usuario.
- **`LV-195`, `P1`**: y éste salió **al correr el cruce de verdad**, no leyendo
  código. El Rev 17 trae dos seriales partidos por un espacio (`RPA-4401`,
  `RPA-4436`) y el importador los comparaba en crudo contra los de la base, que
  se guardan sin espacios: salían como "serie nueva", y **un conflicto detiene la
  corrida entera**, así que un salto de línea dentro de una celda del Word
  impedía cargar también las 48 fichas de personal. Es la misma forma de defecto
  que `LV-190` y en la misma función — una llave comparada sin la función
  canónica que la app ya usa en todos los otros caminos.
- **`LV-188`, `P1`**: la atribución de faena de un documento conocía **siete**
  modelos y el filtro **dos**. La Carta Permiso salía con el chip `CC738` y
  **desaparecía al filtrar por `CC738`**. Y no era sólo esa pantalla: la misma
  función alimenta la tarjeta de alertas, el resumen por correo y **el informe de
  cumplimiento por faena**, donde no hay filtro de usuario de por medio.

### ⚠️ Lo que hay que mirar al desplegar `LV-188`

**El informe de cumplimiento va a mover sus números**, y no porque el
cumplimiento haya cambiado: cambia el universo contado. Conviene medir el antes
y el después **en la VM**, que es donde están los documentos (el demo no tiene
ninguno cargado, así que ahí no se puede medir). El desglose por tipo de sujeto
dice todo — lo que no sea `registry.aircraft` ni `registry.operator` es lo que
antes no contaba en ninguna faena:

```
uv run python manage.py shell -c "from collections import Counter; from django.contrib.contenttypes.models import ContentType as CT; from apps.compliance.models import Document; print(Counter(str(CT.objects.get_for_id(i)) for i in Document.objects.filter(is_active=True, is_current_version=True).values_list('content_type_id', flat=True)))"
```

**Y esto ordena el pedido de la tendencia**: `ComplianceSnapshot` viene guardando
desde el 2026-08-12 una serie calculada sobre el universo incompleto. Graficarla
sin más metería un salto que se lee como "el cumplimiento mejoró" cuando es el
arreglo. O se arregla antes de graficar —ya está arreglado— o el gráfico dice
desde qué fecha la serie es comparable. Los snapshots viejos **no se recalculan**:
son un hecho fechado, igual que una migración.

### Segunda tanda del 2026-08-31: el crítico y cuatro más

Desplegado `3315933` en `p340` (respaldo `aero_ops_20260831_123616` verificado,
`registry.0039` aplicada, `bootstrap_roles` corrido). **Queda el paso manual:
asignar el rol `Compliance` a Ariel y a Cristóbal**, o media fila de `LV-184`
sigue sin efecto. Después de ese despliegue se cerraron cinco filas más, **sin
desplegar todavía**:

- **`LV-202`, `P0`, declarado crítico por el usuario** — el mapa no podía dibujar
  una circunferencia. **No había nada roto**: el botón redondo de la barra es el
  de punto (`drawCircleMarker`, que es cómo se dibuja un KML Point) y no existía
  herramienta de círculo, apagada con la razón *"no faithful KML representation"*.
  Cierto a medias: KML no tiene un círculo pero sí lo tiene **poligonalizado**,
  que es cómo llegan los de Trimble. Se dibuja como anillo de 64 lados con el
  mismo radio terrestre que usa el servidor, más el **pin central** al terminar.
  Verificado ejecutando el JS con node: error de radio −0,06% y desviación 0,12%
  contra el umbral de 10%, en las cuatro latitudes de la operación.
- **`LV-204`, `P1`** — la alerta de un documento no decía de qué faena era.
  Faltaban tres rutas (`costcenter`, `geoplan`, `flightrequest`) contra una lista
  que ya existía, `DOCUMENTABLE_MODELS`. **Aquí se cobró lo que `LV-188`
  invirtió**: con filtro y atribución unificados, las tres llegan al chip, al
  filtro, al correo y al informe con la misma línea.
- **`LV-201`** — el panel y el informe dicen cuántos permisos hay vigentes,
  esperando aprobación y con la vigencia pasada. Un solo cálculo para las dos
  pantallas.
- **`LV-196`** — "Patrullaje" en el vocabulario de propósito. **Lleva `migrate`**
  (`operations.0022`, `registry.0040`, las dos `(no-op)`).
- **`LV-195`** — el espacio en la celda del Word (ver arriba).

**Paso de despliegue de la tanda: `migrate` + `collectstatic`.** No hace falta
`compilemessages`: el `.mo` va versionado.

**Desplegado `fe73561` en `p340`** (respaldo `aero_ops_20260831_135710` verificado,
`operations.0022` y `registry.0040` aplicadas, 3 estáticos copiados — los tres JS
del mapa, o sea que el círculo llegó).

### Tercera tanda: deshacer lo que se hizo mal

Dos filas más, **sin desplegar**:

- **`LV-199`** — desvincular un plan del permiso. Vincular no tenía inversa. **La
  ubicación que el plan rellenó se queda**, y el aviso lo dice antes de aceptar:
  borrarla dejaría un permiso aprobado sin coordenadas. No hizo falta escribir
  bitácora — `GeoPlanPermissionLink` (`OPS-7`) ya registra todo cambio de esa FK,
  incluido el paso a nulo.
- **`LV-203`** — archivar un plan desde el listado. **El pedido estaba cumplido en
  sus dos tercios y nadie lo sabía**: archivar existe desde `LV-135` con permiso
  propio (`delete_geoplan`) y con motivo escrito obligatorio cuando el plan dejó
  rastro (`LV-178`). Lo que faltaba era llegar: la columna ofrecía "Restaurar" y
  nada más. **No se agregó el "escriba BORRAR"** que el usuario propuso: el motivo
  escrito es un freno más fuerte —dice *por qué*, no sólo que alguien leyó— y
  `LV-135` ya había decidido que "una confirmación vacía sólo enseña a apretar sí
  sin leer". Queda dicho: si lo quiere igual, es un cambio chico.

**Paso de despliegue: `collectstatic`.** Sin migración.

### Cierre del 2026-09-07 (noche): la tanda 6, con alcance acordado — **empezar por acá**

El plan la tenía bloqueada (*"requieren decisión de negocio... no empezar sin
acordar alcance"*). El usuario acordó el alcance ese día y eligió **las cuatro
filas que no dependen de un texto externo**.

**Gate verde, los nueve pasos**: 3154 pruebas, **97,42 %** de cobertura,
**31m40s**, `ruff check`, `ruff format --check`, `bandit` y `pip-audit` limpios.
Sin dependencias nuevas, así que `pip-audit` no dice nada que no dijera antes.

⚠️ **Esto lleva migración: `operations.0029`** (cuatro modelos nuevos, ninguna
fila tocada). Y `bootstrap_roles`, `collectstatic` y dos cosas a mano después —
ver *"El despliegue de esta tanda"* más abajo.

⚠️ **`makemigrations --check` atajó una migración que faltaba**, y vale anotar
cómo: cambié la etiqueta de `PreflightAnswer.VALUE_CHOICES` **después** de
generar `0029`, y Django guarda `choices` dentro de la migración. El gate la
detectó y propuso un `0030_alter_preflightanswer_value`. Se plegó en `0029`
—regenerándola— en vez de mandar dos: `0029` no se había aplicado en ninguna
parte salvo la base de demo, que es descartable, y en SQLite un `AlterField`
reconstruye la tabla, o sea trabajo por una etiqueta. **Esto sólo es correcto
mientras la migración no haya salido**; una vez desplegada, el arreglo es siempre
una migración nueva.

| Fila | Qué quedó, y qué hay que saber para tocarlo |
|---|---|
| `UX-27` «¿Puedo volar?» | Una respuesta para aeronave + operador + faena, hoy. **Vencido bloquea, por vencer avisa** — la escala de `UX-01`, no una nueva. ⚠️ **La fecha ausente bloquea**: contestar «sí» porque *no se sabe* es peor que no contestar. 🔶 La brecha de compatibilidad y pertenecer a otra faena **nunca** bloquean. Y la pantalla dice que no autoriza nada. |
| `UX-31` vistas por rol | Los roles son **los grupos de `bootstrap_roles`**, no una taxonomía nueva. Aterrizaje **sólo al iniciar sesión**, y un `?next=` gana siempre: no hay redirección desde `/` porque habría vuelto el panel inalcanzable para tres de cinco roles. Los atajos del menú son un añadido, no un recorte. |
| `UX-26` PWA | `/sw.js` **desde la raíz** (el alcance de un worker es el directorio del que se descarga). Todo lo que no sea `GET` no se intercepta: sin cola, sin reintento. Hay un guardián que vigila que no aparezca maquinaria de escritura diferida. Cerrar sesión borra la caché. Lleva un ajuste nuevo, `SERVICE_WORKER_VERSION` — **el despliegue debería pasarle el commit**, o el navegador seguirá sirviendo lo guardado. |
| `UX-29` checklist prevuelo | `operations.0029`. ⚠️ **La respuesta copia el texto del punto** (`LV-233` antes de que duela) y **firmado se congela**. 🔶 Un «no conforme» **no** impide firmar: la lista registra, no decide — bloquear habría hecho que la gente vuele igual y no firme nada. Las listas se configuran en el centro de administración; `PreflightCheck` y `PreflightAnswer` **no** se registran ahí a propósito. |

**`UX-30` queda sin empezar**, y su propia fila dice por qué: *"sujeto a
verificar el texto oficial primero"*. El clasificador DAN 151 Ed. 4 no se escribe
contra una norma que no se tiene delante.

#### ⚠️ EL DESPLIEGUE DE ESTA TANDA (fases D, E y 6, más el pie del informe)

**Lo que trae, en una línea:** una migración (`operations.0029`), cero
dependencias nuevas, y **tres pasos que no puede saltear** — `bootstrap_roles`,
`collectstatic` y, después, **crear la lista de chequeo prevuelo a mano**.

##### Los pasos, en el orden correcto

El orden es el mismo de siempre y por los mismos motivos, así que no se repiten
acá: **entrar, `cd`, comprobar la ventana, entorno, respaldo, y recién migrar**.
Están escritos completos más abajo, en *"El despliegue de esta tanda (`355f6c1`)"*
— léalos ahí antes de pegar nada; ⚠️ **esta sección no los reemplaza**, y
dictarlos de memoria es exactamente lo que salió mal el 2026-09-07.

```
ssh levdigital01@100.121.16.118
cd /opt/aerocontrol && hostname && pwd
```

Tiene que decir **`p340`** y **`/opt/aerocontrol`**. Si dice el nombre del PC,
es la ventana equivocada.

```
git pull && uv sync
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo $DJANGO_SETTINGS_MODULE; echo $DB_PATH
uv run python manage.py backup && uv run python manage.py verify_backup
uv run python manage.py showmigrations operations | tail -5
uv run python manage.py migrate --no-input
uv run python manage.py bootstrap_roles
uv run python manage.py collectstatic --no-input
sudo systemctl restart aerocontrol && git log --oneline -1
```

##### Por qué cada paso no opcional lo es, esta vez

| Paso | Por qué |
|---|---|
| `migrate` | **Una sola**, `operations.0029`: cuatro tablas nuevas de `UX-29`. No toca ninguna fila existente. |
| `bootstrap_roles` | ⚠️ **Hace falta**, a diferencia de la tanda anterior. Los cuatro modelos nuevos traen permisos nuevos, y el grupo `Administrator` se define como *todos* los permisos — sin volver a correrlo, nadie puede configurar una lista de chequeo. Los otros roles no cambian: contestar y firmar el chequeo usa `operations.change_flightrecord`, que `Operations` ya tenía. |
| `collectstatic` | ⚠️ **Obligatorio, como siempre** (`ManifestStaticFilesStorage`: sin él las listas dan 500), y esta vez además **es lo que invalida la caché de la PWA**: `SERVICE_WORKER_VERSION` sale de la fecha de `staticfiles.json`. Cambian `app.css`, `app.js`, `icons.svg`, `geo/inspector.js`, `geo/main.js`, y hay tres archivos nuevos (`command-palette.js`, `pwa.js`, `manifest.webmanifest`). |
| `restart` | El `.mo` compilado viaja en el repo, pero Django lo carga al arrancar. |

##### ⚠️ Después de desplegar: dos cosas que ningún comando hace

**1. Crear la lista de chequeo prevuelo.** Sin ella, `UX-29` dice *"No hay
ninguna lista de chequeo prevuelo configurada para el modelo X"* — que es
correcto y deliberado (inventar una lista vacía dejaría que alguien la firmara
creyendo que comprobó algo), pero significa que la fila **no hace nada** hasta
que exista una. Se crea en `/admin/operations/preflightchecklist/`:

- **Nombre**: el que use el procedimiento de la empresa.
- **Palabras clave del modelo**: **vacío** para que aplique a toda la flota. Se
  llena sólo si hace falta una lista distinta por modelo, y ahí la específica
  gana sobre la general.
- **Puntos**: uno por renglón, con su orden. `Obligatorio` marcado es el defecto.

⚠️ **El contenido de la lista es una decisión de la empresa, no mía**, y por eso
no viene precargada: un chequeo prevuelo que alguien firma es una declaración
sobre el estado de una aeronave, y sembrar puntos inventados haría que la primera
firma afirmara algo que nadie acordó.

**2. Comprobar que la gente está en su grupo de rol.** `UX-31` reparte pantalla
de inicio y atajos por los grupos de `bootstrap_roles`. Quien no esté en ninguno
sigue viendo exactamente lo de antes —el panel y el menú completo— así que **no
se rompe nada** si esto no se hace; simplemente la fila no se nota. Se revisa en
`/administracion/usuarios/`.

##### Qué mirar en la VM, después

| Comprobación | Qué tiene que pasar |
|---|---|
| Abrir «¿Puedo volar?» desde el menú | Tres desplegables; elegir la terna da un «Sí» o un «No» con sus motivos |
| Abrir un informe mensual e imprimirlo | El pie igual en las cinco hojas, con «Revisión N · Página X de 5» |
| Abrir la ficha de un vuelo | Botón «Chequeo prevuelo» |
| `Ctrl+K` en cualquier pantalla | Se abre la paleta y lista las pantallas del menú |
| Abrir en un teléfono | Lupa en la barra, y la aplicación se puede instalar |
| `curl -sI https://…/sw.js` | `200` y `content-type: application/javascript` |

⚠️ **Y un defecto viejo que apareció mirando el navegador, no el test.** La línea
del pulso del panel (`UX-15`, *"N operaciones hoy · M permisos vigentes"*)
**salía en inglés en producción desde que se escribió**: la entrada del catálogo
está con `{flights}` y `blocktranslate` emite `%(flights)s`, así que nunca
coincidió. Sus tres tests decían `«1 operaciones hoy» o «1 operations today»`, y
esa disyunción de más los dejó pasando por el camino equivocado. Corregido, y con
un test que ahora afirma que **no** hay inglés en la línea.

---

### Cierre del 2026-09-07 (tarde): fases D y E del plan de UX

**Sin migraciones. Con `collectstatic` obligatorio**: cambiaron `app.css`,
`app.js` y hay dos archivos de JS nuevos (`command-palette.js`, y
`geo/inspector.js` reescrito). Y `compile_translations`: siete cadenas nuevas.

| Fila | Qué quedó |
|---|---|
| `UX-19` | Cerrar el cuadro con algo escrito pregunta antes. En `hide.bs.modal`, que es cancelable y cubre las cuatro salidas (`Esc`, la cruz, "Cancelar", clic fuera). ⚠️ **El 422 no reinicia la marca**: ese swap devuelve el formulario con todo lo escrito. |
| `UX-20` | Formulario de más de 8 campos visibles, o con selección múltiple, sale del cuadro: `HtmxFormMixin.get()` responde `HX-Redirect`. ⚠️ Sólo si la página completa **existe**; hay vistas que sólo viven en el cuadro. |
| `UX-21` | `inputmode` por tipo de campo, en `AeroModelForm`. `enterkeyhint` y `autocomplete` **quedan fuera a propósito**, con el porqué escrito en el código. |
| `UX-22` | "Guardar y crear otro" en bitácora, documentos y asignaciones. Opt-in por vista, sólo en el alta, vuelve con la query puesta. |
| `UX-23` | El borrador, fuera del formulario de permiso. ⚠️ **Casi queda inerte**: `generic/form.html` no lo sirve a los largos porque los largos tienen plantilla propia. Se descubrió mirando el navegador, no el test. |
| `UX-24` + `UX-25` | Un solo componente: la paleta (`Ctrl/⌘+K`) y la lupa de la barra bajo 768 px. Los destinos **se leen del menú lateral**, así que hereda los permisos sin preguntar. Verificado a 375×812. |
| `UX-28` | Tabla de coordenadas editable en el globo del elemento (WCAG 2.2 §2.5.7). |
| — | El **pie del informe** era cinco pies distintos: la portada anclada 16 px más arriba, con otra regla y otro rótulo, y la revisión sólo en una hoja de cinco. Ahora `reporting/_foot.html`, uno solo. |

⚠️ **Un fallo de pérdida de datos, encontrado en el navegador y no por un test.**
En la tabla de coordenadas, un `<input type="number">` con basura dentro devuelve
`""`, y `Number("")` es **0** — que pasa `Number.isFinite` sin chistar. Escribir
una letra en una latitud mandaba el vértice al ecuador **en silencio**, y quedaba
guardado. La celda vacía ahora cuenta como inválida y se rechaza la tabla entera.
Es la clase de defecto que sólo aparece ejercitando la pantalla.

**Y un guardián que acusaba a quien no toca lo suyo**:
`test_no_menu_row_is_left_outside_a_group` cortaba `base.html` desde `<aside>`
**hasta el final del archivo**, lo que funcionó mientras el menú fuera lo último
con enlaces. La paleta lleva un `{% url 'global-search' %}` en un `data-*` y el
guardián lo contó como fila de menú. Ahora corta en `</aside>`.

**Fase 6 (`UX-26`, `UX-27`, `UX-29`, `UX-30`, `UX-31`) sigue sin empezar**, y el
propio plan dice por qué: *"Requieren decisión de negocio, no sólo diseño. No
empezar sin acordar alcance."*

---

### Cierre del 2026-09-03 al 2026-09-07 — **empezar por acá**

⚠️ **Esta sección abarca dos jornadas y conviene leerla sabiéndolo**, porque el
despliegue las separa: lo del **03** está en `p340` desde ese día; lo del **07**
—`LV-233` y `LV-218(b)`— no. Las fechas de las filas se corrigieron contra
`git log`, no de memoria: durante el trabajo del 07 se venían fechando como 03
por arrastre del día anterior.

**Lo que entró hoy, en cinco commits sobre `1598fef`:**

| | |
|---|---|
| `3106b99` | **Las tres decisiones que esperaban al usuario**, respondidas y con el porqué escrito: metas de KPI (4 de 5 se quedan sin meta **a propósito**, no es deuda), segregación de funciones en el informe (**no se separa**: redactor y firmante son la misma persona, y queda escrita la condición para reabrirlo), y `LV-232` (**un solo aviso**, con la implementación segura especificada como fila propia). |
| `322a479` | **`LV-220`: la región guardada dice de dónde salió** (`operations.0026`). Cierra la contradicción que la mitad (b) dejó anotada. Sin backfill, y ése es el punto: no hay forma honesta de saber qué se tecleó y qué escribió el plan. Con el guardián de voseo, que apareció porque **se escapó una novena cadena** un día después de dar la revisión por cerrada. |
| `532e597` | **`UX-07`: la tabla de trabajo, una sola vez.** Las 16 listas por un mismo componente, más el orden por columna que no existía en ninguna. |
| `f108528` | **`LV-231`: el folio sale del PDF de la DGAC.** Propone, nunca escribe solo; la vista que confirma **vuelve a leer el PDF y no acepta ningún número del formulario**. Suma `pypdf`. |
| `dc87527` | **`UX-09` + `UX-12`: columnas por persona y vistas guardadas** (`core.0008`), en un solo modelo. |

**Gate verde sobre `ecb8984`**: 2893 pruebas, 97,35 % de cobertura, **27m37s**,
`ruff check`, `ruff format --check`, `bandit` y `pip-audit` limpios. Lo último
importa hoy más que otras veces: `pypdf` es dependencia nueva.

(El gate pasó de 26m03s a 27m37s con las 77 pruebas nuevas. Eso **no** es motivo
para squashear migraciones — ver más abajo.)

**Dos migraciones nuevas para esta tanda: `operations.0026` y `core.0008`.**
Ninguna hace backfill; las dos son columnas nuevas con defecto vacío, así que
aplican sobre producción sin tocar una fila.

**No hace falta `bootstrap_roles` por estas dos filas**: `ListPreference` no
declara permisos de rol a propósito —esconder una columna es cómo alguien mira su
propia pantalla, no un privilegio— y los campos de `FlightPermission` viajan con
los permisos que ese modelo ya tiene. Lo que sí hace falta es **`collectstatic`**:
cambiaron `app.css` y `worktable.js`.

#### ⚠️ EL DESPLIEGUE DE ESTA TANDA (`355f6c1`)

##### Cómo se entra a `p340`

```
ssh levdigital01@100.121.16.118
```

Es la IP de Tailscale (`p340.tailccd107.ts.net`). **Esto se corre en la terminal
de Windows**; todo lo demás, ya dentro.

Y **entrar deja en `/home/levdigital01`, no en el proyecto**, así que el primer
comando de adentro es siempre:

```
cd /opt/aerocontrol && hostname && pwd
```

Sin el `cd`, `git pull` responde *"not a git repository"* — que es un fallo
limpio y visible, a diferencia del de Windows.

##### ⚠️ Y el orden es: **entorno primero, respaldo después**

El 2026-09-07 se dictó al revés —`git pull && uv sync && manage.py backup`— y
`backup` murió con `SECRET_KEY not found`: sin el entorno cargado, `manage.py`
cae a `config.settings.dev`, que no tiene la clave. El `&&` cortó la cadena ahí,
así que **ni el respaldo ni su verificación corrieron**, y las cuatro migraciones
entraron sin red de seguridad.

No hubo daño —eran aditivas y el fallo fue limpio— pero el paso existe
justamente para el caso en que sí lo haya. **El orden correcto ya estaba escrito
en § "El despliegue, por pasos"**; se dictó de memoria y por eso salió mal, que
es el mismo error que esa sección advierte dos veces.

La secuencia buena, entera:

```
ssh levdigital01@100.121.16.118
cd /opt/aerocontrol && hostname && pwd
git pull && uv sync
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo $DJANGO_SETTINGS_MODULE; echo $DB_PATH
uv run python manage.py backup && uv run python manage.py verify_backup
uv run python manage.py migrate --no-input
uv run python manage.py bootstrap_roles
uv run python manage.py collectstatic --no-input
sudo systemctl restart aerocontrol && git log --oneline -1
```

⚠️ **Faltaba escrito, y por eso se perdieron tres intentos.** Esta sección decía
*"los comandos van sin `ssh` porque quien despliega ya está dentro de la VM"* —
cierto, pero daba por sabido el paso que lleva adentro. Sin él, los bloques se
pegaban en la PowerShell de Windows, donde **parecen funcionar**: `git pull`
responde, `migrate` aplica (sobre la base de desarrollo) y el fallo sólo aparece
en el último renglón, cuando `sudo` no existe.

##### ⛔ Y antes de pegar cualquier bloque, correr esto solo

```
hostname && pwd
```

Tiene que decir **`p340`** y **`/opt/aerocontrol`**. Si dice el nombre del PC y
`D:\I+D\AeroControl`, es la ventana equivocada y el bloque **no** va ahí.

⚠️ **Esto no es celo: ya pasó tres veces y dos de ellas el mismo día.** Los
comandos van sin `ssh` y sobre `/opt/aerocontrol` porque quien despliega ya está
dentro de la VM (dictarlos con `ssh p340 "…"` hace que la máquina se pida
contraseña a sí misma — 2026-09-01). Pero eso mismo los vuelve indistinguibles de
un comando local, y el 2026-09-07 el bloque entero se pegó **dos veces** en la
PowerShell de Windows: las migraciones se aplicaron a la base de desarrollo,
`collectstatic` copió a `D:\`, y el fallo sólo se notó al final porque `sudo` no
existe en Windows. No hubo daño, pero **producción quedó sin desplegar creyendo
que sí**, que es exactamente la confusión que esta sección ya perdió tres veces.

Las tres señales de que está en la ventana equivocada:

| Señal | Qué significa |
|---|---|
| El prompt dice `PS D:\…` o `pwsh` | es Windows |
| `set -a; source <(sudo cat …)` da *"The '<' operator is reserved"* | es PowerShell: no entiende la sustitución de proceso |
| `sudo` responde *"Sudo está deshabilitado en este equipo"* | es Windows |

El prompt correcto es `levdigital01@p340:/opt/aerocontrol$`.

##### ✅ DESPLEGADO EN `p340`: **`7fa2ce0`**, el 2026-09-03

Respaldo previo tomado **y verificado**: `aero_ops_20260903_155818.sqlite3`
(*"restorable"*). `git log --oneline -1` en la VM dice `7fa2ce0`.

Las tres migraciones aplicaron limpio —`core.0008`, `operations.0026`,
`reporting.0002`—, que son exactamente las tres que el Paso 2 había contado.
`bootstrap_roles` configuró los cinco roles y el grupo de notificación (era el
crítico: traía los permisos de `ReportRun`), y `collectstatic` copió **10**
archivos con 398 post-procesados — los diez que faltaban. `uv sync` instaló
`pypdf 6.16.2`, la dependencia nueva de `LV-231`.

`seed_document_types` y `seed_alert_rules` reportaron **0 creados**, que es lo
esperado: los dos son idempotentes y lo suyo ya estaba.

⚠️ **Queda pendiente en la VM, y no lo hace ningún comando**: desactivar a mano la
regla *"Permisos: renovación vencida de plazo (T-15 · Gerencia)"*.
`seed_alert_rules` sólo crea, nunca borra, y por eso dijo "0 creados" sin tocarla.

---

##### ⛔ Paso 0 corrido el 2026-09-03: **la tanda del 02 por la tarde nunca se desplegó**

Medido, no supuesto:

```
## main...origin/main
3fb556d (HEAD -> main, origin/main, origin/HEAD) docs(handoff): el gate del ultimo commit termino verde
```

`3fb556d` es del **2026-09-02 a las 11:38**, y `main` va en `355f6c1`
(2026-09-03, 15:31). **Son 34 commits, no 11.** La VM está limpia y en `main`
—no en HEAD desprendido—, así que el `git pull` va a funcionar; lo que no pasó
fue el despliegue de la tarde.

**Cómo se llegó a creer que sí**: el cierre del 02 registró el despliegue de la
**mañana** y a continuación escribió las instrucciones de la tarde, que nadie
ejecutó. Nada las marcó como pendientes, así que "quedó desplegado lo pendiente"
describía la mañana. Es la tercera vez que este documento pierde la respuesta a
*"¿qué corre en `p340`?"*, y las tres veces el costo fue el mismo: una tanda que
se creía en producción y no estaba. **La regla que faltaba y ahora está escrita:
el commit desplegado se anota en el momento, o no se anotó.**

Lo confirma un detalle: `compliance.0025` **no** está entre las pendientes, o sea
que ya se aplicó. Sólo faltan las tres de abajo.

##### Lo que hay que desplegar, entonces

Es **la tanda del 02 por la tarde más la del 03**, no sólo la del 03.

| | |
|---|---|
| Migraciones pendientes | **tres**: `reporting.0002` (la narrativa del informe, `LV-227` — quedó de la tanda no desplegada), `operations.0026` y `core.0008`. Las de hoy son columnas nuevas con defecto vacío: **no tocan una fila**, no hay backfill |
| `collectstatic` | ⚠️ **Crítico, y por partida doble.** Faltan **diez** archivos estáticos —`app.css`, `worktable.js`, `login.css`, `login.js`, `report-a4.css`, `icons.svg`, `theme-init.js`, `app.js` y los dos PNG del informe—. Con `ManifestStaticFilesStorage` el hash viejo deja de resolver: no es un estilo feo, es **500** |
| `bootstrap_roles` | ⚠️ **Vuelve a ser el crítico.** Por las dos filas de hoy no haría falta —`ListPreference` no declara permisos de rol a propósito—, **pero los permisos de `ReportRun` están en la tanda que no llegó**: sin esto nadie salvo `root` abre el informe mensual, y `R3`/`R4`/`R5` quedan invisibles para quien tiene que firmarlo |
| `seed_document_types` | También de la tanda no desplegada (`LV-230`): sin él, el tipo de documento sigue con el nombre viejo |
| Regla T-15 | Sigue pendiente de desactivar a mano — ver Paso 4. `seed_alert_rules` sólo crea, nunca borra |

Son además **49 plantillas** y `generate_monthly_report`, que no piden ningún
paso extra pero explican por qué la comprobación de abajo mira una lista **y** el
informe.

##### Las comprobaciones que importan acá

1. **Una lista** (`/compliance/alerts/` o `/registry/batteries/`), **no el
   panel**: el panel no ejercita nada de lo que cambió. Tienen que verse las tres
   cosas nuevas — el encabezado ordena al apretarlo, y aparecen los botones
   "Columnas" y "Guardar vista". **Si la lista da 500, la causa casi segura es
   `collectstatic`.**
2. **El informe mensual** (`/reporting/monthly/`) **con una cuenta que no sea
   `root`**. Es lo que prueba que `bootstrap_roles` corrió: si pide permisos, no
   corrió.
3. **El acceso**, también sin ser superusuario: la línea del entorno, la ayuda y
   el botón de mostrar contraseña — todo eso viene en la tanda no desplegada.
4. **El corte del padrón de agosto**, que era la comprobación pendiente del 02:

```
uv run python manage.py shell -c "from datetime import date; from apps.dashboard.views import panel_readiness; print({c['key']: (c['count'], c['total']) for c in panel_readiness(date(2026,8,31))['readiness']})"
```

   El criterio es que devuelva **41** operadores y no 42. Si no baja, la causa no
   es el arreglo: es que `created_at` refleja la fecha de carga masiva y no la
   del hecho.

#### ⛔ El squash de migraciones queda retirado, y hay que saber por qué

La condición decía *"se squashean cuando el gate pase de 25 minutos"*, y el
2026-09-02 el gate marcó 26m03s. **Se midió antes de tocar nada y la premisa es
falsa: 158 migraciones desde cero tardan 4,3 segundos** sobre un gate de ~1560, y
se aplican **una vez por sesión de pruebas**, no por prueba. El detalle y las
otras razones (26 `RunPython` sin `elidable`) están en `MASTER_PLAN.md` §
"Migraciones". **No squashear.**

#### Después del despliegue, el mismo día

- **`c58dace`** — arreglo de la primera columna enorme y vacía en centros de
  costo, aeronaves y operadores. Desplegado (2 estáticos). Era la casilla de
  selección inyectándose sin su `<col>`; con `table-layout: fixed` eso corría
  todos los anchos un lugar. **Sin migración.**
- **`LV-200c`** — "Usar uno ya cargado" en el expediente del permiso, para no
  volver a subir la misma carta del mandante. **Sin migración.**
- **`UX-09b`** — la faena como columna en la bandeja de alertas. **Sin
  migración.**

✅ **Los tres desplegados en `p340`: `676be11`.** `collectstatic` corrido y
servicio reiniciado. (Anotado en el momento, que es la regla que esta misma
sección escribió después de perder tres veces la respuesta a *"¿qué corre en
`p340`?"*.)

✅ **Y la tanda del 2026-09-07 desplegada: `69eab52`.** Las cuatro migraciones
—`compliance.0026`, `operations.0027`, `operations.0028`, `reporting.0003`—
aplicaron limpio, `bootstrap_roles` configuró los cinco roles y `collectstatic`
publicó. Entra con esto todo lo del 07: `LV-233` completo (las tres partes),
`LV-218(b)`, `LV-235` y `UX-14`.

⚠️ **Sin respaldo previo**, por el orden mal dictado que se explica más abajo. Se
tomó uno **después** (`aero_ops_20260907_132346`, verificado). No hubo daño —las
cuatro migraciones son aditivas— pero queda anotado porque es la clase de atajo
que un día sí importa.

✅ **Y la segunda tanda del 2026-09-07 desplegada: `c6ded72`.** Sin migraciones:
`UX-13` (la bandeja de trabajo), `UX-14` (responsable), y `UX-15` a `UX-18`, que
cierran la fase C del plan UX. Sólo `git pull` + `collectstatic` + reinicio.

⏳ **Del 2026-09-07 quedan cuatro commits subidos y SIN desplegar**, del
`30bc2e6` al `a5988fc`: las tres partes de `LV-233`, `LV-218(b)` y la consulta a
la DGAC. **Llevan dos migraciones** (`operations.0027` y `0028`) y
**`bootstrap_roles` es obligatorio** — sin él el botón de registrar la revisión
de NOTAM aparece y nadie puede usarlo, el mismo defecto que `R3` pagó con los
permisos de `ReportRun`.

Y hay que saber una cosa antes de mirar el panel:

> ⚠️ **El "Vigentes" del panel puede bajar.** `LV-233` cambió la definición: un
> permiso aprobado que **todavía no empieza** dejó de contarse como vigente y
> pasa a `not_started`. No se perdió nada — estaba contado en la casilla
> equivocada, y mirando una fecha de corte pasada eso era una afirmación falsa
> ante la DGAC. Si el número baja, es esto y no un dato perdido.
- 🆕 **`LV-233` y `LV-234` abiertas**, las dos sobre el informe mensual: revisar
  cómo se edita y se cambia, y **si el cruce de información es correcto**. La
  segunda es el hallazgo que bloquea a la primera — ver abajo.

#### Lo que sigue abierto

- **`LV-218(b)`, el cruce automático de NOTAM: bloqueado fuera del código.** La
  propia fila lo dice — *"requiere hablar con la DGAC primero"*. El paso (a) está
  hecho (el enlace al IFIS) y el (b) exige una conversación con la autoridad
  antes de escribir nada.
- **`LV-232`**, ahora con criterio decidido y forma especificada: ver su fila.
- Del plan UX, la fase C en adelante (`UX-13` … `UX-31`).
- Las filas de datos (`LV-74`, `LV-228`, `LV-98`, `LV-102`) y `R6`/`R7`, que
  esperan SMTP y datos que todavía no existen.

---

### Cierre del 2026-09-02 (tarde)

## ⚠️ EL DESPLIEGUE DE ESTA TANDA

### La etiqueta ya existe, y eso pone una condición

**`v0.6.0-beta` está creada y empujada, sobre `e894b06`** (= `origin/main` al
2026-09-02). En este repo la etiqueta ha significado *"esto es lo que está en
producción"* — así quedó `v0.5.0-beta` —, así que:

- **Desplegar `e894b06` exactamente.** Si la etiqueta y lo desplegado divergen,
  la próxima persona que quiera saber qué corre en `p340` mirará la etiqueta y
  leerá otra cosa.
- **Si entra algún commit antes de desplegar**, hay dos salidas honestas: mover
  la etiqueta al commit que sí se despliega (`git tag -f` y `push --force` **de
  la etiqueta**, no de la rama), o dejarla donde está y etiquetar el despliegue
  real como `v0.6.1-beta`. Lo que no sirve es dejarla apuntando a algo que nunca
  llegó a la VM.
- Al terminar, `git log --oneline -1` en la VM tiene que decir `e894b06`. Ésa es
  la única prueba de que la etiqueta dice la verdad.

**Ocho commits**, del `f2eb099` al `00e3f29`. Los pasos van copiados de
§ "El despliegue, por pasos", **no escritos de memoria** — eso ya costó una
vuelta, y el `;` de la carga del entorno corta un `&&`, que es la forma exacta
de los dos despliegues fantasma del 2026-08-27.

### Paso 0 — averiguar qué tiene la VM, antes de dictar nada

**No asumir desde qué commit viene.** `AGENTS.md`: *"el paso de despliegue es el
de TODO lo que falta en la VM, no el del último commit"*, y esa suposición tiró
producción el 2026-08-31.

```
cd /opt/aerocontrol && git status --short --branch && git log --oneline -1
```

La primera línea tiene que decir `## main...origin/main` y **no**
`## HEAD (no branch)`: después de un rollback la VM queda en HEAD desprendido y
todo `git pull` posterior falla mientras el resto del despliegue **parece**
correr.

### Paso 1 — traer el código y el entorno

```
git pull
uv sync
```

```
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo $DJANGO_SETTINGS_MODULE; echo $DB_PATH
```

Tiene que decir `config.settings.prod` y
`/srv/aerocontrol-data/db/aero_ops.sqlite3`. Sin `set -a`, `source` define
variables de shell y no de entorno, y `manage.py` cae a `config.settings.dev` —
que acá no sería un error visible sino **trabajar sobre la base equivocada**.

### Paso 2 — cuántas migraciones faltan, con el entorno ya cargado

```
uv run python manage.py showmigrations | grep -c '\[ \]'
```

La tanda trae **dos**: `compliance.0025` (`LV-230`, fusiona el tipo de documento
duplicado y **renombra** el que se queda) y `reporting.0002` (`LV-227`, la
narrativa del informe). Si `cd61e53` ya se desplegó, `compliance.0025` ya está y
el contador dirá **1**. Las dos son idempotentes por definición de `migrate`.

### Paso 3 — respaldo, y recién después migrar

```
uv run python manage.py backup && uv run python manage.py verify_backup
uv run python manage.py migrate --no-input
uv run python manage.py seed_document_types
uv run python manage.py seed_alert_rules
uv run python manage.py bootstrap_roles
uv run python manage.py collectstatic --no-input
sudo systemctl restart aerocontrol
git log --oneline -1
```

**Los tres que `migrate` no hace y sin los cuales media tanda no llega:**

| Comando | Qué pasa si falta |
|---|---|
| `bootstrap_roles` | ⚠️ **El más importante de esta tanda.** Los permisos de `ReportRun` son nuevos: sin esto **nadie salvo `root` puede abrir el informe mensual**, y `R3`, `R4` y `R5` quedan invisibles para quien tiene que firmarlo. Ahora hay un test que lo vigila |
| `seed_document_types` | El tipo de documento sigue con el nombre viejo (`LV-230`) |
| `collectstatic` | Entran `report-a4.css`, `login.css`, `login.js` y dos PNG. Sin él, en producción **toda etiqueta `{% static %}` falla** — el informe y el acceso salen sin estilos |

`seed_alert_rules` es por consistencia; no pasa nada malo si falta.

### Paso 4 — lo que ninguna migración hace, porque no debe

⚠️ **Desactivar a mano la regla *"Permisos: renovación vencida de plazo
(T-15 · Gerencia)"*** desde `/compliance/alertrule/` o el admin, si no se hizo
en el despliegue anterior. `seed_alert_rules` **sólo crea, nunca borra**. Las
alertas que ya emitió se quedan: una alerta es evidencia ISO 10.2 y borrarlas
desde una migración eliminaría el rastro de que existieron.

### Paso 5 — comprobar en la VM lo que acá no se puede

**a) El corte temporal del padrón (bloque 3).** El criterio del plan es que el
payload de agosto devuelva **41** operadores y no 42:

```
uv run python manage.py shell -c "from datetime import date; from apps.dashboard.views import panel_readiness; print({c['key']: (c['count'], c['total']) for c in panel_readiness(date(2026,8,31))['readiness']})"
```

Si **no** baja, la causa no es el arreglo: es que `created_at` refleja la fecha
de **carga masiva** y no la del hecho, y el corte no alcanza para ese dato.

**b) El informe, de punta a punta.** Abrir `/reporting/monthly/`, congelar el
borrador de agosto y comparar contra el PDF emitido: **12 faenas, 11 permisos
vigentes, 3 en trámite, 14 aeronaves**. O desde la consola:

```
uv run python manage.py generate_monthly_report --period 2026-08 --dry-run
```

**c) El acceso**, con una cuenta que **no** sea superusuario: que se vea la
línea del entorno, la ayuda y el botón de mostrar contraseña.

### Lo que este despliegue NO lleva

- **El timer del informe.** El comando corre a mano; ponerlo en `systemd` es un
  paso aparte. El informe se emite el **día 5** con corte al último día del mes
  anterior, así que el disparo natural es el **día 1 o 2** — no el último día
  del mes, que es cuando el corte todavía no cerró.
- **`SUPPORT_CONTACT`** en `/etc/aerocontrol.env`, opcional: sin él la pantalla
  de acceso dice qué hacer sin nombrar a nadie.
- **El bloque 9 salvo su primera pieza.** `UX-02`, `UX-04` y `UX-05` están
  hechos; de `UX-07` entró *"mostrando N–M de T"*, que es la parte que aplica a
  las doce listas sin tocar ninguna. Medido antes de decidir, no estimado:

  | Fila | Alcance real medido el 2026-09-02 | Estado |
  |---|---|---|
  | `UX-02` · escala | 311 literales `rem`, 12 repetidos entre 9 y 26 veces | ✅ tokens + techo |
  | `UX-04` · encabezado único | **59 `<h1>`** en **8 formas** distintas | ✅ tamaño; marcado incremental |
  | `UX-05` · sprite SVG | **55 `<path>`** en línea en `base.html` | ✅ 28 símbolos |
  | `UX-07` · "mostrando N–M de T" | Las 12 listas comparten `_pagination.html` | ✅ |
  | `UX-07` · componente de tabla | **58 `<table>`** a mano; ~12 asserts acoplados a clases de presentación (el resto de los 31 son comentarios) | ⬜ |
  | `UX-10` · fila-tarjeta móvil | La lista de aeronaves medía **900 px de tabla en un contenedor de 356** a 390 px de pantalla | ✅ 900 → 356 |
  | `UX-08`, `UX-11` | Densidad conmutable, acciones en lote | ⬜ |
  | `UX-09`, `UX-12` | Columnas por persona y vistas guardadas — **modelo nuevo y migración cada una** | ⬜ |

  Lo que queda de la tanda de la tabla **no es una fila más**: son dos modelos
  con migración y un componente que sustituye 58 tablas. El propio plan lo
  estima en 1–2 sesiones y es el único que marca de **riesgo alto**.

  ⚠️ **Y antes de `UX-07`, el barrido de §6.3.** Los ~12 asserts que localizan
  por clase de presentación se rompen todos con un componente de tabla nuevo; si
  no se barren primero, la tanda se va en arreglarlos. La lista está arriba.
- **`LV-189`** (documentos de sujetos en estado terminal). Está **medida y lista
  para escribir** —son cuatro líneas en `_subject_scope`— y se dejó fuera **a
  propósito**: mueve los porcentajes de cumplimiento igual que `LV-188`, y su
  propia fila pide medir antes y después **en producción**, lo que exige que
  este despliegue ya haya ocurrido. Dos cambios que mueven cifras en el mismo
  lote hacen indistinguible la causa. 🆕 Antes de escribirla hay que decidir un
  hueco que la fila no tenía: `geo.geoplan` tiene `status` con `rejected` y
  **no declara `TERMINAL_STATUSES`**, así que el arreglo tal como está escrito
  dejaría los planes rechazados contando **en silencio**.
- **`LV-220`(b)**. Al medirla apareció que **el principio de la fila ya está
  violado**: `fill_permission_from_plan` escribe región y comuna derivadas en
  los campos del permiso, que no tienen ningún marcador de procedencia. La (b)
  no evita que haya regiones derivadas presentadas como declaradas; sólo evita
  agregar más. Cerrarlo de verdad exige un campo de procedencia y migración, y
  **eso es una decisión aparte**, no lo que la fila pide.

### Después de desplegar, el orden sugerido

1. **Medir** lo del paso 5 y anotar los números en el `MASTER_PLAN`.
2. **`LV-189`**, ya con la medición previa hecha y el hueco de `geo.geoplan`
   decidido. Sola en su lote, porque vuelve a mover cifras.
3. **El timer** del informe, y `SUPPORT_CONTACT` si se quiere.
4. **Bloque 8** (`UX-02`, `UX-04`, `UX-05`) y recién después el **9**. ⚠️ El
   plan avisa que antes de `UX-07` hay que **barrer los tests que localizan
   cosas por clase de presentación**: si no, la tanda se va en arreglarlos.

---


**El usuario informó que el despliegue pendiente quedó hecho**, así que la
sección de abajo ("Cierre del 2026-09-02") ya no describe una cola: describe lo
que se desplegó. ⚠️ **Lo único que ninguna migración hizo y hay que comprobar
que se haya hecho a mano**: desactivar la regla *"Permisos: renovación vencida de
plazo (T-15 · Gerencia)"* en `/compliance/alertrule/`. `seed_alert_rules` sólo
crea, nunca borra. Si sigue activa, `LV-232` no cerró en producción aunque el
código sí esté.

#### El bloque 2 del plan: el informe visible

**`R3` + `UX-06`**, las dos filas juntas como el plan las agrupa. El informe
mensual RPA se ve **dentro de la aplicación**, en `/reporting/monthly/`, y entró
al menú el mismo día que ganó pantalla — el repo lleva seis vistas vivas sin
puerta y ésta no suma la séptima.

**Lo que hay que saber para seguir:**

1. ⚠️ **El ZIP trae ocho plantillas, no seis.** El `HANDOFF` y el plan decían
   "seis artboards A4". Contadas: `p1_portada`, `p2_resumen`, `p3_habilitantes`,
   `p3_permisos`, `p4_cobertura`, `p4_dotacion`, `p5_plan` y `dato_ejecutivo`.
   **`p3_habilitantes` y `p4_dotacion` son variantes que NO llegaron al PDF
   emitido** —`build_pdf.py` del propio ZIP arma la secuencia
   `Main · Resumen · Permisos · Cobertura · Plan`—, y `dato_ejecutivo` es otro
   documento: una hoja mensual aparte, con su propio PDF
   (`JEJ_Dato_Ejecutivo_RPA_PLANTILLA.pdf`). Son **cinco** las páginas del
   informe. Es la tercera cifra citada de memoria que al recontarse no cuadra;
   la regla del plan —"recontar al empezar cada tanda, no citar"— vale también
   para sus propias cifras.
2. **El ZIP vive en `D:\OneDrive - J.E.J. Ingeniería S.A\DGAC\INFORMES\Agosto2026\`**,
   no en el `OneDrive` del perfil. Ahí están también el PDF emitido, el borrador
   y el SPEC.
3. **Las plantillas van a `templates/reporting/`, no a `apps/reporting/templates/`**
   como decía el plan. Ninguna app de este repo tiene carpeta propia de
   plantillas: todas viven bajo la raíz. Se reconcilió a favor del repo, como
   manda `AGENTS.md` §"Precedencia documental".
4. **Ningún número de agosto quedó quemado en las plantillas.** Todo sale del
   payload o se dibuja en ámbar punteado. Dejar la tabla de agosto escrita
   habría hecho que el informe de septiembre mostrara los permisos de agosto.

**Lo que el informe ya muestra de verdad**: la portada entera, los seis
indicadores del resumen, la situación de los permisos al corte, y **la tabla de
faenas fila por fila con su estado de habilitación** — la página que existe para
mostrar las que **no** pueden volar.

**Lo que quedaba pendiente se cerró el mismo día.** `R4` (la tabla permiso a
permiso, el próximo vencimiento por faena, la concentración operacional y la
ventana de 60 días) y `LV-227` (los hallazgos y la observación). **El informe ya
no tiene bloques en ámbar punteado**: lo único que se dibuja como pendiente es
la narrativa cuando todavía nadie la escribió, que es lo correcto.

#### `R5`: el informe se congela solo y lo aprueba una persona

`manage.py generate_monthly_report`, idempotente, con `--force` y `--dry-run`.
**Congela, no aprueba** — un trabajo nocturno que aprobara estaría firmando en
nombre de alguien. `freeze` vive en el modelo porque lo llaman el botón **y** el
comando.

⚠️ **Dos cosas que quedan fuera del código y hay que resolver al desplegar:**

1. **El timer no está cableado.** El comando corre a mano. El informe se emite
   el **día 5** con corte al último día del mes anterior, así que el disparo
   natural es el **día 1 o 2** — no el último día del mes, que es cuando el
   corte todavía no cerró. Va como unidad nueva de `systemd`, con el mismo
   patrón de los otros diez.
2. **Segregación de funciones, decisión del usuario.** Hoy alcanza con
   `change_reportrun`, así que quien redacta la narrativa puede además
   aprobarla. Para una evidencia ISO eso es una pregunta organizacional —a qué
   rol va el permiso de aprobar— y no la decide el código. Separarla exige un
   permiso propio y tocar `bootstrap_roles`.

#### La pantalla de acceso: la ayuda que faltaba, y el bloqueo que no se explicaba

Sale de la §2.1 del plan UX (cinco carencias) más **dos que el plan no tenía**:

1. ⚠️ **El bloqueo devolvía un 403 pelado en inglés** mientras el formulario
   decía "probá de nuevo". A los cinco intentos `django-axes` retiene la cuenta
   **quince minutos por nombre de usuario**, así que reintentar es exactamente
   lo que no funciona — y lo que reinicia la espera. Ahora hay pantalla propia
   con la chapa de la app, y **el plazo se lee de `AXES_COOLOFF_TIME`**: escrito
   a mano se desincroniza el día que alguien cambie el ajuste.
2. **El eslogan estaba impreso dos veces**, palabra por palabra, en el subtítulo
   y en el pie.

Entran además: mostrar/ocultar contraseña, aviso de Bloq Mayús, la línea de
ayuda (**no hay recuperación por cuenta propia**) y **a qué instancia estás
entrando**.

⚠️ **Una corrección al plan UX**: su hallazgo (c) proponía reemplazar el
`#087f78` escrito a mano por `--ac-primary`. Es el mismo valor **en claro**;
**en oscuro** `--ac-primary` vale `#42d4c6`, y blanco sobre ese verde da
**1,9:1**. Se unifica el color y el **primer plano** cambia con el tema —
calculado, no mirado: claro 4,87:1, oscuro 10,0:1, con test que recalcula los
tres.

**Ajuste nuevo, opcional:** `SUPPORT_CONTACT`. Vacío por omisión a propósito —
una dirección inventada manda correo a un buzón que puede no existir. Sin él la
pantalla dice qué hacer sin nombrar a nadie.

#### `R4`: los semáforos, y la escala que NO se copió

⚠️ **La escala del permiso no es la del documento, y conviene no "unificarlas"
después.** `digest.bucket_for` corta en 7/15/30; el permiso corta en **30/60**,
porque su renovación exige carta nueva del mandante y el aviso arranca a los 45
(`LV-226`). Vive en `permit_band`, junto al resto del dominio de permisos.

**No es una tercera paleta** —el riesgo que el plan anotó antes de `UX-01`—: los
**nombres** son los mismos niveles de severidad de la aplicación y hay un test
que lo fija contra `BUCKET_BADGE_CSS`. Cambia el umbral, no el vocabulario.

Cuatro definiciones que se decidieron y no conviene reabrir sin motivo:

| Qué | Cómo quedó |
|---|---|
| Semáforo de la faena | El **peor** de sus habilitantes (§4.2). Sin permiso vigente es `critical`, no "sin banda" |
| Próximo vencimiento | `Min` y no `Max`: el que obliga a actuar es el primero en caer |
| Faena que depende de una persona | La **unión** de operadores de sus permisos vigentes tiene un solo miembro — si alguno designa a otro, hay suplente |
| Solicitud en trámite | Bloque aparte, días en guion. Mezclarla sugeriría que un trámite habilita |

#### El bloque 3 del plan: la exactitud del informe

Las dos brechas de la §4 del plan, las dos de exactitud en un documento que va
firmado a la autoridad.

1. **El padrón que se contaba era el de hoy.** `panel_readiness` recibía la
   fecha de corte y la usaba **sólo para comparar vencimientos**; la población
   salía de `filter(is_active=True)`. Ahora la flota y el padrón se acotan
   además con `created_at__date <= cutoff`. **Va sin parámetro y siempre**: con
   la fecha de hoy la condición es verdadera para toda fila, así que el panel no
   cambia — y una segunda función "igual pero con corte" es cómo el panel y el
   informe empiezan a discrepar.
2. **"Sin fecha" y "vencida" iban sumadas.** El payload gana
   `insurance_missing`/`insurance_lapsed` y
   `credentials_missing`/`credentials_lapsed`, y las páginas 2 y 4 las muestran
   partidas por lo que hay que hacer con cada mitad.

⚠️ **Lo que hay que medir en la VM al desplegar, porque acá no se puede.** El
criterio de verificación del plan es que el payload de agosto devuelva **41**
operadores y no 42. Si **no baja**, la causa es que `created_at` refleja la
fecha de **carga masiva** y no la del hecho, y entonces el corte no alcanza para
ese dato — no es que el arreglo esté mal, es que la base no tiene el historial:

```
uv run python manage.py shell -c "from datetime import date; from apps.dashboard.views import panel_readiness; print({c['key']: (c['count'], c['total']) for c in panel_readiness(date(2026,8,31))['readiness']})"
```

⚠️ **Y el límite del corte, escrito para que nadie lo lea de más**: deja de
contar lo que todavía no existía, **no reconstruye** el padrón de esa fecha. Sin
historial de `is_active`, archivar una ficha la saca también de los informes
anteriores — hay un test que fija exactamente eso. La cifra sólo queda estable
cuando el informe se **congela** (`R5`), y por eso `R5` no es un lujo.

#### `LV-227`: la narrativa se escribe dentro de la app

El usuario preguntó por usar **LibreOffice o similar** para editar el informe.
**Descartado, y con motivo:** el repo ya rechazó una dependencia de sistema más
chica —WeasyPrint, por Cairo/Pango— al elegir `reportlab`; LibreOffice headless
son ~1 GB en `p340`; y **no resuelve el problema difícil**, que es el viaje de
vuelta de un `.docx` editado a dato estructurado. Ese viaje es con pérdida y
rompería la garantía de que el informe no inventa un dato: dejaría de poder
distinguirse qué cifra salió de la base y cuál escribió alguien encima. El
usuario eligió **campos en la app**.

Se editan los **dos bloques que cambian todos los meses**: los hallazgos
(gravedad + encabezado + texto, hasta 8) y la observación del período. Antes hay
que **congelar el borrador**, con un botón propio — es un paso explícito porque
congelar es lo que separa "esto se mueve con la base" de "esto es el informe de
agosto". Eso es **media `R5`**: regenerar, comparar y aprobar sigue pendiente.

🔶 **Fuera a propósito**: la página 5 (el plan y su matriz de exigibilidad) sigue
escrita en la plantilla. Cambia una vez por trimestre, no todos los meses, y su
matriz es una tabla de 4×4. Si hace falta editarla, es una fila aparte.

⚠️ **Y una trampa de test que vale para todo el repo**: la prueba de que el
formulario no expone el modelo entero **no puede ser un POST**. Con `"__all__"`
puesto, el POST sale inválido por un campo que no trae (`is_active`) y el test
queda verde sin haber medido nada. El guardián real afirma sobre
`set(PeriodNoteForm().fields)`. Comprobado dejando el `"__all__"`: cae ése y no
el otro.

#### Dos defectos que salieron de escribir los tests, no de leer código

1. **`?period=26-8` devolvía un informe del año 26.** Partir por el guion y
   confiar en `int()` acepta dos dígitos de año y compone una portada y un código
   con una fecha dieciocho siglos atrás, sin que nada avise. Ahora el formato es
   estricto (`\d{4}-\d{2}`) y lo que no calza cae al período por defecto.
2. **`|lower` convertía "DGAC" en "dgac"** en el resumen ejecutivo — el
   regulador en minúscula dentro del documento que se le dirige. Salió mirando la
   pantalla, no corriendo tests: es el caso de "medir y además mirar".
3. **Las fechas del informe salían en orden ISO.** `{{ valor|slice:"5:" }}` sobre
   `2026-08-01` da **`08-01`**, que en un documento chileno se lee como el 8 de
   enero. En un papel que va a la DGAC, una fecha que se puede leer al revés no
   es un detalle de formato. Se arregla con el filtro `as_date`, y **el payload
   sigue guardando ISO**: guardar la cadena ya formateada dejaría los informes
   viejos con el formato viejo el día que cambie la convención. Los tres salieron
   de mirar la pantalla o de escribir el test, ninguno de leer código.

#### El registro que faltaba de la mañana

`LV-200`, `LV-230` y `LV-232` estaban **cerradas y commiteadas** y sus filas
seguían en `⬜`/`🔶`, y **ninguna de las cinco filas del 2026-09-02 tenía entrada
en `CHANGELOG.md`**. Es la fila fantasma que `AGENTS.md` describe, cinco veces
seguidas y en la misma jornada. Corregido. **Y se versiona `docs/ux-ui-plan.md`**,
que estaba sin seguimiento: es la fuente de las 31 filas `UX-nn` y sin él la
mitad de este plan no existe desde el repo.

### Cierre del 2026-09-02 (mañana)

⚠️ **Esta sección describía trabajo commiteado y sin desplegar. Ya se desplegó**
(ver la sección de arriba). Se conserva porque sus pasos y advertencias siguen
siendo la referencia de qué llevó ese despliegue.

#### Lo primero: el despliegue pendiente

Los pasos van copiados de § "El despliegue, por pasos", **no escritos de
memoria** (eso ya costó una vuelta). Lleva **una migración** —
`compliance.0025` — así que va con respaldo previo, y **dos sembrados**:

```
uv run python manage.py seed_document_types
uv run python manage.py seed_alert_rules
```

Sin el primero, el tipo de documento sigue con el nombre viejo. Sin el segundo, no
pasa nada malo — pero conviene correrlo por consistencia.

⚠️ **Y algo que ninguna migración hace, porque no debe hacerlo:** la regla de
alerta *"Permisos: renovación vencida de plazo (T-15 · Gerencia)"* sigue **activa
en `p340`**. `seed_alert_rules` sólo crea, nunca borra. Hay que desactivarla a
mano desde `/compliance/alertrule/` o el admin. **Las alertas que ya emitió se
quedan**: una alerta es evidencia ISO 10.2 y borrarlas desde una migración
eliminaría el rastro de que existieron — resolverlas es del usuario.

#### ✅ El gate está verde, incluido el último commit

El commit de `LV-200` paso 2 (`1aea5c1`) se escribió advirtiendo que su gate había
quedado a mitad por agotarse la ventana. **Terminó después y pasó**: 2625 tests,
cobertura 97.24%, `verify.ps1: all checks passed`. La advertencia que lleva ese
mensaje de commit **ya no aplica** — se deja acá dicho porque el mensaje no se
puede reescribir sin rehacer el commit, y una advertencia obsoleta hace perder más
tiempo que ninguna.

Lo que aquel aviso pedía vigilar quedó comprobado: `save_uploaded_file` ganó un
parámetro opcional y sus **tres** llamadores de `apps/compliance/views.py` —alta,
carga masiva y reemplazo de versión— siguen funcionando; sólo el primero pasa el
parámetro nuevo.

Así que los tres commits pendientes están verificados y **listos para desplegar**.

#### Lo que se hizo el 2026-09-02

| Fila | Qué |
|---|---|
| `UX-01`, `UX-03` | La severidad como token en cinco niveles, reutilizando los valores que `LV-D10` ya había medido para AA. Las clases nuevas **no llevan `!important`** |
| `LV-230` | **Defecto propio**: `LV-225` duplicó un tipo de documento. Fusionado, con migración de datos |
| `LV-232` | **Defecto propio**: la cadena de tres alertas era ruido. Se retira el umbral de 15 días |
| `LV-200` paso 2 | La misma carta en varios permisos = un solo archivo, con la guarda de `cleanup_documents` |
| Registradas | `LV-231` (folio desde el PDF), `LV-227`, `LV-228`, `LV-229` |

#### El plan vigente está fuera del repo

**`~/.claude/plans/distributed-cooking-axolotl.md`** — plan consolidado y aprobado
que junta los tres frentes: el informe mensual, el `docs/ux-ui-plan.md` (31 filas
`UX-nn`) y la deuda del `MASTER_PLAN`. Tiene el orden por bloques, los riesgos y
la sección de depuración.

**Lo siguiente en ese orden es el bloque 2: `R3` + `UX-06` juntos** — extraer las
seis plantillas A4 del ZIP a `apps/reporting/templates/` y el `@media print`. El
payload ya devuelve las cifras correctas en producción (12 faenas, 11 permisos
vigentes, 3 en trámite, 14 aeronaves), así que hay contenido real que mostrar.

Antes de `R4` (semáforos) va `UX-01`, que ya está hecho: los tokens existen.

#### Dos cosas que el 2026-09-02 dejó aprendidas

1. **Un nombre que miente cuesta un tipo duplicado.** `LV-230` no salió de leer
   mal: el tipo se llamaba "Autorización DGAC (carta de permiso)" y su propia
   documentación decía que va *hacia* la DGAC. Cuando un nombre y su comentario se
   contradicen, el nombre gana en la cabeza de quien lee.
2. **Que el motor pueda emitir una alerta por regla no significa que deba.**
   `LV-232`. Dos avisos con acciones distintas informan; tres diciendo la misma
   fecha enseñan a no mirar la bandeja.

### Cierre del 2026-09-01 (tarde)

**Desplegado en `p340`: `2d04482`.** Nada pendiente de desplegar, `showmigrations`
en 0. **14 filas cerradas** en la jornada, en seis despliegues, con tres
migraciones (`operations.0023`, `0024`, `0025`) y dos sembrados. Gate final: 2579
tests, cobertura 97.20%.

#### Lo que quedó en la cola

**Código:**

| Fila | Qué falta |
|---|---|
| `LV-218`(b) | El cruce **automático** de NOTAM. El (a) —el enlace— ya está. Antes de codificar: que un fallo de consulta no se lea como "no hay avisos", política de caché, y **preguntar a la DGAC si hay vía oficial** (eso es una conversación, no código) |
| `LV-227` | La narrativa del informe editable en la app. **No** un editor de plantillas: ver la fila |
| `LV-220`(b) | Derivar la región de las coordenadas. Decidido no hacerlo sin marcar que es derivada |
| `LV-200` paso 2 | Un documento con varios sujetos |
| `LV-189` | Estado terminal en el cumplimiento |
| R0/R2–R7 | Los bloques del informe mensual. **Leer `apps/reporting/MAPPING.md` primero** |

**Datos, sin código** — y es lo que más impacto de cumplimiento tiene:

| Fila | Qué falta |
|---|---|
| `LV-74` | **1 aeronave** (`RPA-7126`) sin seguro y **7 credenciales** DGAC sin fecha. Re-medido hoy: eran 3 aeronaves y una ya se cargó; `RPA-2019` no aplica (bodega, ver `LV-229`) |
| `LV-228` | Cuatro operadores sin faena: René Herrera, Natalia Ramos, Jimmy Andrade, David Vidal |
| `LV-98`, `LV-102` | Tipos de documento bajo "Otro", y el calendario — que depende de los dos anteriores |

Y **el correo** sigue siendo el único criterio en rojo, esperando SMTP.

#### ⚠️ Dos diagnósticos escritos resultaron falsos, y conviene no repetirlo

Lo más útil que dejó la jornada no es una fila, es esto:

1. **`LV-207` traía registrado que 5 de 7 colores del menú no llegaban a 3:1**, con
   cifras concretas (`registry 2.41`). Calculado sobre los hex del CSS, `registry`
   da **5.91** y los siete cumplen. Fiarse habría significado "corregir" siete
   colores correctos.
2. **La §6 del SPEC del informe daba por inexistente el modelo de permisos** y lo
   marcaba como bloqueante. Existía desde antes (`FlightPermission`).

En los dos casos el error fue medir o mirar contra la referencia equivocada. **Un
diagnóstico escrito —incluido uno propio de hace semanas— se re-verifica antes de
actuar sobre él**, sobre todo si va a cambiar datos o revertir una decisión. Está
en `AGENTS.md` junto a la razón técnica: un ratio de contraste se calcula, no se
lee de un navegador.

Y el corolario del entorno: **el navegador integrado devuelve valores que no se
corresponden con el CSS para `#sidebar`** (un `!important` inline no cambia el
computado, que es imposible). Un `div` de control sí computa bien, así que sirve
para elementos creados al vuelo y no para ese.

### Cierre del 2026-09-01 (mañana)

Continuación de la jornada del 31. **Desplegado en `p340`: `0a7a2ce`.** Lo que
sigue está commiteado y **sin desplegar** (`9a84c48`: `LV-215`, `LV-216`,
`LV-223`): sólo `collectstatic`, sin migración y sin `bootstrap_roles`.

**Antes de dictar cualquier despliegue**, la lección que costó una caída:

```
uv run python manage.py showmigrations | grep -c '\[ \]'
```

Tiene que devolver `0`. El paso de despliegue es el de **todo lo que falta en la
VM**, no el del último commit.

⚠️ **Ese comando sólo vale con el entorno ya cargado**, y en la primera versión de
este bloque no se decía. Sin `set -a; source <(sudo cat /etc/aerocontrol.env);
set +a`, `manage.py` cae a `config.settings.dev` y `showmigrations` responde por
la base de **desarrollo**: un `0` tranquilizador sobre la base equivocada, que es
peor que un error. El orden correcto está en § "El despliegue, por pasos" —
entorno primero, diagnóstico después.

⚠️ **Y los comandos van sin `ssh` y sobre `/opt/aerocontrol`.** En el cierre del
2026-09-01 se dictaron con `ssh p340 "cd /srv/aerocontrol && ..."`: la ruta no
existe (es `/opt`, no `/srv` — `/srv/aerocontrol-data` es sólo la base) y el `ssh`
sobraba porque quien despliega ya está dentro de la VM, así que pidió contraseña
para conectarse a sí misma. No hubo daño —`cd` falló y el `&&` detuvo el resto—
pero se perdió una vuelta. **Cuando se dicten comandos de despliegue, copiarlos de
§ "El despliegue, por pasos" en vez de escribirlos de memoria.**

#### ⚠️ El próximo despliegue lleva migraciones **y dos sembrados**

Dos migraciones: **`operations.0023`** (`LV-219`, la vigencia admite nulos) y
**`operations.0024`** (`LV-224`, el motivo de excepción del plazo). El paso es
`migrate` + `collectstatic` **con respaldo previo**, no sólo `collectstatic` como
los tres anteriores — la situación que tumbó producción el 2026-08-31.

Y algo que **`migrate` no hace y es fácil de olvidar**, porque no falla, sólo no
aparece:

```
uv run python manage.py seed_document_types
uv run python manage.py seed_alert_rules
```

Sin el primero, la **carta del mandante** (`LV-225`) no existe como tipo y no se
puede cargar: el expediente pediría un papel que la app no ofrece subir. Sin el
segundo, las alertas **T-45 y T-15** (`LV-226`) no se crean y la cadena de
renovación se queda en el aviso de 30 días que ya había. Los dos son idempotentes
—`get_or_create` por `code` y por `name`— así que correrlos de nuevo no rompe nada
ni pisa una regla que alguien haya ajustado a mano.

Es el mismo error que ya costó una vez: `LV-184` quedó a medias en producción
porque `bootstrap_roles` no se corrió, y la lección está en `AGENTS.md` como *"el
gate verifica código, nadie verifica el cableado de producción"*.

Después de desplegar, el chequeo nuevo dice de un vistazo si la operación real
tiene las cartas al día:

```
uv run python manage.py check_client_letters
```

#### ⚠️ El informe de agosto ya se emitió, y es la referencia real

`OneDrive/DGAC/INFORMES/Agosto2026/JEJ-GTE-CT-INF-RPA-2026-08_Agosto2026.pdf`.
**Ese PDF manda sobre la especificación**: son 5 páginas con otra división que los
6 artboards del SPEC, y la estructura real está volcada en
`apps/reporting/MAPPING.md` junto con los indicadores del cierre de agosto, que
sirven de caso de prueba para los colectores.

Tres cosas que salieron de leerlo:

1. ✅ **La Fase 1 del plan del informe, comprometida para octubre, ya está
   implementada y desplegada** (`LV-224`, `LV-225`, `LV-226`). El informe la
   describe con el mismo reparto de roles que llevan las reglas sembradas.
2. ⚠️ **"7 de 11 permisos fueron autorizados por 3 meses y 4 por 2 meses."** Por
   eso `LV-224` **valida** el techo en vez de calcular el vencimiento: calcularlo
   habría falseado 4 de 11 vigencias reales.
3. **La mitad de la Fase 2 (noviembre) también está**: `LV-219` ya rechaza
   registrar un vuelo contra un permiso sin vigencia.

**Buena parte del informe es narrativa escrita a mano** —resumen ejecutivo,
hallazgos, la observación del período, las cuatro fases— y eso es lo que `LV-227`
tiene que resolver, no un editor de plantillas.

#### El informe mensual RPA para la DGAC — R1 hecho

Entró un frente nuevo: JEJ debe emitir cada mes un informe de reportabilidad RPA
(estándar `JEJ-GRI-SS-INS-096`). El diseño y la especificación están fuera del
repo, en `OneDrive/DGAC/INFORMES/Agosto2026/`
(`plantilla-informe-rpa-aerocontrol.zip` con 6 artboards A4, y
`SPEC_REPORTE_MENSUAL_RPA.md`). **El plan aprobado está en
`~/.claude/plans/distributed-cooking-axolotl.md`** y el mapeo campo→modelo en
`apps/reporting/MAPPING.md`.

**Lo más importante que dejó la investigación**: la §6 del SPEC lista siete datos
"que probablemente falten" y **acertó en dos de siete, errando en el que marcaba
como bloqueante**. El modelo de permisos con emisión, vencimiento y carta ya
existía (`FlightPermission`); faltaban la carta del mandante y el plazo, que son
`LV-225` y `LV-224`. Antes de construir cualquier bloque del informe, leer
`MAPPING.md`: `kpis.py`, `upcoming_expirations`, `ComplianceSnapshot`,
`apps/core/pdf.py` y `openpyxl` ya cubren buena parte de lo que el SPEC propone
crear de cero.

Decisiones ya tomadas con el usuario, para no reabrirlas: **no se usa WeasyPrint**
(el repo eligió `reportlab` a propósito, sin paquetes de sistema en la VM) y el
informe se ve en HTML dentro de la app primero, con el PDF automático después.

R2–R7 siguen pendientes. ⚠️ **R6 (envío por correo) está bloqueado por el SMTP**,
no por prioridad.

#### Lo que quedó en cola, en orden de valor

1. **`LV-218` — cruzar los NOTAM de la DGAC con el sector del permiso.** La idea
   más valiosa que dejó el usuario y la más grande. Lo primero es averiguar si
   `aipchile.dgac.gob.cl/notam` ofrece API o feed; **el riesgo manda el diseño**:
   un fallo de consulta no puede leerse como "no hay avisos". La fila tiene el
   detalle.
2. **`LV-217` — los badges de tipo son todos grises**, en vencimientos y en
   alertas. Ojo: la urgencia ya usa color en la misma fila (`LV-148`), así que hay
   que elegir el canal sin canibalizar el rojo.
3. **`LV-207` — los colores del menú.** **Diagnóstico terminado**: sólo dos
   secciones mezclan color adentro (Informes: azul + ámbar; Inventario: azul +
   gris) porque el color se asigna por app de destino y no por sección; y Padrón
   comparte azul con Inventario, Cumplimiento comparte ámbar con Informes.
   **Medido**: en tema claro **5 de 7 familias no llegan a 3:1** (`overview` 2.55,
   `workboard` 2.36, `maintenance` 2.50, `registry` 2.41, `admin` 2.41); en oscuro
   todas están sobre 8. Hay 8 grupos y 7 colores, así que falta uno: el mejor
   candidato medido es **`#65a30d` / `#bef264`** (4.60 sobre navy y 14.04 sobre el
   fondo oscuro), que además supera a todos los existentes en claro.
4. **`LV-221`, `P1` — la altitud se pide en pies y la operación piensa en
   metros.** **Medir producción antes de tocar el campo**: en la captura del
   usuario hay un `120` en un campo rotulado `(ft)`, y 120 ft son 36 m. Puede
   haber permisos con la altitud mal cargada, y eso no se deduce desde acá.
5. **`LV-222` — los rosters de operadores y aeronaves se ven desalineados** al
   buscar, porque la rejilla asume etiquetas cortas y estas ocupan tres líneas. El
   usuario propone un desplegable con buscador; **evaluarlo sin adoptarlo de una**:
   son campos de selección múltiple y `LV-151` eligió la rejilla justamente para
   eso. La fila tiene dos alternativas que conservan lo ganado.
6. **`LV-220` — la región no aparece en la ficha del permiso**, porque `LV-197`
   sacó esas casillas del alta y el plan no siempre las trae.
7. **`LV-208` — el ancho de la barra de navegación no se puede regular** (hoy dos
   estados y nada en medio).
8. **`LV-189`** (estado terminal en el cumplimiento) y **`LV-200` paso 2** (un
   documento con varios sujetos), las dos con su decisión escrita en la fila.

Y lo de siempre: **el correo** sigue siendo el único criterio en rojo, esperando
las credenciales SMTP.

#### Un test caducó al cambiar el mes (`LV-223`), y vale saberlo

El gate de cierre falló con un test que **nadie había tocado**:
`test_only_assessable_deliverables_count` daba `assert 0 == 2`. No era regresión:
el módulo fija su ventana en agosto de 2026 y el test dejaba que el modelo sellara
la fecha con **ahora**, así que pasó el 31 de agosto y cayó el 1 de septiembre.
Costó diagnóstico porque apareció junto a `LV-213` y parecía su consecuencia.

**La señal a recordar**: si un test falla y el diff no toca nada de lo que ese
test afirma, mirar la fecha antes que el diff. Quedó anotado en `AGENTS.md`.

### ⚠️ Producción se cayó con un 500, y la causa fue mía en la comunicación

Después de desplegar `d20057d` el panel devolvía `Server Error (500)`:
`no such column: registry_costcenter.operates_flights`. **`registry.0041` no
estaba aplicada.** El commit anterior (`d09a758`) traía esa migración; el
siguiente no traía ninguna propia, así que se entregó "sólo `collectstatic`" — y
se corrió eso sobre una VM que no había migrado. Se resolvió con `backup` +
`verify_backup` + `migrate` + `restart`.

**La regla quedó en `AGENTS.md`**: el paso de despliegue es el de **todo lo que
falta en la VM**, comparando su `git log -1` contra lo que se sube y uniendo los
pasos de las filas que hay en medio. Una advertencia al final del mensaje no
cuenta. Y `showmigrations <app> | tail -6` es el diagnóstico de treinta segundos
ante un 500 tras desplegar: una migración sin `[X]` con código que ya la usa lo
explica sin leer un traceback.

### Sexta tanda: tres defectos, dos de ellos míos del mismo día

Sin desplegar:

- **`LV-211`, `P1`** — **editar un centro de costo borraba cinco campos.** La
  ficha dibuja campo por campo desde `LV-36`, y un campo que no se dibuja **no se
  envía**: un checkbox ausente vale `False`. Le pasó al usuario a los minutos —
  editó `CC410` y la faena desapareció de la tabla sin que él la desmarcara. Al
  escribir el test aparecieron **otros cuatro preexistentes**: `latitude`,
  `longitude` (de donde sale el pronóstico de una faena) y los tres criterios de
  aceptación del contrato (`R7.4`). Bastaba corregir un nombre para perderlos, y
  venía de antes de esta jornada. El test recorre `Meta.fields` y exige la
  plantilla completa.
- **`LV-210`** — la caja de borradores del listado se dibujaba vacía con el botón
  suelto. Es la mitad que `LV-209` no arregló: resolvió el *ocultar* y no el
  *estado inicial*. `d-none` pasa al HTML y el JS apaga explícitamente.
- **`LV-212`** — "vence pronto" en su propia columna, dejando el total limpio.

**Paso de despliegue: `collectstatic`.** Sin migración.

### Quinta tanda: los dos pendientes, dos pedidos nuevos y un defecto

Desplegados ya `068ccfa` y `d09a758`. Después de eso, **sin desplegar**:

- **`LV-209`** — el botón "Descartarlo" del borrador. **Hacía la mitad**: borraba
  el borrador y no ocultaba el aviso, así que parecía muerto. La causa era CSS y
  medible: `[hidden]` está en la posición ~10.129 del bundle de Bootstrap y
  `.d-flex` en la ~163.993 — misma especificidad, los dos `!important`, gana el
  último. **El atributo `hidden` no oculta un elemento con `d-flex`.** `.d-none`
  (~164.069) sí, y de ese orden depende el arreglo, así que hay un test que lo
  vigila. **El mismo defecto lo tenía el aviso que `LV-198` había agregado.**
- **`LV-205`** y **`LV-206`** — ver arriba, ya desplegados en `d09a758`.

Y quedaron **registradas sin implementar**: `LV-207` (los colores del menú lateral
se mezclan dentro de una misma sección, así que el color no agrupa ni distingue) y
`LV-208` (el ancho de la barra de navegación no se puede regular: hoy hay dos
estados y nada en medio).

**Paso de despliegue: `collectstatic`.** Sin migración.

**Desplegado `6dc2acb` en `p340`** (0 estáticos copiados, que es lo correcto: esa
tanda tocó plantillas y Python, nada bajo `static/`).

### Cuarta tanda: los tres pedidos que tenían una decisión adentro

El usuario pidió avanzar y **decidir cada una**. Sin desplegar:

- **`LV-197`** — el alta deja de pedir las seis casillas que el plan rellena.
  **Este pedido ya era el de `LV-166`**, con su frase casi idéntica, resuelto
  entonces sólo en la edición. Lo que cambió es la política: que el dato no esté
  *todavía* no es razón para pedirlo a mano, porque hay tres caminos y ninguno es
  tipearlo. La edición los sigue ofreciendo mientras estén vacíos, y el escape
  `?ubicacion=manual` —que existía sólo en la edición— se le agrega al alta.
- **`LV-198`** — el listado de Permisos dice cuántos borradores hay. **Por
  navegador**, porque `localStorage` es la decisión de `LV-154` y prometer un
  listado que otro no ve sería peor. Más el paréntesis vacío, arreglado.
- **`LV-200`** — 🔶 **paso 1**. `content_sha256` estaba a medias: sólo lo escribía
  el importador de `Z:`, así que **todo lo subido por la app lo tenía vacío**.
  Ahora se calcula al subir y avisa —sin bloquear— nombrando el documento que ya
  tiene ese archivo. **El paso 2 sigue siendo una decisión de modelo** y está
  escrita en la fila: multi-sujeto toca el informe de cumplimiento; compartir el
  blob pone dos filas sobre el mismo archivo.

⚠️ **Tres tropiezos propios de esta tanda, los tres en `AGENTS.md`**:
`{% translate %}` **no traduce un literal con `%(count)s`** (devuelve el inglés
donde `gettext` devuelve el español); **`self.instance.pk` nunca es falsy** en
este proyecto porque `BaseModel.id` tiene `default=uuid.uuid4`, así que la guarda
`if not self.instance.pk` no comprueba lo que dice; y **agregué dos veces un
método que la clase ya tenía más abajo** (`get_context_data`, `save`) — Python se
queda con el último y el nuevo no corre, sin error ninguno.

**Paso de despliegue: `collectstatic`.** Sin migración.

⚠️ **Tres tests pasaban por la razón equivocada y se corrigieron con su razón
escrita**, todos destapados por estas filas: el de `LV-129` colgaba su "documento
de la empresa" del centro de costo en vez del tenant; el de `R7.7` atrapó la
tarjeta nueva imprimiendo "0/0" con la base vacía; y el de `LV-188` falló con
`KeyError` sobre los tres modelos nuevos, que es **exactamente** lo que su
docstring prometía hacer.

### Los cuatro pedidos del usuario de hoy, cerrados

- **`LV-192`** — el listado de permisos abre con folio y **faena** (chip `CC738`,
  el mismo de la bandeja y del panel). El dato iba en el CSV desde `LV-53`, o sea
  que estaba en el archivo exportado y no en la pantalla.
- **`LV-193`** — "Completado" fuera del selector de "Corregir el estado".
  `LV-155` lo había retirado del flujo y **esa pantalla quedó fuera**: era la
  única capaz de volver a escribir el estado retirado. `JEJ-2026-003` se sigue
  encontrando con el filtro y se puede corregir hacia otro estado.
  **"Rechazado" se queda, confirmado por el usuario**: es un hecho de la DGAC y
  está en `CREATABLE_STATUSES`, así que retirarlo dejaría sin forma de corregir
  un permiso marcado así por error.
- **`LV-194`** — los dos últimos renglones del expediente operativo, retirados.
  **No era una limpieza**: nacían en ámbar y ninguno podía cerrarse (SIGO salió
  del menú en `LV-150`; la bitácora de vuelos se lleva contra la faena), así que
  el encabezado decía "2 por confirmar" en todo permiso para siempre y ningún
  expediente podía leerse como completo.
  **Y la decisión que ese retiro volvió urgente, tomada por el usuario el mismo
  día: la revisión meteorológica es necesaria y se queda como está.** Al irse los
  otros dos pasa a ser el único renglón que puede quedar en ámbar, y la
  diferencia es la que importa: **ésta sí se puede cerrar**, con el botón de la
  ficha del plan. Un ámbar que se resuelve es lo que un checklist debe tener.
  No se hizo bloqueante: el expediente no bloquea nada a propósito (`LV-107`).
- **El cruce del Capítulo 1 Rev 17** — ver abajo, que tiene su propia sección.

### El despliegue, por pasos

`p340` está en `22f379f` y le faltan `LV-184` a `LV-195`. **Por pasos y no
encadenado**: el `;` que necesita la carga del entorno corta un `&&`, y esa es la
forma exacta en que se produjeron los dos despliegues fantasma del 2026-08-27.

```
cd /opt/aerocontrol && git status --short --branch
```

La primera línea tiene que decir `## main...origin/main` y **no** `## HEAD (no
branch)`. Después `git pull`, `uv sync`, y el entorno **antes** de cualquier
`manage.py`:

```
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo $DJANGO_SETTINGS_MODULE; echo $DB_PATH
```

Tiene que decir `config.settings.prod` y `/srv/aerocontrol-data/db/aero_ops.sqlite3`.
Sin `set -a`, `source` define variables de shell y no de entorno, y `manage.py`
cae a `config.settings.dev` — que acá no sería un error visible sino trabajar
sobre la base equivocada. Luego, con respaldo previo:

```
uv run python manage.py backup && uv run python manage.py verify_backup
uv run python manage.py migrate --no-input
uv run python manage.py bootstrap_roles
uv run python manage.py collectstatic --no-input
sudo systemctl restart aerocontrol
git log --oneline -1
```

**`bootstrap_roles` no es opcional**: sin él, el permiso `view_assessment_answers`
de `LV-184` existe y no lo tiene nadie salvo `root`, así que media fila queda sin
efecto. Y después, en la app: **el rol `Compliance` a Ariel Ortega y a
Cristóbal**. La única migración de la tanda es `registry.0039` (`LV-184`, sólo el
permiso; `sqlmigrate` la reporta `(no-op)`).

### El cruce del manual, después de desplegar

El comando ya existía (`chapter1_docx_import`, con `LV-133` adaptado a la Rev 17);
lo que faltaba para poder confiar en él eran **`LV-190` y `LV-195`**, así que va
después del despliegue. Verificado sobre
`1 Capítulo 1 202608_R17_reparado.docx`: **17 aeronaves** (las 16 de producción
más `RPA-7213`) y **48 fichas permanentes**, los 48 RUT válidos con su dígito
verificador, 48 números de empleado distintos, ningún campo vacío, y la sección
1.5 cerrando en `EVENTUALES (NO APLICA)` sin nada después — o sea que 48 es la
dotación real y no un parser desbordado. Producción tiene 42, así que la corrida
crea alrededor de seis.

**El cruce contra `p340` no se puede hacer desde una sesión de agente** (`ssh`
responde `Permission denied (publickey)`, y la base local está vacía), así que va
en la VM. El documento tampoco está allá — vive en OneDrive—, así que primero se
copia, con nombre simple para no pelear con espacios y acentos:

```
scp "D:\OneDrive - J.E.J. Ingeniería S.A\DGAC\Manual\ManualRev17\1 Capítulo 1 202608_R17_reparado.docx" levdigital01@p340:/tmp/cap1.docx
```

Y **el informe primero**, que no escribe nada:

```
cd /opt/aerocontrol && uv run python manage.py chapter1_docx_import --source /tmp/cap1.docx --export-dir /tmp/cap1
```

Leer `already_on_file`, `operators_ready` y cualquier línea `CONFLICT` antes de
aplicar. **Un `CONFLICT` no se fuerza**: significa que el manual y el padrón no
coinciden sobre una persona o una aeronave, y la línea dice qué ficha ocupa el
valor. Con 42 fichas en el padrón, lo esperable es que la mayoría salga saltada:
un `already_on_file: 0` sería señal de que el entorno no apunta donde se cree.
Sólo cuando no haya conflictos:

```
cd /opt/aerocontrol && uv run python manage.py chapter1_docx_import --source /tmp/cap1.docx --apply --skip-existing
```

⚠️ **Y una deuda que `LV-190` deja a la vista**: las fichas que este import creó
antes de hoy tienen el **RUT con puntos**, porque `create()` no pasa por
`clean()`. `operator_with_rut` compara contra la forma canónica, así que el
formulario de alta no encuentra a esas personas y dejaría crear su duplicado a
mano. Normalizarlas es una corrida de datos aparte y hay que medirla primero.

### Lo que sigue abierto, con el camino ya acordado

Tres de los cuatro pedidos del 2026-08-28 siguen en pie —**colores por elemento
en el mapa**, **la tendencia en el panel** y **el ancho de la hoja SIGO**— con el
detalle en la sección de abajo, que no cambió. El cuarto era el pendiente del
test y quedó cerrado. Y nueva: **`LV-189`**, el estado terminal en el
cumplimiento, que `LV-188` destapó y deliberadamente no hizo — está en el tablero
con el porqué de no haberlas mezclado.

### Y lo de siempre, que sigue mandando

El **correo**: único criterio en rojo, listo para encenderse desde `LV-182`, sólo
faltan las credenciales SMTP con los nombres de variable de siempre. Y los dos
timers (`check_scheduled_jobs`, `verify_backup`) siguen sin instalar.

## Cierre del 2026-08-28 (tarde)

Continuación del mismo día. Se cerraron `LV-184` a `LV-186` y quedan **cuatro
pedidos del usuario abiertos, con el camino ya acordado**.

### Estado exacto

- **`origin/main` = `b0037f3`** (más el commit de `LV-186` si su gate cerró
  verde — mirar `git log`). **`p340` está en `22f379f`**: le faltan `LV-184`,
  `LV-185` y `LV-186`.
- **Ese despliegue lleva `migrate` + `bootstrap_roles` + `collectstatic`.** Sin
  `bootstrap_roles`, el permiso `view_assessment_answers` de `LV-184` existe y no
  lo tiene nadie salvo `root`, así que **Compliance no vería la clave de
  respuestas** — media fila sin efecto.
- Después de desplegar, el usuario tiene que **darles el rol `Compliance` a
  Ariel Ortega y a Cristóbal** para que vean las respuestas correctas.

### Lo que el usuario pidió y quedó acordado, sin hacer

1. **Colores por elemento en el mapa del plan.** Hoy `static/js/geo/main.js`
   dibuja **todo** con un único `STROKE = "#0f9f95"`: círculos, líneas, polígonos
   y puntos. En un plan de siete circunferencias las siete son idénticas y el
   panel de capas no ayuda a distinguirlas. Acordado: un color por elemento
   ciclando **la paleta que la app ya tiene** (los cuatro tonos del menú y de la
   hoja SIGO, no una nueva), **la misma marca de color en el panel de capas**
   —que es el verdadero valor: hoy la lista dice "CG-07 | Circunferencia gran…" y
   el mapa no dice cuál es—, y un centro que se distinga del borde. El modo
   *diff* conserva sus colores por encima: ahí el color significa estado.
2. **Tendencia en el panel** (el usuario eligió este camino, textual: *"un panel
   de cumplimiento se vuelve interesante cuando muestra una tendencia"*).
   **El dato ya existe y nunca se mostró**: `ComplianceSnapshot` (`R7.7`) guarda
   `total`/`valid`/`expired`/`due_7`/`due_15`/`due_30` por fecha y faena, con
   índice hecho para "el snapshot más reciente antes de X", y su propio docstring
   dice que existe *"para hacer posible la tendencia"*. El timer `snapshot` corre
   a las 23:00 desde el 2026-08-12, así que hay **unas dos semanas** de historia
   real. **Por eso la ventana no puede ser fija**: comparar contra "hace 30 días"
   inventaría una línea base. Comparar contra el snapshot más viejo disponible
   dentro de la ventana **y decir contra qué fecha compara**.
3. **La hoja de SIGO aprovecha mal el ancho.** El usuario dijo que se lee bien y
   que sirve para copiar, pero que sobra espacio. **Lo que NO hay que hacer es
   apretar las casillas**: están ordenadas como el formulario del Estado y su
   trabajo es que se copie sin equivocarse de fila; ganar densidad se paga en
   errores de transcripción, que es lo que `LV-171` vino a reducir. Lo propuesto
   y no confirmado: en pantallas anchas, **el mapa al lado** de los datos en vez
   de debajo.
4. **El test de punta a punta de `LV-186`, y el hallazgo que puede esconder.**
   Ver el comentario al final de `apps/dashboard/test_lv186_...py`: un documento
   vigente, dentro de la ventana y con `is_current_version=True`, sale del panel
   con `expirations == []` incluso con `admin_user`. Si eso se reproduce en
   producción **no es un fixture mal armado sino documentos por vencer que la
   pantalla no muestra** — la familia de `LV-120` y `LV-146`. Averiguarlo antes
   de dar la fila por buena.

### Y lo de siempre, que sigue mandando

El **correo** es el único criterio en rojo y ahora está listo para encenderse:
`LV-182` migró la configuración a `MAILERS`, así que sólo faltan las credenciales
SMTP con **los mismos nombres de variable de siempre**. Y los dos timers
(`check_scheduled_jobs`, `verify_backup`) siguen sin instalar.

## Cierre del 2026-08-28 (mañana)

Segunda jornada de revisión en vivo, y la más larga hasta ahora: **once filas
cerradas y desplegadas** (`LV-169` a `LV-179`).

### Estado exacto

- **`p340` está en `a2c7008`**, desplegado y verificado. **`origin/main` siguió
  avanzando después** con `LV-180` y `LV-181`, que **quedaron SIN desplegar**:
  son lo primero al retomar. `LV-180` **lleva `migrate`** (`compliance.0024`,
  renombra una fila); `LV-181` es el salto a Django 6.1, así que el `uv sync` de
  la VM va a instalar Django 6.1 y DRF 3.18.
- **`pwsh scripts/verify.ps1` verde sobre lo último**: 2284 tests, cobertura
  96.96%, ya con Django 6.1.
- **Tres migraciones aplicadas hoy**, todas limpias: `registry.0037` (`LV-169`,
  sin SQL), `registry.0038` (`LV-177`, reconstruye la tabla de operadores) y
  `geo.0006` (`LV-178`, dos columnas vacías). Respaldos previos tomados **y
  verificados** (`aero_ops_20260828_095511` y `aero_ops_20260828_102722`).
- **`split_operator_names --apply` corrió en producción**: 41 de 42 fichas con
  el corte nombres/apellidos hecho. **Queda una a mano: Boris Santibáñez** —
  dos palabras, y ahí no se puede saber si falta el apellido materno. Mientras
  tanto aparece ordenado por su nombre completo.

### Lo que se cerró, en una línea cada una

`LV-169` el ID de empleado se deriva del RUT · `LV-170` el menú en seis grupos
plegables con estado recordado · `LV-171` jerarquía en la hoja de campo de SIGO
· `LV-172` el catastro cierra con su total · `LV-173` root archiva un intento de
la prueba, nunca lo borra · `LV-174` la tipografía normalizada · `LV-175` la
habilitación como la escribe la DGAC · `LV-176` cerrar el plan junto con sus
permisos, sin cascada · `LV-177` el padrón ordenado por apellido · `LV-178` el
motivo del cierre, para poder contarlo · `LV-179` el clima del panel enlaza a
donde queda registrado.

### Tres cosas del día que valen para mañana

- **`makemessages` inventó traducciones en las SEIS corridas del día**, y dos
  eran graves: una copió en un mensaje nuevo una traducción con `%(date)s` —un
  marcador que ese mensaje no tiene, habría reventado con `KeyError` al
  renderizar el catastro— y otra tradujo *"Rejected by the DGAC"* como
  *"Reportada a la DGAC"*, que en cumplimiento es lo contrario. **El
  procedimiento de `AGENTS.md` no es opcional**: después de cada corrida, grep
  `fuzzy` y corregir a mano. El guardián las cazó todas.
- **`verify_backup` sin argumentos verifica el último respaldo.** Ahorra el
  copiar-pegar de la ruta, que es donde se rompió el primer intento del día.
- **Un guardián que sólo pasa mientras nadie use el flujo documentado no está
  vigilando, está esperando.** El de i18n exigía cadenas que viven dentro de un
  `{% comment %}`, de donde Django no extrae; llevaba latente desde `LV-150` y
  estalló en la primera regeneración del catálogo.

### Lo que queda de la cola, con las decisiones ya tomadas

1. **«Geo source» a un nombre en español.** Sugerido: *"Archivo KMZ/KML de
   origen"*. **Lleva migración de datos**, así que ese despliegue **no** será
   sólo `collectstatic` — el `name` se fija sólo en los `defaults` del
   `get_or_create` (`apps/geo/views.py`), y la fila que ya existe en producción
   no se renombra sola. El **código** sigue siendo `GEO_SOURCE`: lo referencian
   otras partes y el usuario ve el nombre, no el código.
2. ~~**Clima de Casa Matriz.**~~ **Resuelto de otra manera el 2026-08-28
   (`LV-179`), y conviene saber por qué**: el usuario preguntó si sumar la
   temperatura al plan, y la respuesta fue que **el plan ya la tiene** —`R8.1`
   muestra el pronóstico sobre el área dibujada y ahí se archiva como evidencia.
   Duplicar cifras habría creado dos pantallas con el mismo pronóstico y una
   sola que deja constancia, que es una invitación a mirar la que no registra.
   Se resolvió con un enlace. **Si vuelve a pedirse el clima de la oficina**, la
   condición sigue en pie: las coordenadas de Casa Matriz van **rotuladas como
   aproximadas y sólo para el pronóstico**, porque ninguna decisión aeronáutica
   puede leerlas.

### Brechas: cuatro cerradas el 2026-08-28, una abierta y con forma nueva

- ~~El CI nunca estuvo verde~~ ✅ **Causa encontrada y arreglada (`LV-180`)**:
  `${{ runner.temp }}` **no existe en `jobs.<id>.env`**, así que el workflow
  **abortaba al arrancar** — nunca corrió un test. **Falta confirmar la primera
  corrida real en GitHub**, que desde una sesión de agente no se ve.
- ~~4 ramas dependabot, una es Django 6.1~~ ✅ **Hecho (`LV-181`)**: 6.0.8 → 6.1
  con el gate verde y **sin un solo cambio en nuestro código**. El único bloqueo
  fue de terceros — Django 6.1 quitó `cc_delim_re` y el DRF instalado lo
  importaba; el piso sube a `djangorestframework>=3.18`.
- ~~6 ramas viejas sin mergear~~ ✅ **Quedan dos** (`LV-180`), y están
  documentadas en `BACKLOG.md` junto al ítem B-06 que implementan. Las borradas
  tienen su SHA anotado ahí.
- ~~`docs/dev/remote-vm-operations.md` sólo en `p340`~~ ✅ **Versionado**,
  reconciliando dos contradicciones: usaba el nombre DNS que no resuelve, y su
  bloque de despliegue **no incluía el respaldo ni su verificación**.
- ⚠️ **El correo saliente sigue sin salir, y el trabajo cambió de forma.**
  `EMAIL_HOST` sigue vacío en `p340`: las siete notificaciones se imprimen en el
  journal. Sigue siendo el bloqueador del criterio 2. **Pero Django 6.1 deprecó
  la familia `EMAIL_*` completa en favor de `MAILERS`, con retiro en Django
  7.0** (27 avisos nuevos en la suite; toca `config/settings/base.py:214-231` y
  el `get_connection()` de `check_email`). **El orden correcto es: primero
  migrar la configuración a `MAILERS`, después cargar las credenciales** —
  hacerlo al revés es configurar hoy una API que Django 7.0 borra, y rehacerlo.

## Cierre del 2026-08-27

Sesión de revisión en vivo sobre la app desplegada: el usuario fue reportando
pantalla por pantalla y se cerraron siete filas (`LV-162` a `LV-168`).

### Estado exacto

- **`origin/main` = `0f18305`**, y **`p340` está en `0f18305`** ✅ — el lote
  completo `LV-162`..`LV-169` desplegado y verificado el 2026-08-27
  (`git log -1` coincidiendo con el `main` pusheado, `registry.0037` aplicada y
  `showmigrations` en `[X]`). **`pwsh scripts/verify.ps1` verde**: 2199 tests,
  cobertura 96.89%, ruff, bandit y pip-audit sin hallazgos.
- **`LV-169` fue el primero del lote con migración**, y el `migrate` se saltó en
  el primer intento —se fue del `echo` derecho al `collectstatic`— y se aplicó
  después. No hubo daño porque `0037` no emite SQL, pero la lección es del
  runbook: **cuando el lote trae migración, el `migrate` es un paso propio y hay
  que verlo aplicar**, no darlo por incluido en la cadena de `&&`.
- **Desde una sesión de agente no hay acceso a `p340`** (`ssh` responde
  `Permission denied (publickey,password)`, verificado otra vez ese día), así
  que el bloque de despliegue lo pega el usuario en su sesión SSH.
- **`LV-168` es una regresión propia de `LV-163`, encontrada por el usuario en
  producción el mismo día.** Colapsar los espacios del banco se llevó los saltos
  que separaban los ítems `I.`/`II.`/`III.` en 6 preguntas de 100 — justo las
  que preguntan "SÓLO I Y II" contra "SÓLO II Y III". Vale como aviso: una
  normalización de texto que "no cambia ninguna palabra" **sí puede cambiar
  dónde corta el renglón**, y eso en una pregunta de examen es contenido.
- **`LV-168b` salió de ahí mismo**: cortar los ítems destapó que el enunciado se
  dibujaba **fuera** de su tarjeta, porque un `<legend>` sin flotar se monta
  sobre el borde del `<fieldset>`. Vale como método más que como arreglo: la
  duda se cerró **midiendo en el navegador** (0 px contra 21 de sangría
  superior), después de que una lectura a ojo de una captura me hiciera afirmar
  primero que el borde cruzaba el texto —lo que era falso— y antes negar que
  hubiera un problema —lo que también era falso—. Para medir así, `.claude/launch.json`
  admite un servidor estático temporal sobre la raíz del repo; el panel del
  navegador **no ejecuta JS sobre `file://`**, sólo sobre `http://`.
- **⚠️ `p340` estaba en HEAD desprendido en `9c4d063`, y por eso las tandas del
  2026-08-26 y del 2026-08-27 nunca se habían desplegado.** Un rollback viejo
  (`git checkout <commit>`) dejó la VM sin rama: `git pull` fallaba con *"You are
  not currently on a branch"*, pero `collectstatic` y el `restart` corrían igual
  y el despliegue parecía exitoso. Se arregló con `git checkout main && git pull`
  (14 commits de fast-forward). `9c4d063` era ancestro de `main`, así que no se
  perdió nada. La lección quedó en `AGENTS.md`: **el primer comando de todo
  despliegue es `git status --short --branch`.**
- **Sin migraciones** en todo el lote. El paso extra al desplegar fue
  **`collectstatic`**: cambia `static/css/app.css` y entra
  `static/js/quiz-progress.js`. Sin él, con el `STORAGES` de `prod.py` toda
  etiqueta `{% static %}` falla.

### Lo único que quedó abierto de esta sesión

**Habilitaciones en la ficha del operador**, esperando decisión del usuario. En
producción se ven tres filas (`Serie Matrice`, `Serie Phantom`, `sensefly eBee`)
con emisión y vencimiento en `—`: son las que sembró `seed_operator_qualifications`
(`LV-12b`) parseando el texto libre de `authorizations`, sin fechas. Es el mismo
`NULL` que `LV-152` definió como *"nunca se ingresó"*. Y hay dos decisiones
suyas que apuntan distinto: `R5.8` dice mostrar el catálogo estructurado en la
ficha, y `LV-152` dice *"poner directamente en el recuadro lo que dice la DGAC,
no más; no buscar más allá de estandarizar"*. Las tres salidas que se le
plantearon, con la segunda como recomendada:

1. Dejarlo y cargar las fechas a mano por operador.
2. Mostrar en la ficha el texto libre de la DGAC y **ocultar** el bloque
   estructurado con el patrón de siempre (se oculta la vista, no se borra el
   dato, así `Qualification` sigue alimentando el aviso de compatibilidad de
   `B4.4` y las alertas de vencimiento). Sin migración.
3. Mostrar sólo las habilitaciones con fecha — el arreglo más chico, pero deja
   habilitaciones invisibles sin avisar.

**No implementar ninguna sin que el usuario elija**: cuál de las dos pantallas
manda es decisión de negocio.

Por pasos, mirando la salida de cada uno — **no como una sola línea encadenada**,
que es como se produjo el despliegue fantasma del 2026-08-27:

```bash
cd /opt/aerocontrol
git status --short --branch     # 1. debe decir "## main...origin/main", NO "## HEAD (no branch)"
git checkout main && git pull && git log --oneline -1   # 2. debe terminar en el commit pusheado
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo "settings=$DJANGO_SETTINGS_MODULE  db=$DB_PATH"    # 3. debe decir config.settings.prod
uv sync && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```

Después del restart, las dos pantallas que conviene mirar con ojo crítico son
las de `LV-165` (modo oscuro: **no se aclaró ningún gris**, se agregó el
guardián que faltaba) y `LV-166` (el permiso ahora **omite** los campos que el
plan no provee — el KMZ no trae altitud, y un plan multi-círculo no aporta
coordenadas).

### Lo que se cerró, y en una línea cada una

`LV-162` el reparto de columnas de Operadores (la habilitación pasa de 281 a
436 px medidos; el encabezado ya no pisa al vecino) · `LV-163` la prueba de
conocimientos se lee (un solo elemento pesado por pregunta, opciones clicables,
barra de avance) · `LV-164` el catastro corta bien las hojas y ningún encabezado
queda huérfano en ningún PDF · `LV-165` el contraste de la paleta queda vigilado
—**ya cumplía AA**, no se aclaró ningún gris— · `LV-166` el permiso deja de pedir
lo que el plan provee · `LV-167` el catastro con las dos vigencias, en horizontal.

### La cola que queda, con lo ya decidido

En el orden que el usuario aprobó. **Las decisiones ya están tomadas**, no hay
que volver a preguntarlas:

1. ~~**Navegación.**~~ ✅ **Hecha y desplegada el 2026-08-28 (`LV-170`).** El
   ancho se **midió** (272 px es el mínimo real, quedó en 280) y el `title` de
   las filas largas ya lo ponía `app.js`, así que esa mitad no necesitó código.
   Texto original, por si hace falta el contexto: partir *Padrón* (nueve entradas de veinte) en *Padrón*
   (faenas, aeronaves, operadores) e *Inventario y movimientos* (baterías,
   asignaciones, movimientos). Un grupo **Informes** con el catastro y el reporte
   juntos: el usuario los fue a buscar ahí y por eso los confundió. Grupos
   colapsables con el estado recordado, barra más ancha (hoy 248 px corta
   "Documentos de la empresa" y "Evaluación de conocimient…"), y `title` en lo
   que igual se corte.
2. ~~**Tablero SIGO menos gris.**~~ ✅ **Hecho y desplegado el 2026-08-28
   (`LV-171`).** No se aclaró ningún gris, como estaba decidido: lo que cambió
   fue la jerarquía (el valor manda, el rótulo se aquieta) y el acento por
   tramo. Latitud y longitud comparten acento porque son una sola coordenada.
3. ~~**ID de empleado automático desde el RUT.**~~ ✅ **Hecho y desplegado el
   2026-08-27 (`LV-169`).** Quedó como estaba decidido, y con dos hallazgos que
   valen para lo que sigue: la derivación se mudó a `apps/registry/rut.py`
   **porque `chapter1_docx_import` armaba la suya**, y dos copias del mismo
   formato terminan duplicando fichas en silencio; y el aviso de duplicado hubo
   que hacerlo correr **sobre el valor derivado**, porque la unicidad por tenant
   no la valida Django desde el formulario y el choque llegaba como 500.
4. ~~**Root archiva intentos de la prueba.**~~ ✅ **Hecho el 2026-08-28
   (`LV-173`), pendiente de desplegar.** La premisa se **verificó**:
   `generate_alerts` filtra `is_active=True`, así que archivar el intento que
   sostiene la vigencia sí le apaga la alerta a esa persona. Por eso hay
   confirmación, y **sólo** cuando al archivar la persona queda sin prueba
   vigente: advertir en los otros casos sería ruido, y el ruido enseña a no
   leer.
5. **«Geo source» a un nombre en español.** Sugerido: **"Archivo KMZ/KML de
   origen"**. Ojo con dos cosas: el `name` se fija sólo en los `defaults` del
   `get_or_create` (`apps/geo/views.py:454`), así que **hace falta una migración
   de datos** para renombrar la fila que ya existe en producción; y el **código**
   es `GEO_SOURCE` (no `geo-source`) y **no conviene cambiarlo** — el usuario ve
   el nombre, y el código lo referencian otras partes. `test_lv149_...:117` usa
   `geo-source` por error y conviene alinearlo.
6. **Clima de Casa Matriz como opción base del selector.** Ya está el
   reconocimiento hecho: `_weather_candidates` devuelve `(permits, sites)` y
   `_resolve_weather_choice` mapea `kind ∈ {permission, cost_center}` buscando
   **dentro de las listas ya cargadas** (nunca un `get()` fresco, ver `LV-147`).
   Para la casa matriz hace falta un tercer `kind` = `"hq"` que se resuelve
   **sin registro**: hay que interceptarlo **antes** de la guarda del `":"`, con
   valor `"hq"` a secas. Las coordenadas van en `apps/core/branding.py` junto al
   resto de la identidad, **rotuladas como aproximadas y sólo para el
   pronóstico** — ninguna decisión aeronáutica las lee. Es la única opción del
   selector que no necesita permiso, porque no revela ningún registro.

### Dos preguntas del usuario que quedaron contestadas, para no reabrirlas

- **Catastro y Reporte se quedan separados.** Responden preguntas distintas: el
  reporte es una foto de un **período** con comparación y tendencia ("¿están
  vigentes mis papeles?"), el catastro una foto a una **fecha de corte** sin
  período ("¿qué tengo inscrito?"). La prueba: el catastro no tiene sentido con
  un rango de fechas y el reporte no tiene sentido sin él. Lo que sí había que
  arreglar era el **nombre** que lo mandó al lugar equivocado, y eso lo resuelve
  el grupo *Informes* del punto 1.
- **Los grises del modo oscuro no se tocan.** Ver `LV-165`: la paleta cumple AA
  con holgura y hay tests que lo vigilan. Lo que se percibe como "apagado" es
  falta de jerarquía y color.

### Una trampa nueva de este entorno, ya escrita en el código

**El panel de navegador congela las transiciones CSS.** Costó una persecución en
`LV-163`: el estado de una opción elegida no se pintaba y se culpó a `:has()`,
que no tenía nada malo. Con `transition: none` los dos selectores dan el valor
correcto. Está escrito en `static/css/app.css`, junto a `.quiz-option`. **Si un
estado no se pinta al verificar ahí, sospechar de la transición antes que del
selector.**

## Cierre del 2026-08-26

`main` = `origin/main`, árbol limpio salvo `.vscode/` (sin versionar).
`pwsh scripts/verify.ps1` verde: **2114 tests**, cobertura 96.83%, ruff, bandit y
pip-audit sin hallazgos. De 1755 a 2114 tests en el día, en dos tandas.

Y el gate encontró un bug que llevaba meses escondido: `test_r72_batteries.py`
comparaba una fecha en UTC contra lo que la plantilla renderiza en hora de
Santiago, así que **fallaba entre las 20:00 y la medianoche** y pasaba el resto
del día. Sobrevivió desde `R7.2` porque el gate rara vez corre en esa ventana; se
arregló en su propio commit, comprobado en los dos sentidos. Si alguna vez el
gate falla de noche en un test de fechas, es esta forma de defecto: comparar
contra `timezone.now()` en vez de `timezone.localtime(...)`.

### ⚠️ Qué está desplegado y qué no

**Esto es lo primero que hay que mirar, y es donde este archivo se puso rancio
antes** (el 2026-08-24 dijo un sha que ya no era y dos mensajes de planificación
se construyeron encima). **Verificá contra la VM, nunca contra este párrafo.**

- **`p340` está en `684ef79`** — la primera tanda del día, desplegada de punta a
  punta y verificada con datos: respaldo previo (`aero_ops_20260826_165944`),
  `registry.0036` aplicada, `bootstrap_roles` corrido (permisos nuevos:
  `view_costcenter` para tres roles y los dos de la evaluación), `collectstatic`,
  y `sync_jac_insurance --apply` que corrigió **dos** aeronaves: `RPA-5534` de
  2026-08-08 a **2027-08-24** (el caso que el usuario reportó) y `RPA-5532` de
  2027-08-04 a 2027-08-06.
- **La segunda tanda está en `origin/main` y NO desplegada.** Son cuatro filas
  (`LV-144`, `LV-145`, `LV-149`, `LV-150`), el comando de `LV-119` y el arreglo
  del test de baterías, desde `2f71763`. **El usuario pidió expresamente
  confirmar antes de mandar a operación**, así que el despliegue quedó esperando
  su visto bueno, no olvidado.
- **Sin migraciones en la segunda tanda.** El paso extra es **`collectstatic`**:
  entran `static/img/jej-logo-blue.png` (el logo del membrete) y
  `static/js/sigo-copy.js` (los botones de copiar). Sin él, en producción los
  estáticos llevan hash y `{% static %}` falla — pero el logo del PDF **no** se
  lee por URL a propósito, así que un `collectstatic` olvidado rompe el JS de
  copiar y no el membrete.

### Dos cambios de infraestructura que hay que saber

- **El repositorio es privado desde hoy** (a pedido del usuario). No tiene forks,
  así que no quedó copia pública. Consecuencia práctica: la VM ya no puede clonar
  ni tirar por HTTPS anónimo.
- **`p340` tira por SSH con una llave de despliegue de solo lectura**
  (`p340-aerocontrol`, id 161420193). La llave se llama `~/.ssh/aerocontrol_deploy`
  —nombre no estándar— así que el repo tiene
  `core.sshCommand = ssh -i ~/.ssh/aerocontrol_deploy -o IdentitiesOnly=yes`
  configurado localmente. Sin eso, `git pull` responde
  `Permission denied (publickey)` aunque la llave esté cargada en GitHub.

### Lo que se cerró hoy, en orden

`LV-142` (el duplicado avisa quién tiene el valor en vez de reventar con 500) ·
`LV-143` (el RUT validado) · `LV-151` (el roster del permiso se busca) · `LV-152`
(la habilitación dice lo que dice la DGAC) · `LV-156`/`LV-157` (aprobar exige el
PDF **y** el número; el alta no puede nacer aprobada) · `LV-155` (la línea del
permiso termina en caducado) · `LV-153` (el permiso trae los datos del plan) ·
`LV-154` (borrador local del formulario) · `LV-146` (el centro de costo se ve y se
filtra) · `LV-147` (el clima se elige) · `LV-148` (reorden del panel; cierra
`LV-31`) · `LV-158` (la prueba interna de conocimientos) · `LV-159` (la Resolución
de la JAC pone la vigencia del seguro; cierra el pendiente de `LV-81b`).

**Segunda tanda, la que cerró el lote** (pusheada, sin desplegar): `LV-144` (el
membrete corporativo JEJ en los PDF, como helper compartido) · `LV-145` (el
informe de catastro de flota y personal, cuatro salidas) · `LV-149` (la ficha del
plan geoespacial y la hoja de campo para SIGO con botones de copiar) · `LV-150`
(Solicitudes SIGO fuera del menú, paso 1) · `LV-119` 🔄 (el comando `check_email`;
el correo sigue sin salir hasta que alguien pegue las credenciales).

El plan del lote, con el contexto de cada decisión, está en
`C:\Users\cmunoz\.claude\plans\d-onedrive-j-e-j-ingenier-a-parallel-map.md`.

### El lote quedó completo

Las cuatro filas que faltaban se cerraron en la segunda tanda, y `LV-119` quedó
en 🔄 con el código entero. El detalle de cada decisión está en su fila del
tablero; acá va sólo lo que la próxima sesión necesita para no repreguntar.

**Lo único que queda de `LV-119`, y no se puede hacer desde una sesión de
agente**: pegar las credenciales del SMTP de JEJ en el entorno del servicio en
`p340` y probarlo. El procedimiento, para pegar en la sesión SSH:

```bash
sudo -e /etc/aerocontrol.env      # EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER,
                                  # EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL
sudo systemctl restart aerocontrol
cd /opt/aerocontrol && set -a && . /etc/aerocontrol.env && set +a
.venv/bin/python manage.py check_email
.venv/bin/python manage.py check_email --to cmunoz@jej.cl
```

Cuatro cosas que conviene saber antes de escribir esas cinco variables:

- **`set -a` no es opcional** (la lección de siempre): `source` sobre un archivo
  `CLAVE=valor` define variables de *shell*, no de entorno, y `manage.py` cae a
  `config.settings.dev` con la base equivocada.
- **`DEFAULT_FROM_EMAIL` suele tener que ser igual a `EMAIL_HOST_USER`.** Un
  buzón que autentica bien puede no tener permiso para retransmitir con otra
  dirección de remitente, y eso **no se ve al abrir la conexión**: sale sólo al
  enviar, que es para lo que existe el `--to`.
- **Si el buzón tiene MFA hace falta una contraseña de aplicación**, no la del
  usuario. El comando lo dice cuando el servidor rechaza las credenciales.
- **Puerto 465 con SSL implícito**: fijar `EMAIL_USE_SSL=True` y **no** tocar
  `EMAIL_USE_TLS`. Django rechaza las dos juntas con un `ValueError` en el
  momento de enviar, o sea de noche y dentro del trabajo programado.

`check_email` sale con código distinto de cero si algo falla y **nunca imprime la
contraseña** (sólo si está y cuántos caracteres tiene, que es lo que delata un
salto de línea pegado de más). Mientras las variables estén vacías, el estado de
hoy es el que informa: la configuración, qué falta y salida 1.

Cuando el correo salga, lo que empieza a llegar son las **nueve notificaciones**
que hoy se imprimen en el journal, incluido el informe ejecutivo de los lunes con
su XLSX. Vale avisarle a Dirección antes de encenderlo.

### Filas nuevas capturadas hoy y sin resolver

- **`LV-74`, `LV-98`, `LV-102`, `LV-78`/`LV-103` (pasos 2 y 3), `LV-11b`** siguen
  como estaban. `LV-119` pasó a 🔄 (ver arriba).
- Nada más quedó capturado sin decidir: los cuatro pedidos que llegaron durante la
  sesión (`LV-151` a `LV-154`) y los cinco del reporte en vivo (`LV-155` a `LV-159`)
  se cerraron el mismo día.
- **`LV-150` deja escrita su condición de reversión**: si en un mes (o sea desde
  el **2026-09-26**) hay al menos una solicitud SIGO creada en producción, el
  retiro del menú se revierte descomentando una línea de `templates/base.html` en
  vez de avanzar al paso 2. Conviene hacer los tres retiros (`LV-78`, `LV-103`,
  `LV-150`) juntos cuando cumplan el mes.

### Dos preguntas para el usuario, chicas y con consecuencia

1. **¿La casilla "Distancia al AMC" de SIGO acepta coma o punto decimal?** La
   ficha del plan la muestra `110,9` (locale español) y el botón de copiar copia
   eso. Los segundos de la coordenada sí se forzaron a punto, porque la lectura
   corrida de al lado usa punto y dos formas del mismo número en la misma
   pantalla es un error esperando. La distancia se dejó **como estaba antes** —el
   botón reproduce exactamente lo que ya se leía en la pantalla, así que no
   introduce un riesgo nuevo—, pero si SIGO exige punto, es una línea.
2. **¿El membrete queda así?** Se envió el PDF de muestra en el chat. Si el logo
   va muy grande o muy chico, o la franja azul molesta, son constantes en
   `apps/core/pdf.py` (`_LOGO_WIDTH`, `_HEADER_TOP`, `_RULE_GAP`).

### Pendientes del usuario, actualizados

Del cierre anterior siguen: las capturas del selector de SIGO de "Bermuda Intl" en
adelante, `SCSA`, cargar `RPA-7213`, corregir `RPA-7126`, y la comuna equivocada de
`JEJ-2026-002`. **Ya no está pendiente** el despliegue (se hizo hoy) ni el cierre
del círculo del seguro (`LV-159`).

Y uno nuevo, chico: si la ficha de una aeronave sigue diciendo "Vencida" después de
esto, es porque **su Resolución Exenta de la JAC no está adjunta**. No es defecto:
sin el verificador la app no se inventa una vigencia. `sync_jac_insurance` sólo
mueve la fecha cuando hay Resolución en ficha.

## Cierre del 2026-08-24, sesión de tarde

`main` = `origin/main`, árbol limpio salvo `.vscode/` (sin sha a propósito: una
línea que nombra su propio commit queda obsoleta con el commit siguiente).
`pwsh scripts/verify.ps1` verde: **1755 tests**, cobertura 96.56%, ruff, bandit y
pip-audit sin hallazgos. De 1637 tests a 1755 en el día.

### Lo que se cerró hoy, en orden

`R10.4` (el KMZ de Trimble deja de leerse como "sin círculo") · `R10.5`
(documentos en plan y solicitud) · `R10.6` (una sola sección de documentos en el
permiso) · `R10.7` (el catálogo de aeródromos se posiciona con el AIP: de 6 a 15)
· `R10.8` (la circunferencia mínima que encierra un área irregular) · `LV-130` (el
expediente lleva a resolver lo que falta) · `LV-131` (fuera el botón que no
separaba) · `LV-132` (una fila por circunferencia) · `LV-133`/`LV-134` (el
Capítulo 1 Rev 17 se lee, y sin duplicar) · `LV-135` (archivar plan y permiso, con
doble verificador y filtros) · `LV-136` (el mapa usa la pantalla, y se amplía) ·
`LV-137` (el permiso recibe el AMC del plan que se vincula) · `LV-138` (folio
`PG-2026-001`) · `LV-139` (modelo y serie en la pestaña Flota) · `LV-140` (rótulos
Lat/Lon) · `LV-141` (comuna, provincia y región desde el pin central).

### Lo que sigue, para retomar

**Necesita al usuario** — nadie más puede:

1. **Desplegar** lo que quedó (ver "Qué está en `p340` y qué no": esta tanda trae
   migraciones y respaldo verificado antes).
2. **Las capturas del resto del selector de SIGO**, de "Bermuda Intl" en adelante.
   Es lo único que mejora el AMC: con 50 nombres, Quintero a 124 km seguirá siendo
   la respuesta correcta para el Choapa aunque las posiciones ya sean exactas.
3. **`SCSA`**: SIGO la llama "Alberto Santos Dumont" (Río de Janeiro) y el
   AIP-Chile "Rungue Dr. C. Barría B.". Sin resolver eso queda sin posición.
4. **Cargar `RPA-7213`** con sus cuatro PDF (datos en la fila `LV-121` y en el
   punto 4 de la lista de arriba), y **corregir `RPA-7126`**: modelo escrito
   "Matrice 4E" contra "MATRICE 4 ENTERPRISE" de sus tres hermanas, y seguro en
   "Faltante o por renovar" teniendo los papeles.
5. **`JEJ-2026-002` tiene la comuna equivocada**: dice "Antofagasta, Antofagasta"
   y sus coordenadas caen en **Calama, provincia El Loa** (`LV-141` lo detecta).
6. De la VM, de antes: `EMAIL_HOST` vacío, los dos timers sin instalar, y el
   respaldo del día tomado y **sin verificar**.

**Se puede hacer sin el usuario**, en orden de valor:

7. **Al cargar la Resolución Exenta de la JAC, cerrar el círculo del seguro**:
   pasar `insurance_status` a *autorizado* y tomar la vigencia del documento. Hoy
   el estado se queda en "presentado" hasta que alguien lo cambie a mano y tipee
   la fecha, teniendo el papel con la fecha adentro. **Pedido del usuario el
   2026-08-24**, textual: *"mantener ahora en alerta pero presentado en SIGO se
   espera la resolución de la JAC, ahí queda resuelto"*.
8. **El centroide como centro cuando el círculo viene sin punto**:
   `propuesta_completo.kmz` de CC 738 trae 54 así (los `CG-0N` individuales sí lo
   traen).
9. **Los pares "Área de trabajo / Objetivo del vuelo" en el plan**, si el usuario
   los quiere ahí: hoy viven en la solicitud (`R9.6`) y el catálogo ya coincide
   exactamente con lo que muestra SIGO. Reparo pendiente de conversar: el mismo
   dato en plan, solicitud y permiso son tres copias que se desincronizan.
10. **Higiene**: 7 ramas dependabot abiertas (Django 6.1 entre ellas), dos
    worktrees viejas en `.claude/worktrees/`, y `.vscode/` sin versionar.

### Dos cosas que conviene saber antes de tocar nada

- **Desde una sesión de agente no hay acceso a `p340`**: `ssh` responde
  `Permission denied (publickey,password)`. Toda escritura en producción la hace
  el usuario; nosotros preparamos el bloque de comandos y verificamos con el gate
  local, que es el único gate real (el CI de GitHub nunca ha estado verde).
- **Correr `uv run ruff format apps` ANTES del gate.** `verify.ps1` pone
  `ruff format --check` **después** de pytest, así que un archivo sin formatear
  cuesta once minutos de suite antes de fallar por espacios. Costó dos gates hoy.

## Estado al cierre del 2026-08-24 (mañana)

`main` = `origin/main` (`3eba41d`), árbol limpio, `pwsh scripts/verify.ps1`
verde: **1637 tests**, ruff, bandit y pip-audit sin hallazgos.

### Lo que pasó hoy, en orden

1. **Se desplegó R9 completo en `p340`.** El 500 que se reportó al importar un
   KMZ **no era el archivo**: era el despliegue a medias — `git pull` sin
   reiniciar. Ver el aviso destacado más abajo; es la trampa que conviene no
   volver a pisar.
2. **`LV-129`** — el panel daba cinco respuestas distintas a la misma pregunta.
3. **Django 6.0.7 → 6.0.8** y `pip` 26.2 (`pip-audit` en verde).
4. **`R10.1`–`R10.3`** — la corrección de fondo del flujo geoespacial.

### `R10`: qué cambió y por qué importa

El usuario corrigió una premisa equivocada de R9: *separar* era la **única**
puerta para que un KMZ entregara centro, radio, aeródromo más cercano y
distancia, lo que obligaba al caso normal —**un** KMZ con **una**
circunferencia— a pasar por una acción diseñada para el excepcional (el archivo
de MLP, con 47).

- **La ficha del plan trae "Datos para SIGO"**, calculado al vuelo. Separar sólo
  aparece con más de una circunferencia.
- **Un plan ya subido se vincula a su permiso** y le rellena la ubicación. La
  aritmética vive en `FlightPermission.fill_location_gaps()`, junto al `clean()`
  que la restringe.
- Sin migraciones: todo se apoya en campos que ya existían desde OPS-7.

### Lo siguiente, por valor

1. ~~**Coordenadas de aeródromos**~~ — **hecho el 2026-08-24 (`R10.7`)**: de
   **6 de 50** a **15 de 50**, con las posiciones del AIP-Chile cruzadas por
   designador OACI. Lo que **no** se hizo, por decisión del usuario reafirmada
   ese día: agregar aeródromos que el AIP publica y el selector de SIGO no
   ofrece. Corolario para leer cualquier distancia: **el AMC es el más cercano
   entre los que SIGO ofrece**, no el del país — para CC 738 eso da Quintero a
   124 km teniendo Pichidangui a 79. **Lo que queda**: capturar el resto del
   selector de SIGO (las imágenes del 2026-08-20 llegaban de la "A" a "Bermuda
   Intl") y volver a correr `import_aip_aerodromes`. Y `SCSA` sigue sin
   posición: SIGO la llama "Alberto Santos Dumont" (Río de Janeiro) y el AIP,
   "Rungue Dr. C. Barría B." — una de las dos fuentes está equivocada.
2. ~~**Documentos en plan y solicitud**~~ — **hecho el 2026-08-24 (`R10.5`)**,
   con la sección compartida. Queda una deuda relacionada: la ficha del permiso
   sigue con su propia copia anterior a `attached_documents_context`, así que hoy
   hay dos implementaciones de la misma sección.
3. ~~**Botón "Separar un plan"**~~ — **hecho el 2026-08-24 (`LV-131`)**: era
   navegación disfrazada de acción. La pantalla ahora dice para qué es, y el
   estado vacío explica de dónde nacen las solicitudes.
4. **Crear `RPA-7213` en CC 743 = "Candelaria"**, con sus cuatro PDF. `RPA-7126`
   ya está cargada. Los datos salen del Rev 17 del manual y de los papeles:
   `DJI / MATRICE 4 ENTERPRISE`, serie `1581F7FVC266P00DEDA2`, 1.420 kg, seguro
   JAC vigente hasta **18-08-2027** (`RES. EX. 1.183`), estado del seguro
   *Autorizado*. Los cuatro tipos de documento y sus fechas están en la fila
   `LV-121`. **Ojo con `RPA-7126`**: quedó con el modelo escrito "Matrice 4E" (del
   certificado DGAC) mientras sus tres hermanas dicen "MATRICE 4 ENTERPRISE" (del
   manual), y su seguro sigue en "Faltante o por renovar" aunque los papeles
   existen. `import_aip_aerodromes` no arregla eso y `chapter1_docx_import
   --skip-existing` tampoco: saltar no actualiza, lo reporta como discrepancia.
   **Nadie con acceso a `p340` desde una sesión de agente**: `ssh` desde esta
   máquina responde `Permission denied (publickey)`, así que toda escritura en
   producción la hace el usuario.
5. ~~**La circunferencia que encierra un polígono**~~ — **hecha el 2026-08-24
   (`R10.8`)**. Lo que queda alrededor: **(a)** la solicitud sigue naciendo con
   el centro y radio *dibujados*, no con los de la propuesta — sustituirlos es
   decisión del usuario y no se hizo en silencio; si la quiere automática, es una
   fila nueva. **(b)** `propuesta_completo.kmz` de CC 738 trae **54 círculos sin
   punto centro** (los individuales `CG-0N` sí lo traen), así que ofrecer el
   centroide como centro cuando falta el punto sigue pendiente.

### Los siete KMZ de CC 738, y el bug que destaparon

El usuario aportó `CG-01`…`CG-07_circunferencia_grande.kmz`
(`D:\OneDrive - J.E.J. Ingeniería S.A\DGAC\Permisos\CC 738\08-2026\KMZ\KMZ_circunferencias_grandes\`)
para sacar los permisos con ellos. **Los exporta Trimble Business Center, no
Google Earth**, y ahí el círculo es un `LineString` cerrado en vez de un
`Polygon`: los siete daban "sin círculo" y sin radio (`R10.4`, corregido). Uno
por permiso, una circunferencia cada uno, radios de **252 m a 2396 m**, así que
**no hay que separar ninguno** — con `R10.1` la ficha del plan ya muestra sus
datos para SIGO. Conviene probar contra estos archivos y no sólo contra el KMZ
de MLP (47 círculos, `Polygon`): las dos formas existen en producción.

### Qué está en `p340` y qué no

**Desplegado y verificado en pantalla hasta `b3fb8c0`** (2026-08-24, tarde). La
evidencia son las capturas del usuario: los filtros del listado de planes
(`LV-135`), el botón "Ampliar" en la tarjeta del mapa (`LV-136`) y la fila del
círculo envolvente en `CC 716` (`R10.8`, `LV-132`). O sea `R10.4`…`R10.8`,
`LV-129`…`LV-136` y `R10.6` ya corren allá, con `import_aip_aerodromes` ejecutado
(el AMC se calcula sobre 15 posiciones, no 6).

**Sin desplegar** al cierre: `814301f`, `<folio>` y `<coords>` — o sea `LV-137`,
`LV-139`, `LV-138` y `LV-140`.

**Y esta tanda SÍ trae migraciones**, a diferencia de las anteriores:

- `operations/0021` — el `amc` y su distancia en el permiso (`LV-137`).
- `geo/0005` — el folio `PG-2026-001` del plan, **con relleno de datos**: asigna
  su número a los planes que ya existen, en orden de creación por año.

Así que el bloque de despliegue va **con `migrate`**. El paso de datos
(`import_aip_aerodromes`) ya corrió y es idempotente, pero repetirlo no cuesta
nada y cubre el caso de que alguien lo haya salteado:

```bash
cd /opt/aerocontrol && git pull && set -a; source <(sudo cat /etc/aerocontrol.env); set +a && uv sync && uv run python manage.py migrate --no-input && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol && uv run python manage.py import_aip_aerodromes
```

**Antes de migrar, respaldar y verificar el respaldo** (`manage.py backup`,
`verify_backup <ruta>`): `geo/0005` escribe en todas las filas de `geo_geoplan`.

### Lo que sigue faltando en la VM, de antes

`EMAIL_HOST` sigue vacío (`LV-119`: ningún correo ha salido nunca), los dos
timers (`check_scheduled_jobs`, `verify_backup`) siguen sin instalar, y el
respaldo del 2026-08-24 se tomó pero **no se verificó**
(`aero_ops_20260824_093724`).

## Estado al cierre del 2026-08-17

`main` = `origin/main`, árbol limpio, `pwsh scripts/verify.ps1` verde: **1440
tests, cobertura 95.89%**. Las ramas fusionadas se podaron (quedan `main` y dos
que **no** están fusionadas: `claude/amazing-bouman-1b3d09`, trabajo del Kanban
que se dio de baja, y `claude/brave-benz-8580f9`, retenida por un *worktree*).

### Desplegado y funcionando en `p340`

Todo lo de los días 13 al 17 está en producción, incluidas las migraciones
`compliance/0019`, `0020` y `0021`. El antivirus quedó cerrado (`LV-97`):
`DOCUMENTS_ANTIVIRUS_COMMAND="clamdscan --fdpass"`, con el demonio arrancado y
verificado dando veredicto. **Las comillas no son opcionales** — `systemd` lee la
línea entera, pero el `source` del despliegue es bash y sin ellas parte el valor.

### Lo que falta hacer en la VM — y sin esto, código desplegado que no sirve

1. **Los dos timers nuevos** (serían **13**), con el bloque `mkjob` de
   `docs/scheduled-operations.md`: `check_scheduled_jobs` (09:00) y
   `verify_backup` (22:30). **Hasta que existan, `LV-114` y `LV-115` están
   desplegados y no avisan a nadie** — exactamente el modo de fallo que
   `AGENTS.md` documenta.
2. **La hora del respaldo.** El sistema operativo está en UTC y Django sella los
   nombres en hora de Chile, así que el respaldo "de las 22:00" corre a las
   **18:00 hora local**, en plena jornada. Desde `LV-116` eso ya no arriesga la
   integridad de la copia (se toma con la API de SQLite), así que es orden y no
   urgencia: `mkjob backup "backup" "*-*-* 02:00:00"`.
3. ~~**Dos alertas duplicadas** que quedaron escritas antes de `LV-111`.~~
   **Resueltas a mano por el usuario** (verificado en la captura del
   2026-08-20). Se conservan como historial, por decisión suya: son evidencia
   ISO 10.2. Desde `LV-118` la bandeja abre en "Sin resolver", así que ya no
   estorban, y `generate_alerts` avisa si vuelve a quedar un residuo así.
4. **Los tipos de documento creados a mano** quedaron en "Otro" (`LV-98`).
5. **`EMAIL_HOST` (P1, `LV-119`, 2026-08-20).** Está **vacío**, así que el
   backend es el de consola y **ningún correo ha salido nunca de la VM**: se
   imprimen en el journal (el MIME crudo y los 79 guiones de Django están en la
   salida de `aerocontrol-executive.service`). Deja sin canal las siete
   notificaciones, incluidas las de `LV-114` y `LV-115`, que existen justamente
   para avisar sin que nadie entre a mirar. Es lo primero de esta lista por
   impacto: hasta que exista, cada timer nuevo es código que no avisa a nadie.

### Lo que sólo puede hacer el usuario, por impacto

| Qué | Por qué importa |
|---|---|
| **8 vigencias sin dato** (`LV-74`) | Único con impacto de cumplimiento **hoy**: un nulo no genera alerta, así que son invisibles |
| ~~3~~ **1 corrección de ficha** (`RPA-3696`) | Destraba `LV-102`. `RPA-5532` lo corrigió el usuario el 2026-08-20; **`RPA-7126` ya no necesita corrección** — el certificado del Registro Nacional de RPA de la DGAC confirma la `C` que la app tiene, y `LV-93` quedó **anulada** (aplicarla habría metido el error) |
| ~~3~~ **2 carpetas en `Z:`** (`R4.1a`) | Destraban `R4.4`: correr el importador con `--apply`. La tercera era de `LV-93` y **no hay que renombrarla**: `CC738-...DM5QC-M4E` estaba bien |
| **El PR de AeroLink** | Destraba `X.4`, que es la etapa 2.0 completa |

Los detalles operativos, con comandos, en
[docs/dev/pendientes-usuario-2026-08-13.md](docs/dev/pendientes-usuario-2026-08-13.md).

### Qué se hizo el 14 y el 17

Dieciocho filas cerradas. El detalle de cada una está en `MASTER_PLAN.md`; acá
sólo lo que cambia cómo trabajar mañana:

- **Documentos**: se arregló que no se pudiera subir uno (`LV-94`), el catálogo
  se agrupa por categoría (`LV-95`), los listados agrupan y filtran por ella
  (`LV-104`) y "Ver" abre el archivo sobre la ficha (`LV-92`).
- **Alertas**: lo resuelto ya no reaparece (`LV-111`), no persiguen aeronaves
  dadas de baja (`LV-113`), la bandeja tiene orden (`LV-112`) y el motivo tiene
  columna propia (`LV-110`). Ya no cuestan una consulta por fila (`LV-106`).
- **Permisos**: `LV-101` cerró una puerta trasera real —se llegaba a "Aprobado"
  sin el PDF firmado y sin registrar quién— y la ficha abre con el **expediente
  operativo** (`LV-107`).
- **Infraestructura**: monitoreo de trabajos (`LV-114`), verificación diaria del
  respaldo (`LV-115`) y respaldo consistente con la API de SQLite (`LV-116`).
- **Tres defectos que nadie había reportado**, encontrados verificando en el
  navegador: ningún error de modal se veía nunca (`LV-108`), los dos gráficos del
  panel llevaban semanas vacíos (`LV-109`), y el calendario salió del menú por
  decisión del usuario (`LV-103` paso 1).

Dos análisis nuevos, los dos pedidos por el usuario:
[competencia y ruta de escala](docs/dev/analisis-competencia-2026-08-14.md) —la
única brecha real contra AirData/DroneLogbook es la ingesta automática de vuelos
(`X.4`), y no conviene comprar SaaS— y
[la bandeja de alertas](docs/dev/analisis-alertas-2026-08-14.md), donde el ciclo
de vida ya está por encima del promedio del sector y lo que faltaba era higiene.

### Lo siguiente en mi cola

**Nada que pueda avanzar sin una decisión del usuario.** Lo que queda:

- **`LV-81b`, la mitad grande** (certificado de póliza con endosos): toca
  `insurance_expiry`, la columna que alimenta alertas, calendario, panel, reporte
  y `load_dgac_vigencias` **a la vez**, y el usuario pidió ir de a poco.
- **Estado terminal del seguro por fecha**: aplicarle el criterio que `LV-83` ya
  tomó para los permisos. Media hora, en cuanto se decida.
- `LV-78` paso 3b y `LV-103` paso 3 esperan su condición de disparo; `T4.1` tiene
  hecha la mitad del cliente autenticado y falta la de datos, que se hará cuando
  haya un segundo lector real que la pida.


## Listo para desplegar: todo lo del **2026-08-20/21** — 5 migraciones, 4 seeds

> **Ensayado el 2026-08-21 y verde de punta a punta.** No es "debería
> funcionar": se probó dos veces sobre bases desechables — una instalación
> **desde cero** (todas las migraciones, roles y seeds), y el camino real, que
> es una base **retrocedida al estado exacto de `p340`** (`compliance/0021`,
> `registry/0034`, `operations/0018`), cargada con datos con la forma de los de
> producción y migrada hacia adelante. Resultado: las 5 migraciones aplican
> limpio, `compliance/0023` corrigió la fila preexistente (`requires_expiry`
> pasó de `True` a `False`), el serial de `RPA-7126` quedó intacto y
> `seed_document_types` creó 18 dejando en paz la que ya existía. El gate
> completo (`verify.ps1`) pasa: **1598 tests, ruff, bandit y pip-audit**.

Dos sesiones trabajaron el mismo día sobre el mismo árbol, así que **esta es la
lista completa**, no la de una de las dos. Todo está en `main` y verde en local;
nada de esto está en `p340` todavía, salvo `LV-117`, que ya se sembró.

| # | Qué | Se ve en |
| --- | --- | --- |
| `LV-117` | Tipo "Resolución Exenta JAC" | Carga de documentos · **ya sembrado en `p340`** |
| `LV-118` | La bandeja abre en "Sin resolver", ordena por urgencia y la fecha deja de ser la de hoy | Alertas |
| `LV-119` | Un trabajo deja de decir "Sent" cuando sólo imprimió | Salida de los timers y resumen del trabajo |
| `LV-120` | Lo ya vencido vuelve a aparecer, con tarjeta propia | Panel |
| `LV-122` | …y lo que la bandeja ya cerró deja de aparecer | Panel |
| `LV-129` | Los números del panel dejan de contradecirse; *Alertas pendientes* respeta el filtro por centro de costo | Panel |
| `R10.1` | **"Datos para SIGO" en la ficha del plan**: punto centro, radio, AMC y distancia — sin separar nada. Separar sólo aparece con más de una circunferencia | Planificación geoespacial |
| `R10.2` | **"Vincular plan ya subido"** en la ficha del permiso, y el plan rellena su ubicación | Permisos |
| `R10.3` | Iconos del menú que ya no se repiten | Barra lateral |
| `LV-121` | El registro DGAC ya no exige vencimiento · tipo nuevo "Solicitud a la JAC" | Carga de documentos |
| `LV-125` | La entidad de una alerta enlaza a su ficha | Alertas |
| `LV-126` | El número de serie, en la lista | Aeronaves |
| `LV-127` | 10 orígenes de no conformidad y categoría de causa raíz | No conformidades |
| `LV-128` | Entregables sale del menú | Barra lateral |
| **`R9.1`–`R9.5`** | **Solicitud de vuelo SIGO**: separar un KMZ multi-círculo en una solicitud por circunferencia, hoja copiable con las seis casillas del punto centro, AMC calculado, KMZ individual descargable, flujo con barra de progreso y vínculo al permiso | Menú **Solicitudes SIGO** (nuevo, bajo Vuelo) |

**Las dos migraciones son benignas y ninguna necesita el chequeo previo de datos**
que sí piden las de `unique`/`NOT NULL` (Parte D del runbook):

- `compliance.0022` (`LV-127`): añade `root_cause_category` con defecto
  `undetermined` y amplía los `choices` de `source` sin tocar los cuatro valores
  existentes. No borra, no renombra, no impone restricciones.
- `compliance.0023` (`LV-121`): pone `requires_expiry=False` en **una** fila del
  catálogo (`aircraft-registration`). No borra vencimientos ya cargados.
- `registry.0035` y `operations.0019` (**R9**): crean tablas nuevas
  (`Aerodrome`, `FlightRequest` y sus tres acompañantes). No tocan ninguna fila
  existente, así que no pueden fallar sobre datos reales.
- `operations.0020` (**R9**): sólo un `help_text`. No toca la base.

**`R10` no trae migraciones**: los datos que muestra la ficha del plan se
calculan al vuelo desde la versión vigente del KMZ, y el vínculo plan↔permiso
usa un campo (`GeoPlan.flight_permission`) y una bitácora
(`GeoPlanPermissionLink`) que existen desde OPS-7. Lo único que hacía falta era
la puerta.

**Esta tanda sube Django de 6.0.7 a 6.0.8** (`PYSEC-2026-3717`, un aviso de
GeoDjango que esta app no usa; se aplica igual porque es un parche de la misma
minor). El `uv sync` del bloque de despliegue lo instala solo — no hay paso
extra, pero conviene saber que el reinicio de `aerocontrol` levanta con una
versión nueva del framework.

El respaldo previo sigue siendo obligatorio igual.

> ### ⚠ Un `git pull` a medias deja el sitio caído, y en segundos
>
> **Ocurrió el 2026-08-24.** Se hizo `git pull` y ahí se paró: sin `migrate`,
> sin `collectstatic`, **sin reiniciar**. El sitio empezó a devolver 500
> (`NoReverseMatch: Reverse for 'geo-plan-split' not found`) y el síntoma que se
> vio fue *"falla al importar un KMZ"*, que no tenía nada que ver.
>
> La causa es una asimetría que conviene tener presente: esta app usa los
> cargadores de plantillas **sin caché** (`APP_DIRS`, sin `cached.Loader`), así
> que **las plantillas se leen del disco en cada petición** — quedan activas
> apenas termina el `pull` — mientras que el **código Python, incluido el mapa
> de URLs, se carga al arrancar el proceso**. Entre el `pull` y el `restart` la
> app corre con plantillas nuevas sobre código viejo, y cualquier `{% url %}`
> que apunte a una ruta nueva revienta.
>
> **Por eso los pasos de abajo son un bloque, no una lista de la que se elige.**
> Si hay que interrumpir a la mitad, lo seguro es volver atrás
> (`git checkout <commit-anterior>`), no dejarlo a medias.

```bash
ssh levdigital01@100.121.16.118
```

```bash
cd /opt/aerocontrol && git pull
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo "settings=$DJANGO_SETTINGS_MODULE  db=$DB_PATH"   # debe decir prod
```

```bash
uv run python manage.py backup
```

```bash
uv run python manage.py verify_backup <la-ruta-que-imprimio-el-anterior>
```

```bash
uv sync && uv run python manage.py migrate --no-input
```

```bash
uv run python manage.py bootstrap_roles
uv run python manage.py seed_document_types
uv run python manage.py seed_aerodromes
uv run python manage.py seed_sigo_catalogs
```

```bash
uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```

**Los cuatro pasos del bloque de siembra, y por qué ninguno sobra:**

- **`bootstrap_roles` es obligatorio esta vez.** R9 trae seis modelos nuevos y
  `ROLE_PERMISSIONS` es una **lista explícita**: sin correrlo, *Solicitudes
  SIGO* da **403 a todo el mundo salvo al administrador**, y desde afuera eso se
  lee como "el despliegue falló" — el modo de fallo que este mismo archivo
  advierte desde el 2026-08-12. Hay tests que lo fijan
  (`test_r9_roles_reach_the_screens.py`), así que la próxima vez la suite lo
  caza antes que la VM.
- **`seed_document_types`** trae `jac-insurance-request` (`LV-121`). Debe decir
  `Ensured 19 document types (1 created)` — **19, no 20**: la cifra estaba mal
  escrita acá y la corrigió el despliegue real del 2026-08-24. El del
  `aircraft-registration`
  **no** lo hace el seed —es idempotente por `code`—, lo hace `compliance/0023`.
- **`seed_aerodromes`** debe decir **`6 of 50 have coordinates`**. Sin él el AMC
  no se calcula y la casilla de SIGO queda vacía.
- **`seed_sigo_catalogs`** debe decir `5 work areas` y `8 objectives`. Sin él los
  dos desplegables de la solicitud salen vacíos.

`collectstatic` tampoco es opcional aunque no haya JS nuevo: se recompiló el
`.mo` y hay plantillas cambiadas en la mitad de las filas.

**Qué mirar después**, en este orden:

1. **Panel**: la tarjeta **Vencidos** con `RPA-5534` y `RPA-2198` en rojo arriba
   de la lista (`LV-120`), y que la credencial de `Carlos Peñailillo` —resuelta
   con "Fuera de CC con operación RPA"— **ya no esté** (`LV-122`). Las dos
   mitades del mismo reporte.
2. **Alertas**: abre en "Sin resolver" (4 filas, no 8), lo más atrasado primero,
   y clicar `RPA-5534` abre su aeronave.
3. **Aeronaves**: la columna `S/N`.
4. **No conformidades**: el formulario con los diez orígenes y la categoría de
   causa. Y que **Entregables** ya no esté en el menú.
5. **Carga de documentos**: el selector con los dos tipos JAC bajo *Documentos de
   la aeronave*, y que el registro DGAC se deje subir **sin** fecha de
   vencimiento.
6. **Solicitudes SIGO** (R9), que es lo nuevo de verdad: la entrada
   **Solicitudes SIGO** en el menú, bajo Vuelo. Después subir el KMZ de MLP
   como plan geoespacial, abrir *Separar en solicitudes de vuelo* y comprobar
   que da **47 filas con 6 avisos** — los tres pares de puntos con coordenadas
   repetidas. Crear una y mirar su hoja: el punto centro en seis casillas y el
   AMC propuesto (`SCER`, ~120 km para MLP).

### Si algo sale mal

Ninguna de las cinco migraciones borra ni reescribe datos, así que **volver
atrás es seguro** y se ensayó: las cinco revierten limpio.

```bash
uv run python manage.py migrate operations 0018 && uv run python manage.py migrate registry 0034 && uv run python manage.py migrate compliance 0021
```

Después `git checkout <commit-anterior> && uv sync && sudo systemctl restart
aerocontrol`. El respaldo previo sigue siendo la red de verdad: revertir
migraciones recupera el esquema, no un dato que alguien haya editado entremedio.

Ninguna de las ocho toca los timers. `LV-119` **no arregla** el correo: hace que
se note que no sale (pendiente 5 de la lista de arriba).

## Pendientes inmediatos del 2026-08-13 (histórico)

> Los que **no dependen del código** (vigencias, CSP, antivirus, `Z:`, el PR de
> AeroLink) están reducidos a un comando o un clic cada uno en
> [docs/dev/pendientes-usuario-2026-08-13.md](docs/dev/pendientes-usuario-2026-08-13.md),
> con lo verificable ya verificado — incluidos los dos nombres de carpeta de `Z:`
> comprobados contra el disco real.

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

**6. Lote nuevo del 2026-08-13: `LV-81` a `LV-88` hechos. Queda `LV-89`.**
El usuario pidió "tomarlo de a poco" e investigar antes de programar, y marcó
`LV-81` (el seguro) como lo clave: **está hecho** — cuatro estados, escalera y
trazabilidad, más el bloqueo que impide marcar "autorizado" sin fecha de
vigencia. Quedó `LV-81b` para el certificado/endoso como registro, que es lo que
se dejó fuera a propósito.

`LV-82` también está hecho: la escalera de mantención dibuja **el camino que el
registro tomó** (casa o taller), decidido por su propio historial, y de paso se
corrigió que el historial mostraba códigos crudos en inglés.

`LV-83` está hecho, con la decisión del usuario: **estado nuevo "Caducado"**, no
auto-completar (completar exige el PDF firmado de la DGAC, y un permiso puede
caducar sin haber volado). **Agrega un trabajo programado nuevo**
(`expire_permissions`, 05:30, antes de `generate_alerts`) que hay que instalar en
`p340` con el bloque `mkjob` — serían **11 timers**. El bloque de
`docs/scheduled-operations.md` ya lo incluye.

El bloque de documentos (`LV-84`/`LV-85`/`LV-86`) también está hecho: listado con
acciones, **preview dentro de la página** y carga de varios archivos a la vez.
Dos cosas de ese bloque que conviene no perder: la excepción de *framing* es
**por respuesta** (sólo el archivo se deja enmarcar; la app sigue en `DENY`), y
**`DOCUMENTS_ANTIVIRUS_COMMAND` sigue vacío** — la carga masiva multiplica
archivos entrando al sistema, así que conviene configurarlo antes de usarla en
producción.

`LV-87` y `LV-88` también están hechos: columna propia para la credencial
adjunta, y la lista de movimientos acotada a 30 días por defecto con selector
visible, trayecto en una sola columna y enlace a la ficha del recurso.

**`LV-78` está en el Paso 2 (congelado), con las armas descargadas.** El tablero
se quedó **sin superficies** —panel, calendario, buscador, centro de
administración, índice de la API— sin borrar una fila. Lo que destrabó todo y no
estaba escrito en ninguna parte: el **índice de la API y el endpoint de token
vivían dentro de `apps.workboard`**, o sea que la integración con AeroLink
colgaba del módulo a retirar; ahora están en `apps.core.api`. Además se quitaron
las dos formas de reencenderlo sin querer: los campos de Kanban salieron del
formulario de reglas de alerta, e **`init_dgac_board` salió del runbook**.

**Queda el Paso 3b: borrar la app y los campos de `compliance`.** La
recomendación es que **viaje de acompañante** de otra migración que ya toque esas
tablas, no como despliegue propio: borrar compra orden, no capacidad. Antes de
borrar, exportar el tablero (`TaskReportCsvView`/`TaskReportXlsxView`). Y si en
producción alguna regla todavía tiene `create_kanban_task` encendido,
`generate_alerts` lo dice en su salida diaria.

**`LV-89` está hecho**, con las tres decisiones del usuario tomadas el mismo día:
encabezado con un solo botón, los dos gráficos flojos reemplazados por la tira
de **flota disponible / seguros al día / credenciales al día**, y la **ventana de
luz diurna** en la tarjeta de clima (sin llamada nueva; la póliza cubre jornada
diurna). **Con esto el lote completo `LV-78`…`LV-91` está cerrado.**

**Los dos hallazgos de la revisión del 2026-08-13 quedaron resueltos el mismo
día**, y uno resultó peor de lo capturado: `LV-90` (los estados terminales ahora
los declara cada modelo) destapó que la lista literal **ya había mordido dos
veces** — `retired` no estaba nunca, así que una regla sobre el estado de una
aeronave alertaba sobre aeronaves dadas de baja para siempre. `LV-91`
(`MaintenanceHistory` con dos fechas de creación) también está cerrado.

**`LV-80` cerrado, con la causa corregida**: la fila culpaba a la falta de
traducción, pero la mayoría de esos modelos **sí** tenían `verbose_name`
traducido — lo que rompía era el `.title()`, que evalúa el lazy a inglés y hace
que el `_()` de afuera busque una cadena que no está en el catálogo.

### Estado de la Sesión B (avanzada el 2026-08-12)

| Ítem | Estado |
|---|---|
| Verificación de eficacia (R7.6a) | ✅ Hecho — 30 días, decidido por el usuario |
| Revisión meteorológica como evidencia (R8.2) | ✅ Hecho |
| Los **5** KPI operacionales (R7.7a + R7.7b) | ✅ Hecho — completos. **Sólo la meta de flota (90%) está acordada**; los otros 4 muestran su valor sin marcar incumplimiento. ✅ **Confirmado el 2026-09-02**: el usuario no puede fijar todavía las 4 metas restantes, así que **se quedan sin meta a propósito y no es deuda**. La conducta actual ya es la correcta —se muestra el valor y no se marca incumplimiento— justo porque una línea inventada convertiría el KPI en ruido. **Lo que se hace cuando lleguen**: son constantes documentadas en `apps/compliance/kpis.py`; `KpiTarget` sigue sin crearse hasta que haya una meta con dueño distinto al del resto (una tabla de configuración de una sola fila es una tabla que nadie mantiene) |
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

## ~~Sin desplegar~~: `R8.4` y el lote `LV-80` a `LV-91` — **desplegado el 2026-08-13**

> Se conserva por lo que documenta —**qué hizo cada migración a los datos**—, que
> es lo que hace falta si alguna vez hay que explicar por qué una fila cambió. El
> encabezado decía "sin desplegar" y ya no era cierto.

**Siete migraciones, ninguna riesgosa, pero dos tocan datos:**

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
- `compliance/0018`, `operations/0018` (`LV-80`) y `maintenance/0009` (`LV-91`):
  sólo metadatos y una columna duplicada de menos. Ninguna toca datos.
- `operations/0017` (`LV-83`): sólo amplía las opciones de estado del permiso.
  No cambia ninguna fila — el cierre lo hace el trabajo programado, no la
  migración. **Conviene correr `expire_permissions --dry-run` antes** de
  habilitar el timer: dice cuántos permisos reales se van a cerrar en la primera
  corrida, y en producción es probable que sean varios de golpe.

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
- Tomar un respaldo (`manage.py backup`) y **verificarlo** antes de migrar.
  **`verify_backup` sin argumentos verifica el último**, y es lo que conviene
  pegar: el 2026-08-28 el paso se saltó porque el bloque llevaba un marcador
  literal (`<la-ruta-que-imprimio>`) que bash rechazó, y se migró sin haber
  verificado nada. Un procedimiento que exige copiar y pegar una ruta a mano es
  un procedimiento que alguien va a saltarse.
  ```bash
  uv run python manage.py backup
  uv run python manage.py verify_backup
  ```

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
