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
  **`p340` sigue en `22f379f`**: ahora le faltan **`LV-184` a `LV-194`**.
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
- **El cruce del Capítulo 1 Rev 17** — ver abajo, que tiene su propia sección.

### El cruce del manual: listo para correr en la VM

El comando ya existía (`chapter1_docx_import`, con `LV-133` adaptado a la Rev 17)
y **`LV-190` era lo que faltaba para poder confiar en él**. Verificado sobre
`1 Capítulo 1 202608_R17_reparado.docx`: **17 aeronaves** (las 16 de producción
más `RPA-7213`) y **48 fichas permanentes**, los 48 RUT válidos con su dígito
verificador, 48 números de empleado distintos, ningún campo vacío, y la sección
1.5 cerrando en `EVENTUALES (NO APLICA)` sin nada después — o sea que 48 es la
dotación real y no un parser desbordado. Producción tiene 42, así que la corrida
crea alrededor de seis.

**El cruce contra `p340` no se puede hacer desde una sesión de agente** (`ssh`
responde `Permission denied (publickey)`, y la base local está vacía), así que va
en la VM, y **el informe primero**:

```
uv run python manage.py chapter1_docx_import --source "<ruta al docx>" --export-dir /tmp/cap1
```

Leer `already_on_file`, `CONFLICT` y `operators_ready` antes de aplicar. **Un
`CONFLICT` no se fuerza**: significa que el manual y el padrón no coinciden sobre
una persona, y la fila dice qué ficha tiene ese RUT. Sólo cuando no haya
conflictos:

```
uv run python manage.py chapter1_docx_import --source "<ruta al docx>" --apply --skip-existing
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
- **Puerto 465 con SSL implícito**: poné `EMAIL_USE_SSL=True` y **no** toques
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
