# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto usa versionado `alpha`/`beta`/semántico informal mientras
está en fase de estabilización (ver [MASTER_PLAN.md](MASTER_PLAN.md)).

## [Unreleased]

### Added

- **Las tablas se ordenan por columna, se acomodan y se guardan como vistas
  (`UX-07`, `UX-09`, `UX-12`).** Las 16 listas de la aplicación pasan ahora por
  un mismo componente. Con eso: **ordenar apretando el encabezado** —que no
  existía en ninguna—, **esconder las columnas que uno no usa**, y **guardar un
  filtro con nombre** que aparece como pestaña sobre la tabla ("Seguros
  vencidos", "Credenciales a 60 días"), propia o compartida con todos. Cada
  persona tiene sus columnas y sus vistas; compartir una vista es ofrecerla, no
  cederla: la borra quien la creó. De paso, siete listas que se escribían la
  tabla a mano ganan la **selección múltiple** que ya tenían las demás — sus
  filas estaban preparadas y les faltaba sólo la barra. **El orden se ofrece
  únicamente donde corresponde a lo que la celda muestra**: no se puede ordenar
  por "Entidad" en alertas, porque ahí el orden sería por identificador interno,
  o sea azaroso con aspecto de orden.
- **El número del permiso se toma de la autorización de la DGAC (`LV-231`).**
  Pedido del usuario: es siempre el mismo PDF y trae el número escrito, así que
  transcribirlo a mano era abrirle la puerta a un error en un dato que va a la
  autoridad. Ahora la ficha lo **propone**, rotulado con su procedencia, y se
  escribe sólo al confirmarlo — nunca solo, porque leer un PDF es heurística y un
  número equivocado escrito por la máquina nadie lo revisa. Si no se puede leer,
  o si el PDF trae dos números distintos, no propone nada y la casilla se teclea
  como siempre.
- **La región y la comuna de un permiso dicen de dónde salieron (`LV-220`).**
  Cuando se deducen de las coordenadas del plan, la ficha lo advierte con el
  mismo aviso de la BCN que ya usa la hoja SIGO; una escrita del papel de la DGAC
  no lleva aviso. Antes eran indistinguibles, y la capa administrativa está
  simplificada a ~111 m: cerca de un límite devuelve la comuna vecina. Corregir a
  mano una región deducida **le quita el aviso**, porque después de esa
  corrección ya no es deducida. Los permisos cargados antes de esto quedan sin
  marca —"no se sabe"— y se ven como siempre: inventarles una procedencia sería
  el mismo defecto al revés.

- **El informe mensual RPA se ve dentro de la aplicación (`R3`).** Las cinco
  hojas A4 del documento que se emite a la DGAC —portada, resumen ejecutivo,
  permisos, cobertura por Centro de Costo y plan de normalización— salen de las
  plantillas del diseño con el que se emitió el de agosto, y no de una
  reinterpretación. La pantalla dibuja el **payload congelado** del período
  cuando hay un `ReportRun`, y una vista previa en vivo cuando todavía no lo
  hay; el aviso de arriba dice cuál de los dos se está mirando, porque en el
  papel los dos son idénticos y un borrador firmado como emitido es el peor
  resultado posible. **Lo que no tiene dato sale en ámbar punteado y nunca como
  cero**, que es la regla que manda sobre todo el informe: un cero afirma ("hay
  cero") y la ausencia no afirma nada. Entra al menú el mismo día que gana
  pantalla, y exige `reporting.view_reportrun` — nombra cada faena y si está
  habilitada para volar.
- **Las listas dicen cuántos registros hay, y se puede exportar lo marcado.**
  La paginación desaparecía con una sola página, así que una lista de ocho filas
  no decía si eran ocho de ocho o **ocho de doscientas filtradas** — y es la
  lista corta la que más invita a creer que se está viendo todo. Ahora cada lista
  paginada muestra "mostrando N–M de T". Y se puede **marcar filas por casilla y
  exportar sólo esas**: la selección es explícita, nunca inferida por fecha ni
  por regla, y la barra aparece sólo cuando hay algo marcado.
- **La fila se apila como tarjeta en el teléfono.** La lista de aeronaves medía
  **900 px de tabla dentro de un contenedor de 356** en una pantalla de 390:
  leer una fila en faena obligaba a arrastrar de lado, con guantes, y volver a
  empezar en la siguiente. Ahora cada fila se apila con el nombre de su columna
  delante de cada dato, y no hay desplazamiento horizontal. En escritorio no
  cambia nada.
- **Las filas se pueden ver compactas.** Un botón junto al del tema alterna
  entre cómoda y compacta, y recuerda la elección de cada persona. Sólo cambia
  el espacio: bajar además el cuerpo de letra habría hecho que "compacta"
  significara también "más difícil de leer".
- **Un solo tamaño de título en toda la aplicación.** Había ocho formas de
  escribir el encabezado de página repartidas en 59 pantallas, así que el título
  cambiaba de tamaño al navegar y hacía dudar de si se había cambiado de
  sección. Los 28 iconos del menú pasan además a un solo archivo, referenciados
  por nombre.
- **El informe cuenta bien los registros que ya terminaron (`LV-189`).** Un
  documento colgado de una aeronave retirada, o de un permiso caducado, seguía
  contando en el cumplimiento de su faena: se excluían los archivados, no los
  terminados, y son cosas distintas — una aeronave `retired` sigue activa en la
  base. Contar lo que terminó hace que el porcentaje baje para siempre por una
  decisión correcta. ⚠️ **Esto mueve las cifras del informe de cumplimiento**,
  igual que el arreglo anterior de la atribución por faena.
- **La región del permiso se deduce de las coordenadas, y dice que se dedujo
  (`LV-220`).** Presentar una región derivada con el mismo aspecto que una
  declarada es peor que dejarla vacía: quien lee la ficha para llenar el SIGO no
  podría distinguir el dato del papel de una inferencia. Va con su propio rótulo
  y con el aviso de la BCN, sólo cuando no hay dato declarado, y fuera de la
  cobertura cartográfica vuelve a decir "sin informar" en vez de adivinar.
- **El informe se congela solo y se aprueba a mano (`R5`).**
  `manage.py generate_monthly_report` deja el borrador del período con sus
  cifras fijas, para que quien firma llegue a una pantalla quieta en vez de a
  una vista previa que se mueve mientras la lee. **Congela y no aprueba**:
  aprobar es un acto de una persona —el informe va firmado ante la DGAC— y un
  trabajo nocturno que aprobara estaría firmando en nombre de alguien. **Es
  idempotente**, que es lo que le permite ser un timer: correrlo dos veces no
  crea dos informes. `--force` **emite la revisión siguiente y nunca
  sobrescribe**; las anteriores quedan marcadas como reemplazadas, no borradas,
  porque lo que se envió sigue siendo evidencia — y quién aprobó la revisión 0
  sigue siendo un hecho después de que exista la 1. La narrativa **viaja** a la
  revisión nueva: si las cifras se corrigen los hallazgos pueden quedar
  desactualizados, pero borrarlos obliga a reescribir de cero y ahí nadie nota
  que uno dejó de ser cierto. Aprobar cierra el informe y una corrección nace
  como revisión.
- **La pantalla de acceso dice qué hacer, y el bloqueo se explica.** Tras cinco
  intentos fallidos la cuenta queda retenida quince minutos, y hasta ahora eso
  devolvía **un 403 pelado en inglés** mientras el formulario decía "probá de
  nuevo" — justo lo que no funciona y lo que reinicia la espera. Ahora hay una
  pantalla propia que dice qué pasó, **cuánto dura** (leído del ajuste, no
  escrito a mano) y que la retención es sobre el nombre de usuario y no sobre el
  equipo, así que cambiar de computador no la levanta. El acceso gana además:
  **mostrar/ocultar la contraseña** y **aviso de Bloq Mayús** —las dos causas
  más comunes de gastar intentos, y con el bloqueo a los cinco eso cuesta la
  mañana—, una línea de ayuda que dice a quién pedirle el reinicio (no hay
  recuperación por cuenta propia), y **a qué instancia estás entrando**: la
  demo, el respaldo y producción tienen la misma cara, y cargar evidencia en la
  máquina equivocada es la peor equivocación posible de esa pantalla. Se quita
  el eslogan que estaba impreso **dos veces**, palabra por palabra.
- **El informe trae la tabla permiso a permiso y sus semáforos (`R4`).** La
  página 3 lista cada permiso con su folio JEJ, su número DGAC, la faena, los
  operadores designados, las aeronaves, la vigencia y los días que le quedan; la
  página 4 gana el **próximo vencimiento** de cada faena con sus días, y la
  concentración operacional deja de estar pendiente. **Los vigentes y las
  solicitudes en trámite van en dos bloques separados**: una solicitud no
  habilita a volar, y una tabla que los junte lo sugiere — sus días son un guion
  y nunca un cero, porque un cero se leería como "vence hoy". El semáforo del
  permiso corta en **30/60 días** y no en los 7/15/30 de los documentos, porque
  una renovación exige carta nueva del mandante y el aviso arranca a los 45; los
  **nombres** son los mismos niveles de severidad que ya usa el resto de la
  aplicación, así que el rojo significa lo mismo en la bandeja, en el panel y en
  el papel. El semáforo de una faena es **el peor** de sus habilitantes, nunca
  el promedio, y una faena sin permiso vigente es lo peor de la escala y no la
  ausencia de una. Y la tarjeta de "por vencer" pasa a contar **60 días**, que es
  lo que el informe emitido cuenta: hasta ahora se rotulaba por lo que medía —30—
  porque relabelarla habría sido inventar el dato.
- **La narrativa del informe se escribe dentro de la aplicación (`LV-227`).** Los
  dos bloques que el informe emitido trae redactados y que cambian todos los
  meses —los hallazgos y la observación del período— se guardan en el informe y
  se editan en un formulario. **No es un editor de plantillas**, y la distinción
  es la fila entera: las cifras no están ahí porque salen de la base, y corregir
  una cifra es corregir el dato. Si el formulario pudiera tocarlas, el informe
  dejaría de poder afirmar de dónde viene cada número, que es la garantía que lo
  hace firmable. Un hallazgo es **un juicio sobre** las cifras —"la renovación
  exige una nueva carta del mandante, cuya gestión debía haber comenzado ya"— y
  no se deriva de ninguna columna: lo escribe quien firma. Escribir necesita un
  informe donde guardar, así que aparece antes un botón que **congela el
  borrador del período**; es un paso explícito y no un efecto secundario de
  teclear el primer hallazgo, porque congelar es lo que separa "esto se mueve
  con la base" de "esto es el informe de agosto". **Un informe aprobado no se
  edita**: es el documento que se envió, y una corrección nace como revisión
  siguiente.
- **El informe cuenta el padrón que existía al corte, no el de hoy.** La función
  que da flota, seguros y credenciales recibía la fecha de corte y la usaba sólo
  para comparar vencimientos: la **población** era siempre la actual. Medido en
  producción, el payload de agosto devolvía 42 operadores y el informe emitido a
  la DGAC decía 41 — y uno generado en diciembre habría dado otra cifra más, que
  es justo lo que congelar el dato viene a evitar. **El panel no cambia**: con la
  fecha de hoy la condición es verdadera para toda fila, y una segunda función
  "igual pero con corte" es cómo el panel y el informe empiezan a discrepar.
  ⚠️ Lo que el corte **no** hace: no reconstruye el padrón de esa fecha, sólo
  deja de contar lo que todavía no existía. Sin historial de archivado no hay
  más, y hay un test que fija ese límite para que nadie lo lea de más.
- **El informe distingue una fecha ausente de una vencida.** Los "8 sin
  credencial vigente" del informe emitido eran **7 sin fecha cargada más una
  vencida**, y no se arreglan igual: una es cargar un dato que nadie ingresó, la
  otra es un trámite ante la DGAC. Sumadas, la cifra no dice a quién llamar — y
  encima no conversa con el resto del documento, porque una fecha ausente no
  genera alerta ni aparece en la lista de vencimientos. El panel ya hacía esta
  distinción; el informe la heredaba sumada.
- **Todo lo que se imprime deja de llevar el menú encima (`UX-06`).** El árbol
  tenía **cero** reglas `@media print`, así que cualquier impresión salía con la
  navegación entera arriba y el contenido estrujado en la columna que le dejaba
  la barra lateral. Ahora la navegación, los diálogos y los botones no se
  imprimen; ninguna fila de tabla se parte entre dos páginas y el encabezado se
  repite arriba de cada una; los fondos de las insignias de estado sobreviven,
  que es lo que distingue un "Vencido" de un "Vigente" en papel. Y sale un
  **sello de generación** —de qué pantalla, de qué servidor, cuándo y quién—,
  porque un papel que circula en una reunión sin eso no se contrasta con nada, y
  las cifras de cumplimiento cambian todos los días.
- **La severidad es un token, en cinco niveles (`UX-01`, `UX-03`).** Reutiliza
  los valores que `LV-D10` ya había medido para AA, y las clases nuevas **no
  llevan `!important`**. `UX-03` alinea las cifras con `tabular-nums`.

- **`manage.py check_email`: probar que el correo sale, no suponerlo (`LV-119`).**
  `manage.py check` pasa con el tubo cortado, que es cómo `p340` corrió meses
  imprimiendo cada notificación en el log. El comando nuevo informa la
  configuración —**nunca la contraseña**, sólo si está y cuántos caracteres
  tiene—, abre la conexión SMTP para probar host, puerto, TLS y credenciales, y
  con `--to` envía un mensaje real: un servidor puede autenticar y negarse a
  retransmitir con esa dirección de remitente, y eso sólo se ve enviando. Cada
  error nombra la variable que hay que revisar, y sale con código distinto de
  cero para que un paso de despliegue pueda apoyarse en él. Entra `EMAIL_USE_SSL`
  para el 465 con SSL implícito, que no tenía variable. **El correo sigue sin
  salir hasta que las credenciales estén en el entorno de `p340`**: el
  procedimiento quedó en `HANDOFF.md`.
- **"Solicitudes SIGO" sale del menú (`LV-150`, paso 1).** Desde que los datos de
  SIGO se leen y se copian en la ficha del plan, con una sola circunferencia no
  hay nada que separar y la lista era una pantalla a la que se llegaba sin tener
  nada que hacer en ella. **Nada se borra**: la vista, la URL y los permisos
  siguen enteros, y se llega igual desde el panel, desde el expediente del
  permiso y desde la ficha del plan, que gana un enlace contextual — "N
  solicitudes de este plan" — con un filtro nuevo por plan en el listado.
  Reversible descomentando una línea. Si en un mes aparece al menos una
  solicitud creada, el retiro se revierte en vez de avanzar.
- **"Datos para SIGO" se copia con un botón (`LV-149`).** Cuando el KMZ trae una
  sola circunferencia —el caso normal— la tarjeta deja de ser una tabla de seis
  columnas y pasa a ser una hoja de campo: área, comuna, provincia, región,
  latitud y longitud partidas en grados/minutos/segundos/hemisferio, radio,
  aeródromo y distancia, cada una en su caja rotulada y con un botón que la
  copia. Con varias circunferencias la tabla se queda —ahí la pregunta es cuál
  separar— y el botón entra sólo en la celda de coordenadas. Los tres avisos de
  honestidad (aeródromo propuesto, cartografía BCN referencial, círculo
  envolvente) siguen en las dos formas, palabra por palabra. Requiere
  `collectstatic` al desplegar.
- **La ficha del plan geoespacial dice de qué faena y de qué archivo es
  (`LV-149`).** El encabezado es más chico y muestra el código del centro de
  costo y el nombre del KMZ; el título guardado **no** se reescribe, así que un
  plan cuyo título escribió una persona lo conserva entero. El permiso enlazado
  pasa a ser un enlace. En el listado la segunda columna muestra el nombre del
  archivo y se puede buscar por él.
- **Informe de catastro de flota y personal (`LV-145`).** "Padrón → Informe de
  catastro": las dos tablas base —aeronaves y operadores— con la **fecha de corte
  declarada**, en pantalla, PDF con membrete, Excel y CSV. Filtros por centro de
  costo y estado, con la opción de incluir retiradas y archivadas. Cuando un
  filtro por faena deja fuera lo no asignado, el informe **dice cuánto**: el
  centro de costo es opcional en los dos modelos, así que filtrar escondía filas
  sin avisar. La pantalla muestra exactamente las celdas que imprime el papel.
  Exige los dos permisos de lectura (aeronaves **y** operadores), porque el
  documento lleva las dos mitades. Sin correo ni teléfono de las personas: se
  pidió el catastro, no una lista de contactos.
- **Los PDF llevan el membrete corporativo JEJ (`LV-144`).** Logo, azul de marca
  `#1E418C` (PANTONE 661 C), Helvetica, y un pie con la razón social, la dirección
  y "Página X de Y". El membrete es un helper compartido (`apps/core/branding.py`
  y `apps/core/pdf.py`) y el Reporte de cumplimiento es su primer consumidor: el
  mobiliario cambió y el contenido no, salvo la línea "Generado:" del cuerpo, que
  se fue porque el membrete ya imprime esa fecha en todas las páginas. En la tabla
  por centro de costo las cuatro columnas de vencimiento se pintan con los mismos
  colores que el panel. El correlativo `J.E.J. N° 00x-26` **no** se inventa: lo
  asigna una persona, así que el PDF lleva una referencia derivada y rotulada
  (`Ref. CUM-20260826`). El logo se lee del disco y nunca por URL, y si el archivo
  falta el informe sale igual con la razón social en su lugar. Requiere
  `collectstatic` al desplegar.
- **La causa de una no conformidad ahora se puede contar (`LV-127`).** Además del
  texto libre —que es lo que lee un auditor y se queda— hay una **categoría de
  causa raíz**: persona, procedimiento, equipo, material, entorno, planificación,
  información, y "sin determinar" como valor de partida. Sin ella, "¿de qué se
  repiten nuestras no conformidades?" sólo se responde leyéndolas todas, y por eso
  no se responde. Migración `compliance.0022`.
- **El número de serie, en la lista de aeronaves (`LV-126`).** Debajo de la
  matrícula y el modelo. La matrícula la ponemos nosotros; el serial lo pone el
  fabricante y es con el que la aeronave aparece en la garantía, en el registro
  de la DGAC y en las carpetas del repositorio documental.

### Fixed

- **«Archivar» se ve como lo que es (`LV-255`).** En las fichas de permisos y de
  planes geoespaciales el botón iba en gris, como «Volver»; ahora va en rojo, como
  en el resto de las fichas.
- **Las listas más usadas reparten bien sus columnas (`LV-254`).** Planes
  geoespaciales, vuelos, no conformidades, documentos y mantención dejan de repartir
  el ancho por contenido: los folios, las fechas y los códigos de faena ya no se
  parten, y el texto largo se lleva el espacio. En la **lista de permisos**, la
  columna de operadores había quedado **sin ancho** con el cambio de `LV-246`; ahora
  tiene el suyo, y la fila muestra tres nombres y «+N más» (la nómina completa sigue
  en la ficha y al pasar el ratón). **Mantención**, la pantalla de inicio del rol
  Mantenimiento, gana lo que las demás listas ya tenían: búsqueda mientras se
  escribe, selección múltiple, columnas ocultables y la vista de tarjetas en el
  teléfono. Documentos marca en rojo lo vencido también en la lista. Y cuando un
  filtro no encuentra nada, estas listas ofrecen quitarlo en vez de decir que no hay
  registros.
- **Una sola forma de decir «vencido» (`LV-253`).** Pólizas, credenciales,
  habilitaciones, pruebas de conocimientos y documentos vencidos se marcaban con el
  mismo rojo que «Rechazado» o «Insuficiente». Ahora todos llevan la misma insignia
  con **⚠**, la del panel. Y la ficha del operador **avisa cuando su credencial DGAC
  venció** — hasta ahora sólo lo decía la lista.
- **Los mensajes de error salen en rojo (`LV-252`).** Los 32 avisos de error de la
  aplicación se mostraban sin color: la clase que los pintaba no existe. También: la
  lista de mantención hacía una consulta por fila, y el panel calculaba «y N más» con
  un número fijo en vez del real.
- **El informe mensual es más corto: la sección de permisos cabe en una hoja
  (`LV-248`).** La tabla dice ahora «4 operadores» en vez de listar cada nombre, y la
  nómina completa va a un anexo al final — nada sale del papel. El ciclo de cuatro
  pasos del permiso pasó a ser una nota breve en el resumen. Y lo que de verdad
  alargaba la tabla era un error de estilo: el folio se partía en dos líneas porque
  la letra salía más grande de lo que el diseño pedía. Con los datos de hoy el
  informe queda en 5 hojas más el anexo, y se corrigió de paso un caso límite en que
  el bloque de cierre de la sección podía quedar recortado sin aviso.
- **Cuatro defectos del informe mensual (`LV-247`).** Emitir una revisión para
  corregir una cifra **borraba las acciones** ya escritas. El Dato Ejecutivo titulaba
  «Vencimientos próximos 60 días» sobre filas que cuentan lo **ya vencido**. Su hoja
  no tenía formato de página —usaba un estilo que no existía— y salía como texto
  suelto. Y un comentario del código describía un estado de hace semanas.
- **Lo vencido se ve, y en rojo (`LV-246`).** Tres pedidos del mismo día. En el
  panel, las **faenas sin permiso vigente van primero** y en rojo, con una tarjeta
  nueva que las cuenta: es el mismo indicador que el informe mensual firma, y hasta
  ahora sólo existía en el papel. La fila que debía destacarlas **nunca se había
  pintado**: usaba una clase de estilo que no existe. En la lista de permisos, un
  permiso caducado dejó de verse en el mismo ámbar que uno «Solicitado»: ahora dice
  **«⚠ Caducado» en rojo**, incluido el que venció anoche y el trabajo nocturno
  todavía no cerró. La lista se reparte mejor (los folios y las fechas ya no se
  parten en dos líneas). Y un plan geoespacial aprobado cuyo permiso caducó muestra
  **«⚠ Permiso vencido»** en la lista y en su ficha.

### Added

- **Ver qué cambió entre dos informes (`LV-251`).** El botón «Ver los cambios»
  compara el informe con su revisión anterior —qué se corrigió— o con el del mes
  anterior —cómo se movió la operación—: los 18 indicadores con su diferencia, los
  permisos que entraron y salieron, y el texto escrito que cambió. Compara los
  informes tal como quedaron congelados, así que lo que muestra es lo que cada uno
  dijo cuando se emitió. Era la mitad pendiente de un pedido del 8 de septiembre.
- **El borrador del informe mensual se congela solo el día 1 (`LV-250`).** Hasta
  ahora había que hacerlo a mano. Queda listo para instalar el trabajo programado
  que lo deja con las cifras fijas —sin aprobarlo: la firma es de una persona— y
  el vigilante de trabajos avisa si un mes no corrió. La hora está elegida para
  que el reloj en UTC del servidor no congele el mes equivocado.
- **Los textos fijos del informe mensual se editan desde la app (`LV-249`).** La
  portada, las fases del plan de normalización y la matriz de exigibilidad estaban
  escritas en el código —la matriz decía «SEP–DIC» a mano, así que en enero habría
  quedado vieja— y cambiar una coma exigía un despliegue. Ahora hay una pantalla
  «Textos del informe», con el mismo permiso que la narrativa. Las columnas de la
  matriz salen de las fases: agregar una fase agrega su mes. **Un informe ya
  emitido no cambia** al editar: estos textos se copian al informe cuando se
  congela, que es lo que lo vuelve un documento controlado.

### Changed

- **Dependencias al día: Django 6.1.1, crispy-bootstrap5 2026.9, pytest-django
  4.14.0 y reportlab hasta la 6 (`LV-244`).** Las cinco ramas de Dependabot que
  estaban abiertas, resueltas de una. Dos de ellas **no se podían mergear**: eran
  de antes de la tanda de septiembre y su diff revertía trabajo — bajaban Django a
  6.0.7 y borraban dependencias añadidas después. Se tomó sólo la subida de
  versión de cada una. `ruff` se queda en 0.15.22 a propósito: la 0.16 amplió las
  reglas por defecto y trae 480 hallazgos, de los cuales 268 son el patrón normal
  de un modelo Django. Es una decisión de política de linting, no un bump, y queda
  anotada para tomarla aparte.

### Fixed

- **Una faena sin registros ya no dice «todo al día» (`LV-243`).** Al elegir una
  faena administrativa en el filtro, las tarjetas mostraban «0/0 · todo al día»:
  con nada que contar no hay nada vencido ni sin fecha, así que la tarjeta caía a
  la frase de cierre y **declaraba cumplimiento sobre un conjunto vacío** — en la
  tira que existe para contestar «¿puedo operar hoy?». Ahora dice «sin registros».
  Cuando sí hay registros y sí están todos al día, se sigue diciendo.
- **Las cifras del panel ahora llevan al trabajo que anuncian (`LV-242`).** Decía
  «1 vencido» y el clic traía las dieciséis aeronaves, así que el número informaba
  y no servía: el filtro por vigencia no existía en ninguna de las dos listas.
  Ahora la tarjeta lleva exactamente a los que contó — y el criterio vive en un
  solo lugar, para que la lista no muestre cinco donde la tarjeta dijo cuatro. Con
  eso, tres arreglos de la misma familia: «Abrir» en la bandeja abre **la alerta**
  y no el listado entero (las veinte filas apuntaban a la misma página), la lista
  de vencimientos **dice cuántos esconde** cuando se corta en diez, y la tabla por
  faena muestra **la fecha del próximo vencimiento** — un dato que ya se calculaba,
  que el informe dibuja hace meses y que el panel descartaba, siendo el que dice
  cuál renovar primero.
- **Lo vencido se contaba mal, y por eso el panel se veía limpio (`LV-241`).**
  Pedido del usuario mirando la pantalla: una faena tenía dos documentos atrasados
  en la lista de vencimientos y su fila de la tabla de permisos estaba **entera en
  guiones**. La causa no era un rótulo: la columna «Vigencia pasada» contaba sólo
  los permisos *aprobados* con fecha pasada, y el trabajo nocturno los pasa a
  *caducado* cada noche — así que **el permiso vencido salía del conjunto antes de
  que nadie lo viera**, y la faena cuyo único permiso caducó desaparecía de la
  tabla. Ahora se cuentan los dos hechos y siguen separados, porque se arreglan
  distinto: un aprobado sin cerrar delata que el cron no corrió; un caducado del
  mes es trabajo de renovación. **El porcentaje no cambia**: el denominador sigue
  siendo los permisos vivos, así que la cifra que va firmada a la DGAC mide lo
  mismo que ayer y lo vencido se ve al lado, no dentro.
- **Las tarjetas del panel ya no muestran un número sin decir de qué es
  (`LV-241`).** Se leía *"13/14 · **1** · 2 vencen en 30 días"*. Tres de las cuatro
  tarjetas no tenían rótulo para su faltante, así que cuando ese faltante no era
  ninguno de los casos con nombre —vencido, sin fecha, esperando— el número salía
  mudo. En permisos ese 1 era uno **aprobado que todavía no empieza**, un dato que
  se calculaba desde hace semanas y que ninguna pantalla dibujaba.
- **El correo diario avisaba de dos de seis fuentes (`LV-240`).** El seguro JAC, la
  credencial DGAC, la prueba de conocimientos y la vigencia del permiso salían en
  el panel y **no** en el correo, porque cada uno tenía su propia forma de juntar
  lo que vence. La que se quedaba corta era la única que va a buscar a la persona:
  el panel hay que abrirlo, el correo llega. Hoy no se notaba porque todavía no
  sale correo de la VM — se habría notado el día de encender el SMTP. De paso el
  correo hereda tres reglas que le faltaban: no repite lo que ya se revisó y se
  cerró (decisivo en algo que llega **cada mañana**), no avisa por equipos dados de
  baja, y de la prueba de conocimientos toma sólo la última de cada persona.

### Changed

- **El plan geoespacial abre en satélite (`LV-239`).** Pedido del usuario: el área
  de un plan es terreno —un tranque, una ladera, un rajo— y sobre el callejero la
  circunferencia queda flotando en blanco, así que había que cambiar de capa antes
  de poder mirar nada, todas las veces. El callejero sigue a un clic. De paso deja
  de depender del **orden** de la lista de proveedores: cuál capa sale al abrir
  era un efecto de qué entrada iba primero en la configuración, y ahora está
  marcado explícitamente — reordenar esa lista ya no cambia en silencio lo que ve
  el operador.
- **El panel deja de pagar por trabajo que nadie mira: de 58 consultas por carga
  a 48 (`LV-237`).** La pantalla dice exactamente lo mismo; lo que cambia es lo
  que cuesta abrirla, y se abre en cada inicio de sesión. Cuatro cosas, y tres
  son la misma historia: **una sección se retira de la pantalla y su cálculo se
  queda vivo**, porque mirando la pantalla no se nota. (1) El **pronóstico del
  tiempo**, cuya tarjeta el usuario mandó retirar hace un mes (`LV-216`): se
  borró de la plantilla y la vista siguió calculándolo en cada carga —permisos
  con coordenadas, sitios, el plan geo ligado y la posible salida al proveedor—
  para un contexto que ya nadie leía. (2) Los **dos gráficos** que `LV-89` había
  retirado, que seguían agregándose y viajando al navegador sostenidos por un
  test que los usaba como evidencia. (3) El **número de permisos vigentes**,
  calculado dos veces para dibujarlo dos veces a cien píxeles de distancia. Y
  (4) la consulta de alertas resueltas, que **no tenía cota ninguna**: traía toda
  la historia de la operación a memoria en cada login para filtrar una lista de
  diez filas, así que su costo crecía para siempre sin que se notara en pantalla.
  Ahora se pregunta sólo por lo que se va a mostrar. Nada de esto cambia una
  cifra: lo que el panel decía ayer es lo que dice hoy. La fila deja además un
  **techo de consultas sobre la vista entera** —había techos sobre funciones
  sueltas y ninguno sobre el panel—, que es lo que habría delatado el clima el
  mismo día en vez de un mes después.
- **La tarjeta "Esperando SIGO" dice cuánto lleva esperando la más antigua
  (`LV-237`).** Decía "3", y había que bajar tres bloques de la pantalla para
  saber si eran de ayer o de hace dos meses — que es la única parte que decide si
  hay que llamar a la DGAC. El dato se calculaba desde `R9.6`, tenía sus pruebas
  y ninguna plantilla lo dibujaba; ahora se lee al lado del número, sin costar
  una consulta.
- **Una faena con contrato cerrado sale del indicador de cumplimiento
  (`LV-236`).** Pedido del usuario mirando el panel: eran siete faenas cerradas
  ocupando la tabla con "Ninguno". No era sólo ruido de pantalla — esas filas son
  el universo del indicador **que va firmado a la DGAC**, así que cada faena
  terminada empeoraba una cifra de cumplimiento por una operación que ya no
  existe. La regla no admite excepción, por decisión del usuario: *"independiente
  que tenga permiso o no, si está cerrado no cuenta"*. De paso, el denominador de
  ese indicador pasa a **ser** las filas de la tabla en vez de una consulta
  aparte que debía coincidir con ellas — que es como un informe empieza a decir
  "7 de 12" en una página y "7 de 11" en la siguiente.
- **Desde una alerta se llega a la ficha de la entidad (`LV-125`).** Clicar
  `RPA-5534` abre su aeronave, que es donde están el estado del seguro, el
  historial del trámite y los documentos. Antes había que ir al padrón, buscar la
  matrícula y entrar: tres pasos hasta la única pantalla desde la que se resuelve.
  El enlace sale de `get_absolute_url` del propio objeto, así que aparece para lo
  que tiene ficha sin mantener un mapa de tipos.
- **Diez orígenes de no conformidad en vez de cuatro (`LV-127`).** Entran reclamo
  del cliente, documento vencido o faltante, falla de equipo, desviación de
  procedimiento, observación en terreno y condición externa. Con los cuatro
  anteriores había que meter en "Incidente" cosas que no lo son, y con eso
  agrupar por origen dejaba de decir nada. Las claves originales se conservan.
- **Entregables sale del menú (`LV-128`).** No se está usando y ocupaba sitio en
  la columna de cumplimiento. La función queda entera —modelo, vistas, permisos y
  URL—; volver a mostrarla es descomentar una línea.

### Added

- **Se registra por qué se cerró un plan, para poder contarlo (`LV-178`).** Dos
  motivos: **rechazo de la DGAC** y **modificación interna**, más *Otro* que
  exige decir cuál. Son cosas distintas y por eso se cuentan aparte: diez
  rechazos de la autoridad dicen que estamos presentando mal, diez
  modificaciones internas son trabajo normal. No se deduce del estado —un plan
  aprobado puede archivarse por modificación interna— y los planes archivados
  antes de esto quedan **sin motivo**, porque inventarles uno haría mentir a
  cualquier informe.
- **Del clima del panel a donde ese clima queda registrado (`LV-179`).** La
  tarjeta del panel se recalcula en cada visita y no guarda nada; la ficha del
  plan muestra el pronóstico sobre el área dibujada y ahí se archiva como
  evidencia. Ahora hay un enlace entre las dos. No se repiten las cifras: dos
  pantallas con el mismo pronóstico y una sola que deja constancia invita a
  mirar la que no registra y creer que se hizo el chequeo.
- **El plan geoespacial se cierra junto con sus permisos, sin cascada
  (`LV-176`).** Al archivar un plan aparece una casilla por cada permiso ligado
  y vivo —los del plan y los de las solicitudes SIGO nacidas de él—, todas
  desmarcadas: lo que no marcás sigue abierto. Cada permiso cerrado deja su
  propia entrada de auditoría, y todas comparten el identificador de la
  petición, así que se ve que fue un solo acto.
- **El padrón se ordena por apellido (`LV-177`).** Estaba ordenado por el nombre
  de pila, porque el nombre vive en un solo campo. Entran dos campos auxiliares
  —nombres y apellidos— que **nacen vacíos**: mientras no estén cargados, la
  ficha ordena por su nombre completo y no desaparece de donde se la busca. El
  comando `split_operator_names` propone el corte y sólo escribe con `--apply`,
  dejando a mano los que no calzan en el patrón. El nombre completo sigue siendo
  el de registro.
- **Un intento de la prueba se puede retirar, archivándolo (`LV-173`).** Nunca
  borrándolo: además de la regla del proyecto, un intento aprobado alimenta el
  motor de vencimientos, y `generate_alerts` sólo mira los activos. Si al
  archivar la persona queda **sin prueba vigente**, se avisa antes con su
  nombre y con la consecuencia escrita —su alerta deja de generarse—; si el
  intento no sostenía ninguna vigencia, se archiva directo. Los archivados
  quedan a la vista en la ficha, con su botón para restaurarlos, y tanto
  archivar como restaurar quedan en la auditoría.
- **El catastro cierra con su total (`LV-172`).** Cuántas aeronaves y cuántos
  operadores, al final del documento y no sólo en el encabezado: con varias
  páginas de tablas, el total del cierre es lo que confirma que no se cortó
  nada. Sale de la misma función en pantalla y en el PDF, así que no pueden
  decir cifras distintas. **No** se agrega al CSV ni a la planilla: una fila de
  totales dentro de un archivo de datos rompe ordenar, filtrar y sumar.

### Security

- **La clave de respuestas deja de mostrársele a quien rindió la prueba
  (`LV-184`).** La revisión listaba la respuesta correcta de cada pregunta
  fallada, a la persona que acaba de rendir y puede volver a rendir: con eso se
  memoriza y se aprueba, y un intento aprobado alimenta el motor de
  vencimientos. Ahora hace falta el permiso `view_assessment_answers`, que va al
  rol **Compliance** y no al de quien rinde. Quien rindió sigue viendo qué falló
  y qué contestó — lo que sirve para estudiar, sin el examen resuelto.
  **Al desplegar hay que correr `bootstrap_roles`.**

### Added

- **El panel y el informe dicen cuántos permisos hay vigentes (`LV-201`).** La
  fila de indicadores mostraba flota, seguros y credenciales, y ninguna cifra del
  objeto que la aplicación existe para tramitar. Ahora hay una cuarta: permisos
  vigentes sobre los que están vivos, con los que esperan aprobación de la DGAC y
  los que ya pasaron su vigencia contados aparte, porque se resuelven distinto.
  La misma cifra aparece en el informe y sale de la misma función, así que las dos
  pantallas no pueden discrepar.
- **"Patrullaje" entra al vocabulario de propósito (`LV-196`).** Hasta ahora un
  patrullaje se registraba como "Otro" con el detalle en texto libre, así que no
  se podía contar ni filtrar. Los permisos ya guardados no se reclasifican: mover
  una fila histórica es decisión de quien la mira, no de una migración.

### Fixed

- **Una novena frase con tono rioplatense en la interfaz, y el guardián que
  faltaba.** El aviso de cuenta bloqueada decía "si necesitás levantarla antes".
  El día anterior se habían neutralizado ocho frases y el trabajo se dio por
  cerrado, con ésta viva: una revisión manual que se declara completa y no lo
  está es peor que no haberla hecho, porque nadie vuelve a mirar. Ahora una
  prueba automática revisa el catálogo entero en cada entrega.

- **La misma carta en varios permisos deja de subirse varias veces (`LV-200`,
  segundo paso).** El primer paso sabía reconocer el archivo repetido y sólo lo
  comentaba. Ahora, cuando el archivo es byte por byte el mismo, la fila del
  permiso nuevo apunta al que ya está cargado y no se escribe una segunda copia:
  **dos permisos, dos filas de documento, un solo archivo.** Se reutiliza el
  archivo y **no** se comparte la fila, y ésa es la decisión de fondo — un
  documento por permiso deja intacto el expediente, la atribución por faena y
  los porcentajes del informe de cumplimiento, donde un documento contado dos
  veces o ninguna mueve una cifra que va a la DGAC. La limpieza de documentos
  archivados comprueba ahora que ninguna otra fila viva use ese archivo antes de
  borrarlo: sin esa guarda, archivar un permiso se habría llevado el papel de
  otro sin avisar, a diez años de retención vista.
- **Dos papeles que eran el mismo vuelven a ser uno (`LV-230`).** El expediente
  pedía dos veces la carta del mandante y la bandeja mostraba dos alertas por un
  solo vencimiento. La causa no fue una lectura descuidada: el tipo que ya
  existía se llamaba "Autorización DGAC (carta de permiso)" mientras su propia
  documentación decía que es lo que va **hacia** la DGAC. **Un nombre equivocado
  hizo inventar un tipo nuevo**, así que el arreglo de fondo es el nombre. El
  catálogo vuelve a 19 tipos, su valor original.
- **Tres alertas por el mismo vencimiento eran ruido, no escalamiento
  (`LV-232`).** Se retira el aviso a 15 días, que repetía la fecha del de 30 y
  sólo cambiaba el destinatario. Quedan dos, cada uno con su propia acción:
  pedir la carta y renovar el permiso. El escalamiento a Gerencia se queda en
  `check_client_letters`, que es de solo lectura y no ensucia la bandeja.
- **Cada sección del menú tiene su propio color (`LV-207`).** Antes el color lo
  daba la pantalla de destino, no la sección, así que Informes mezclaba azul y
  ámbar, Inventario mezclaba azul y gris, y tres secciones compartían el azul —el
  color no servía para agrupar ni para distinguir. Ahora las ocho secciones se
  diferencian entre sí, y los iconos siguen cumpliendo el contraste mínimo en los
  dos temas.
- **El panel ya no cuenta como brecha los equipos que están en bodega
  (`LV-229`).** Una aeronave de un centro administrativo, que no opera, figuraba
  como "sin seguro al día" y bajaba el indicador por una decisión correcta. La
  tabla de permisos por faena ya excluía esos centros; ahora el contador de flota
  también, así que las dos cifras del panel dicen lo mismo sobre la misma faena.
  Una aeronave **sin** faena asignada sigue contando: eso es un dato que falta, no
  un equipo que no vuela.
- **La ficha del permiso enlaza a los NOTAM de su aeródromo (`LV-218`).** Un clic
  desde el permiso a la consulta oficial del IFIS de la DGAC para el aeródromo más
  cercano que el permiso declara. **La app no resume ni interpreta los avisos**:
  lleva a la fuente, porque un aviso mal leído o una consulta fallida no pueden
  parecer "no hay NOTAM". Si el permiso no tiene aeródromo declarado, no se ofrece
  el enlace.
- **La altitud del permiso se pide en metros (`LV-221`).** El campo decía pies, y
  la operación piensa y vuela en metros: los tres permisos que tenían el dato
  cargado decían 120 pensando en metros, o sea un tercio de la altura real. Ahora
  se escribe en metros y la ficha muestra al lado el equivalente en pies —394 ft
  para 120 m— listo para copiar al formulario del SIGO sin calcular. Los valores
  ya cargados se corrigieron, y el número original queda guardado por si alguna
  solicitud ya se había presentado con él.
- **Las etiquetas de tipo ahora tienen color (`LV-217`).** En la lista de
  vencimientos y en la bandeja de alertas, los tipos iban todos del mismo gris, así
  que había que leer cada etiqueta para saber de qué hablaba la fila. Ahora el
  color dice de qué cuelga el vencimiento: de una persona, de una aeronave, del
  permiso, o de un documento. Los colores de urgencia (rojo y ámbar) siguen siendo
  solo de la urgencia, para que no compitan.
- **El ancho de la barra de navegación se regula arrastrando su borde (`LV-208`).**
  Antes había dos estados y nada en medio: abierta o en modo icono. Ahora el borde
  se arrastra, el ancho se recuerda entre visitas, y un doble clic lo devuelve al
  valor original. Funciona también con el teclado (flechas, `Inicio` y `Fin`), y el
  botón de colapsar sigue haciendo lo mismo de siempre.
- **Los listados de operadores y aeronaves se leen parejos (`LV-222`).** Al buscar,
  las casillas quedaban a distintas alturas y un nombre largo desordenaba la
  columna entera; con las aeronaves era peor, porque su etiqueta lleva matrícula,
  modelo y número de serie. Ahora cada fila queda alineada y el texto que ocupa
  dos líneas se indenta bajo sí mismo, no bajo la casilla. El buscador y el
  contador "3 de 42 elegidos" siguen igual.
- **La app ya conoce el plazo de la DGAC: 3 meses (`LV-224`).** El máximo se lee
  en la casilla de "Vigente hasta" antes de escribir nada, y una vigencia más
  larga se rechaza diciendo cuál es la última fecha posible. Si la DGAC otorgó de
  verdad un plazo distinto, se puede guardar escribiendo el motivo, que queda
  registrado — la app no obliga a falsear una fecha para cargar el papel que
  existe.
- **La carta del mandante entra al expediente del permiso (`LV-225`).** Es el
  tercer papel del trámite y el único que no es de la DGAC: la emite el cliente, y
  sin ella la DGAC no renueva. Aparece en el expediente como los otros dos y no
  bloquea la aprobación, porque lo que autoriza a volar sigue siendo la
  autorización firmada.
- **Avisos de renovación a 45, 30 y 15 días (`LV-226`).** El primero sale a 45 y no
  a 30 porque la carta del mandante hay que pedírsela a un tercero y eso toma
  tiempo. Cada umbral deja su propio aviso, así que un permiso próximo a vencer
  acumula tres — que es la señal de que ya no queda holgura. Además, un chequeo
  diario lista los permisos por vencer **sin** la carta cargada.
- **Pedir un permiso ya no obliga a inventar dos fechas (`LV-219`).** "Vigente
  desde" y "Vigente hasta" eran obligatorios en el alta, pero la vigencia la fija
  la DGAC al responder: antes de eso nadie la sabe. Ahora quedan vacías mientras
  el permiso está solicitado, y se exigen al aprobarlo, que es cuando ya vienen
  en la autorización firmada. Un permiso sin vigencia **no caduca solo, no cuenta
  como vigente ni como vencido, y no aparece en el calendario ni entre los
  vencimientos próximos** — queda en "esperando a la DGAC", que es lo que de
  verdad es. Tampoco se le puede registrar un vuelo: sin autorización no hay
  vuelo que registrar, y ahora lo dice en vez de fallar.
- **La ficha del permiso ya muestra la región, incluso cuando falta (`LV-220`).**
  La fila sólo se dibujaba si había región, comuna o nombre de área, así que en un
  permiso sin los tres desaparecía entera y no se distinguía de un dato que no
  aplica. Ahora dice "Sin informar", que es lo que corresponde: la DGAC pide la
  región en el formulario del SIGO. No se deduce de las coordenadas — una región
  inferida no debe verse igual que una declarada.
- **El clima sale del panel (`LV-216`).** No se miraba ahí y además mostraba "el
  pronóstico no está disponible" cuando el proveedor no responde. La revisión
  meteorológica que el expediente pide se sigue registrando en la ficha del plan,
  que es donde siempre estuvo el botón.
- **Un formulario caducado ya no responde con un 403 en blanco (`LV-215`).**
  Cuando una pestaña queda abierta de un día para otro, su ficha de seguridad
  caduca y el envío se rechaza — correctamente, pero antes con un mensaje que no
  decía qué hacer. Ahora la página explica que caducó y ofrece volver a cargarla o
  entrar de nuevo. El rechazo no cambió: sigue siendo un 403.
- **La ficha del centro de costo ya no pide coordenadas ni criterios de calidad
  (`LV-213`).** Salieron del formulario a pedido: esa información no va ahí. Los
  valores que ya estaban cargados **se conservan** — quitar un campo del
  formulario, y no sólo de la pantalla, es justamente lo que evita borrarlos. Con
  esto, las coordenadas de una faena nueva sólo se pueden cargar por importación,
  así que no aparecerá en el selector de clima del panel hasta que las tenga.
- **Las cifras de la tabla del panel quedan bajo su título (`LV-214`).** Iban
  pegadas al borde derecho de la celda, lejos de la palabra que las nombra.
- **Editar un centro de costo ya no borra lo que la pantalla no muestra
  (`LV-211`).** La ficha dibuja sus campos uno por uno, y cinco del formulario no
  estaban ahí: la casilla nueva de "en esta faena se vuela", las coordenadas del
  sitio —de las que sale su pronóstico— y los tres criterios de calidad del
  contrato. Un campo que no se dibuja no se envía, así que bastaba corregir un
  nombre para perderlos. Ahora están todos, y un test exige que la plantilla siga
  completa cuando alguien agregue el próximo.
- **La caja de borradores ya no aparece cuando no hay ninguno (`LV-210`).** Se
  dibujaba vacía, con el botón "Retomarlo" suelto: el arreglo anterior corregía
  el ocultar pero no el estado inicial.
- **"Vence pronto" tiene su propia columna en la tabla del panel (`LV-212`).**
  Iba pegado al total en la misma celda, y así la columna no se podía leer de un
  barrido.
- **El botón "Descartarlo" del borrador ya surte efecto (`LV-209`).** Borraba el
  borrador pero el aviso seguía en pantalla, así que parecía muerto. La causa era
  de estilos: el atributo que lo escondía perdía contra la clase de disposición
  del propio aviso, las dos con la misma prioridad y ganando la última. Ahora la
  visibilidad pasa por un solo lugar, y hay un test que vigila el orden de esas
  reglas — de él depende que el arreglo siga funcionando.
- **El panel muestra los permisos de vuelo faena por faena (`LV-206`).** Incluidas
  las que **no** tienen ninguno vigente, que son las que interesan mirar. Las
  faenas que sólo tienen equipos a cargo y no vuelan quedan fuera con una casilla
  en su ficha: listarlas ahí las declararía incumplidas por una operación que no
  les toca. La tabla ocupa el lugar del clima, que baja al final de la pantalla —
  no se quita, porque es desde donde se registra la revisión meteorológica que el
  expediente pide.
- **Archivar a un operador que se retira deja de dónde venía (`LV-205`).** Se
  cierra su asignación con la fecha y queda registrado de qué centro de costo
  venía, con esa faena guardada **en el movimiento** y no leída de la ficha: la
  ficha puede cambiar después, y entonces el registro contaría otra cosa. El aviso
  nombra la faena, para poder corregir en el momento si se archivó a la persona
  equivocada.
- **El alta del permiso ya no pide los datos que trae el plan (`LV-197`).** Región,
  comuna, nombre del área, latitud, longitud y radio salen del KMZ al elegir o
  vincular el plan, así que el formulario dejó de pedirlos a mano. La altitud
  máxima y la ubicación en palabras se siguen pidiendo: ningún KMZ trae altitud.
  La pantalla de edición los ofrece mientras estén vacíos, y `?ubicacion=manual`
  los devuelve cuando la resolución de la DGAC trae otra coordenada.
- **Los borradores se ven desde el listado de permisos (`LV-198`).** El aviso
  vivía al pie del formulario, así que un borrador sólo se descubría volviendo a
  esa pantalla. Ahora el listado dice cuántos hay y lleva a retomarlos — en este
  navegador, que es donde viven. De paso, el aviso ya no muestra un paréntesis
  vacío cuando el borrador no tiene fecha.
- **Un archivo repetido se reconoce al subirlo (`LV-200`, primer paso).** La huella
  del contenido se calculaba sólo al importar del repositorio, así que todo lo
  subido desde la app no la tenía. Ahora se calcula al subir y, si el archivo es
  idéntico a uno ya cargado, se avisa nombrándolo — sin impedir la subida, porque
  la misma carta cubriendo dos permisos es lo normal. Los documentos cargados
  antes no tienen huella todavía.
- **Un plan vinculado a un permiso se puede desvincular (`LV-199`).** Vincular no
  tenía inversa, así que un vínculo hecho por error sólo se deshacía por el admin
  de Django. La ubicación que el plan rellenó **se queda en el permiso** y el
  aviso lo dice: borrarla dejaría un permiso aprobado sin coordenadas. El
  desvínculo queda en la bitácora que ya registraba los cambios de ese vínculo.
- **Archivar un plan se puede hacer desde el listado (`LV-203`).** La acción
  existía —con su permiso propio y su confirmación con motivo escrito— pero la
  columna de acciones sólo ofrecía "Restaurar": la vuelta sin la ida. Ahora está
  el camino completo, y sigue pasando por la misma confirmación.
- **Toda entidad dice de qué faena es, incluida la que cuelga de otra
  (`LV-204`).** La alerta de una aeronave mostraba su centro de costo y la de un
  documento no mostraba ninguno. Faltaban tres caminos en la tabla de rutas
  —centro de costo, plan geoespacial y solicitud de vuelo—, y los dos últimos son
  los más probables al principio de una faena, cuando los papeles llegan antes
  que el permiso. Ahora el chip, el filtro por faena, el resumen por correo y el
  informe de cumplimiento los conocen todos.

### Security

- **La lista de vencimientos del panel respeta los permisos del usuario
  (`LV-191`).** Las cinco fuentes se listaban sin comprobar si el usuario podía
  ver ese tipo de registro, y cada fila nombra su sujeto: el folio de un permiso,
  la matrícula de una aeronave, **el nombre de una persona junto a su credencial
  DGAC por vencer**, el título de un documento. En una pantalla que se abre en
  cada inicio de sesión, lo veía cualquiera que pudiera entrar. Ahora cada fuente
  pide el permiso de lectura de su propio modelo — ninguno nuevo: quien puede ver
  la ficha de una aeronave puede ver que su seguro vence. Lo tapaba por accidente
  el guard de bienvenida, que escondía la sección entera cuando la base parecía
  vacía; en producción, donde no lo está, no tapaba nada.

### Fixed

- **Un documento pertenece a la faena del registro del que cuelga (`LV-188`).**
  La atribución conocía siete modelos y el filtro sólo dos, así que la Carta
  Permiso del panel salía con el chip `CC738` y **desaparecía al filtrar por
  `CC738`**: la fila afirmaba una faena y el filtro de esa misma faena la
  negaba. No era sólo esa pantalla: la misma función alimenta la tarjeta de
  alertas pendientes, el resumen diario por correo y el informe de cumplimiento
  por faena — y ahí no hay filtro de usuario de por medio, así que los
  documentos colgados de un permiso, de un mantenimiento, de una habilitación o
  de una revisión mensual **no contaban en el cumplimiento de ninguna faena**.
  Las dos mitades pasan ahora por un solo recorrido de la misma tabla, con un
  test que falla si alguien agrega un modelo y no su caso. **El informe y el
  histórico de `ComplianceSnapshot` van a mover sus números con este arreglo**:
  lo que cambia es el universo contado, no el cumplimiento real.
- **La tarjeta de bienvenida ya no esconde la operación (`LV-187`).** El panel
  envolvía todo su contenido en una condición de primera pantalla que miraba
  aeronaves, operadores y alertas — los tres respetan el filtro por faena y los
  vencimientos no entraban. Elegir una faena sin flota ni padrón reemplazaba el
  panel completo por "Comienza tu operación", con vencimientos reales de esa
  faena detrás. Ahora el guard mira también los vencimientos y **sólo aplica sin
  filtro**: con una faena elegida se ve el panel con sus vacíos propios, que
  dice la verdad sobre esa faena en vez de sobre la operación.

### Changed

- **El expediente operativo pierde los dos renglones que no podían cerrarse
  (`LV-194`).** "Solicitud SIGO de origen" y "Vuelos registrados contra este
  permiso" nacían en ámbar y no había forma de resolverlos — el módulo SIGO salió
  del menú en `LV-150` y la bitácora de vuelos se lleva contra la faena—, así que
  el encabezado decía "2 por confirmar" en todo permiso, para siempre, y ningún
  expediente podía leerse como completo. Retiro de pantalla, no de base:
  registrar un vuelo sigue en su propio módulo.
- **El mapa ya permite dibujar una circunferencia, con su centro (`LV-202`).** No
  había herramienta de círculo: el botón redondo de la barra es el de punto, así
  que apretarlo dejaba un marcador. Ahora se dibuja la circunferencia y, al
  terminar, queda también su pin central — que es lo que el backend usa para
  medir el radio y lo que se copia a la hoja de SIGO. Se guarda como anillo
  cerrado de 64 lados, la misma forma en que llegan los círculos de los KMZ de
  Trimble, así que dibujar y importar producen lo mismo.
- **Un espacio en una celda del manual ya no bloquea la carga completa
  (`LV-195`).** El Capítulo 1 Rev 17 trae dos números de serie partidos por un
  espacio, y el importador los comparaba en crudo contra los de la base, que se
  guardan sin espacios: las dos aeronaves salían como "serie nueva", y un
  conflicto detiene la corrida entera — así que un salto de línea en el Word
  impedía cargar también las 48 fichas de personal. Ahora la comparación usa la
  misma normalización que el resto de la app.
- **El importador del Capítulo 1 ya no puede duplicar una persona (`LV-190`).** El
  cruce iba sólo por número de empleado, así que una ficha dada de alta a mano
  —con otro número— no se reconocía y la persona se creaba de nuevo, sin que la
  base pudiera impedirlo. Ahora cruza también por RUT y se detiene con un
  conflicto que nombra la ficha existente, y guarda el RUT en su forma canónica.
- **El listado de permisos dice de qué faena es cada uno (`LV-192`).** El dato ya
  iba en el CSV y no en la tabla, así que el criterio con el que se agrupa el
  trabajo estaba en el archivo exportado y no en la pantalla donde se decide qué
  permiso abrir. Va segunda, después del folio y antes de Operadores, con el
  mismo chip de faena que la bandeja de alertas y el panel.
- **"Completado" ya no se ofrece al corregir el estado de un permiso
  (`LV-193`).** `LV-155` retiró ese estado del flujo — *"completado no debe salir
  luego de aprobado; es caducado y final se archiva"* — y el selector de
  corrección se quedó ofreciéndolo, que era la única pantalla capaz de volver a
  escribirlo. Los permisos que ya lo tienen se siguen encontrando con el filtro
  del listado y se pueden corregir hacia otro estado: es retiro de pantalla, no
  de base.
- **El vencimiento de un documento dice de qué cuelga (`LV-186`).** La fila del
  panel decía "Documento · Carta Permiso" y nada más, y hay una carta por
  permiso: para saber a cuál se refería había que abrirla, que es justo lo que
  una lista de vencimientos existe para evitar. Ahora la fila nombra el sujeto
  — "· JEJ-2026-004" — y con eso el chip de faena deja de ser el único camino
  para ubicarlo. Es el único de los cinco orígenes que lo necesitaba: en un
  seguro la etiqueta ya es la matrícula, y en una credencial el nombre de la
  persona. Un documento de empresa cuelga del tenant y no de un registro, y ahí
  la fila queda como estaba: no se le inventa un sujeto.
- **Los enlaces usan el color de la app y no el azul de Bootstrap (`LV-185`).**
  La app nunca había definido su color de enlace, así que todo enlace fuera de
  las columnas de listado salía en el azul por defecto, sin relación con el
  turquesa de la identidad. En claro se usa el paso oscuro (6.44 de contraste)
  porque el base roza el mínimo con 4.53; en oscuro, el base. Medido en ambos
  temas, con guardián contra la deriva entre el hex y su triplete RGB.
- **El encabezado del plan dice de qué tamaño es el área (`LV-183`).** El radio
  vivía sólo al final de la hoja de campo, que sigue el orden del formulario de
  SIGO. Ahora está arriba, junto a la faena y el permiso. Cuando es el círculo
  **envolvente** lo declara —el radio del círculo que cubre un área no es el
  radio del área— y con varias circunferencias dice cuántas en vez de elegir
  una. No se repite dentro de la hoja: hay dos radios en juego y copiar el que
  no era es el error que esa pantalla existe para evitar.
- **La configuración de correo pasa a `MAILERS` (`LV-182`).** Django 6.1 deprecó
  la familia `EMAIL_*` entera, con retiro en 7.0. Se migró **antes** de cargar
  las credenciales, para no configurar dos veces. **Los nombres de las variables
  de entorno no cambian**, así que el archivo de la VM sigue sirviendo tal cual.
- **Django 6.0.8 → 6.1 (`LV-181`).** Los mismos 2284 tests en verde, sin un solo
  cambio en nuestro código. El único bloqueo fue de terceros: Django 6.1 quitó
  `cc_delim_re` y el DRF instalado lo importaba, así que el piso sube a
  `djangorestframework>=3.18`. **El salto avisa que la familia `EMAIL_*` está
  deprecada en favor de `MAILERS`, con retiro en Django 7.0** — el correo
  saliente, que sigue pendiente de configurar, debe apuntar directamente a la
  API nueva.
- **«Geo source» pasa a llamarse «Archivo KMZ/KML de origen» (`LV-180`).** Era
  el único anglicismo entre tipos de documento que nombran papeles reales. Va
  con **migración de datos**: el nombre se fijaba en los `defaults` de un
  `get_or_create`, que sólo se usan al crear, así que la fila de producción se
  habría quedado con el nombre viejo mientras el código decía otro. No pisa un
  nombre puesto a mano. El código `GEO_SOURCE` no cambia.
- **El CI arranca por primera vez (`LV-180`).** Nunca estuvo verde porque
  `${{ runner.temp }}` no existe a nivel de `job`: el workflow abortaba antes de
  correr un solo test. También se limpiaron cuatro ramas viejas — dos mergeadas,
  dos borradas por superadas con su SHA anotado, y las dos que quedan
  documentadas junto al ítem del backlog que implementan.
- **La tipografía dice lo mismo en toda la app (`LV-174`).** La hoja declaraba
  **siete** pesos y el navegador dibujaba **cuatro**: `650` y `750` se dibujan
  exactamente como `700`, y `500` como `600` — medido con la fuente real. De ahí
  la sensación de que el engrosado estaba puesto al azar: lo estaba. Cada peso
  se reemplazó por el que ya se dibujaba, así que **no se movió un píxel**. Los
  tamaños del texto chico pasan de veintiséis valores a cuatro escalones; los
  títulos no se tocaron.
- **La ficha del operador muestra la habilitación como la escribe la DGAC
  (`LV-175`).** El bloque estructurado mostraba tres filas con emisión y
  vencimiento en guion —sembradas desde ese mismo texto libre, sin fechas—, o
  sea afirmaba tres habilitaciones sin respaldar ninguna. Ahora se ve el texto
  literal de la credencial. **No se borró nada**: el subsistema sigue entero y
  sigue alimentando el aviso de compatibilidad operador↔aeronave.
- **La hoja de campo de SIGO gana jerarquía (`LV-171`).** Eran once casillas
  idénticas en peso y color. Ahora el valor —que es lo que se transcribe— manda,
  el rótulo se achica y se aquieta, una casilla vacía deja de gritar, y cada
  tramo lleva un acento lateral con los mismos colores que ya usa el menú.
  Latitud y longitud comparten acento porque son una sola coordenada. **Ningún
  gris se aclaró**: el problema era jerarquía, no contraste.
- **El menú se reparte y se pliega (`LV-170`).** Padrón se llevaba nueve de las
  veinte entradas: se queda con lo que se da de alta una vez y el resto pasa a
  **Inventario y movimientos**, que es otra pregunta —dónde está y quién lo
  tiene— hecha por otra gente. El catastro y el reporte de cumplimiento se
  juntan en **Informes**: estaban separados y por eso se confundían. Los grupos
  ahora se pliegan y **recuerdan** su estado; el de la página actual se abre
  solo, y con la barra en modo icono se muestran siempre, para que un grupo
  plegado no quede inalcanzable. La barra pasa de 248 a 280 px: a 248 se
  cortaban cuatro filas, medido en el navegador.

### Fixed

- **El ID de empleado se deriva del RUT (`LV-169`).** El alta de operador pedía
  el mismo número dos veces: `RUT-192135974` arriba y `19213597-4` tres campos
  más abajo. Ahora se deja en blanco y se rellena solo, y sigue editable. El
  formato es el que el import del Capítulo 1 ya escribía —de hecho ese import
  pasa a usar la misma función, para que no puedan divergir y terminar
  duplicando fichas—. Sólo se rellena si está vacío, y sólo desde un RUT válido:
  de uno inválido saldría un ID inválido y único, basura en la llave del padrón.
  El RUT **no** se vuelve obligatorio. Un ID derivado que choque con otro avisa
  de quién es, en vez del 500 que devolvía antes. Migración `registry.0037`,
  que **no emite SQL**.
- **El guardián de i18n vuelve a coincidir con el extractor.** Exigía que
  estuvieran en el catálogo cadenas que viven dentro de un `{% comment %}`, de
  donde Django no extrae — así que pedía algo imposible. Estaba latente desde
  que `LV-150` retiró "Solicitudes SIGO" del menú comentándola, y sólo se veía
  al regenerar el catálogo, que es el flujo documentado.
- **Las preguntas que enumeran vuelven a leerse como enumeración (`LV-168`).**
  Regresión de `LV-163`: al colapsar los espacios para sacar los saltos que el
  PDF de la DGAC metía a mitad de frase se fueron también los que separaban
  `I.`, `II.`, `III.`, y seis preguntas quedaron como un párrafo corrido. Son
  justo aquellas cuyas opciones son «SÓLO I Y II» contra «SÓLO II Y III», donde
  no ver dónde empieza cada ítem convierte la pregunta en un ejercicio de
  rastreo visual. El corte es **de presentación**: no cambia el texto que se
  corrige ni la copia que el intento archiva, así que los intentos ya rendidos
  también se leen bien. Sigue sin tocarse una palabra ni la caja.
- **El enunciado de la prueba vuelve a estar dentro de su recuadro (`LV-168b`).**
  Un `<legend>` sin flotar se monta sobre el borde del `<fieldset>`: ignora su
  relleno y borra el borde por detrás, así que la pregunta se dibujaba fuera de
  la tarjeta. Con una línea apenas se notaba; con las seis de una pregunta
  enumerada quedaba a la vista. Medido: sin flotar arranca a 0 px del borde de
  la caja, flotado a los 21 que le corresponden. Se conservan el `<fieldset>` y
  el `<legend>` nativos —lo mejor para un lector de pantalla— mudando el flex
  del número a un envoltorio interno.
- **El catastro dice si los papeles están vigentes (`LV-167`).** Dos columnas
  nuevas: vigencia del seguro JAC en la flota y de la credencial DGAC en el
  personal, pintadas con **la misma escala de colores que el panel**. Una fecha
  sin cargar muestra un guion y no se pinta: un nulo es "nunca se ingresó", no
  "está vigente". Se fue la columna «ID de empleado», que repetía el RUT en otro
  formato — queda el RUT, que es lo que se pide cuando alguien pregunta por una
  persona. El PDF pasa a horizontal: con nueve columnas la vertical cortaba la
  matrícula y el número de serie. Con esto el catastro se puede entregar sin
  adjuntar además el reporte de cumplimiento.
- **El permiso deja de pedir lo que el plan ya provee (`LV-166`).** Al editar un
  permiso con un plan geoespacial vinculado, las casillas de región, comuna,
  nombre del área, latitud, longitud y radio desaparecen del formulario: el dato
  sale del KMZ y el formulario dice de qué plan. La ficha las sigue mostrando y
  ahora nombra el plan de origen, con enlace. **Se esconde una casilla sólo si el
  permiso ya tiene ese valor**, no por estar en una lista: un plan con varias
  circunferencias no aporta coordenadas y la altitud máxima no está en ningún
  KMZ, así que esos campos siguen a la vista porque siguen haciendo falta. Y
  queda la puerta para el papel: «Ajustar según la resolución DGAC» los devuelve,
  porque una resolución puede traer otra coordenada y tiene más autoridad que lo
  que se preparó antes de presentar.
- **El contraste de la paleta queda vigilado (`LV-165`).** Se midió el tema
  oscuro contra WCAG AA y **ya cumplía**: el peor par da 5.35:1 contra un mínimo
  de 4.5, y en las pantallas reales no hay un solo texto ni un solo icono por
  debajo del umbral. No se aclaró ningún gris — subirlos los acercaría entre sí
  y la pantalla quedaría **más** plana. Lo que faltaba era el guardián: una
  matriz de los cuatro tokens de texto contra las tres superficies en los dos
  temas, más un test que exige que los tres niveles de gris sigan separados,
  para que un futuro "subamos el contraste" no aplane la jerarquía. De paso
  quedó a la vista que en el tema **claro** el color primario sobre el fondo
  pasa por 0.03 (4.53:1), así que cualquier retoque lo habría roto en silencio.
- **En el catastro el personal arranca en hoja nueva (`LV-164`).** Flota y
  personal son dos padrones de cosas distintas, y en un documento que se entrega
  cada tabla se lee y se firma por separado. Y de paso lo que estaba mal de
  verdad: **ningún encabezado de sección puede quedar huérfano** al pie de una
  hoja con su tabla en la siguiente. Eso vale para los dos informes en PDF, no
  sólo para el catastro — un salto de página puesto a mano acierta con las filas
  de hoy y vuelve a fallar mañana.
- **La prueba de conocimientos se lee (`LV-163`).** Se veía plana porque **todo
  pesaba igual**: la pregunta y las cuatro opciones en negrita, en mayúsculas y a
  todo el ancho de la pantalla. Ahora el único elemento pesado es el número de
  la pregunta, el enunciado tiene ancho de lectura acotado e interlínea holgada,
  y cada opción es una fila clicable que se pinta al elegirla. Se agrega el
  avance —barra y "n / 25"— en un pie fijo junto al botón de enviar, y un aviso
  si quedan preguntas sin responder, que cuentan como incorrectas. Las tres
  reglas (25 preguntas, 80%, 12 meses) pasan de una frase gris a tres datos.
  **Las mayúsculas del banco no se tocan**: vienen del documento de la DGAC y
  llevan METAR, DAN 151, RPA — bajarles la caja cambiaría el sentido de una
  pregunta de examen. Lo único que se normaliza son los saltos de línea que el
  PDF de origen dejó a mitad de frase. Requiere `collectstatic` al desplegar.
- **En Operadores el encabezado "Centro de costo" se salía encima de
  "Habilitaciones" (`LV-162`).** La columna que absorbe el sobrante se le había
  dado al dato más corto —el código de la faena— así que se quedó con 93 px para
  un rótulo de 125, mientras la habilitación, que es texto libre de la DGAC, se
  truncaba en cuatro de cada diez filas. Ahora cada columna pide lo que su dato
  mide y la de texto libre absorbe el sobrante: pasa de 281 a 436 px. Además el
  encabezado de estas tablas envuelve en vez de desbordar, así que la colisión no
  vuelve al angostar la ventana. Requiere `collectstatic` al desplegar.
- **El catastro decía "1 aeronaves" (`LV-161`).** Lo encontró el padrón real el
  día que se desplegó: la flota tiene exactamente una aeronave sin faena, y los
  fixtures de los tests tenían dos o tres de cada cosa. Cada oración lleva dos
  conteos independientes y `ngettext` maneja uno, así que ahora las frases
  contadas se arman por separado y las oraciones las componen. El verbo se queda
  en plural aunque los dos conteos sean 1, que es lo correcto en español con dos
  sujetos unidos por "y".
- **El guardián de i18n no veía las comillas simples (`LV-160`).** Los dos tests
  que existen para que ninguna cadena salga en inglés dentro de la interfaz en
  español sólo miraban literales entre comillas **dobles**, así que las 72 formas
  `{% translate 'Texto' %}` que hay en las plantillas —casi todas dentro de un
  atributo HTML— podían faltar del catálogo sin que nada fallara. Ensanchado el
  escaneo del lado del código, dejando el del `.po` como estaba (gettext quota
  con `"` y nada más). **Resultado: cero cadenas ausentes** — ya estaban todas,
  lo que faltaba era poder comprobarlo. Con un guardián del guardián de 16 casos
  para que el arreglo no pueda regresar en silencio.
- **Un test de baterías fallaba todas las noches desde `R7.2`.** Comparaba la
  fecha de sincronización en UTC contra lo que la plantilla renderiza en hora de
  Santiago, así que entre las 20:00 y la medianoche eran dos días distintos.
  Sobrevivió meses porque el gate rara vez corre en esa ventana; lo delató el
  gate del 2026-08-26 a las 00:17 UTC. Es la misma trampa que
  `apps/compliance/test_reports.py` documenta en su encabezado.

### Added

- **Prueba interna de conocimientos por operador (`LV-158`).** Cada operador rinde
  desde su propia sesión —el resultado se archiva en su ficha, junto a la credencial
  y las habilitaciones— y la revisión dice **en qué se equivocó y cuál era la
  respuesta correcta**, que es lo que sirve para reforzar. 25 preguntas del banco
  propio de 100, 80% para aprobar, y el resultado vale 12 meses: al vencer entra en
  las alertas y en la lista de vencimientos del panel, igual que una credencial. Una
  prueba no se corrige, se rinde de nuevo: el historial de intentos es justamente lo
  que responde cómo está cada profesional. **Despliegue: correr `bootstrap_roles`.**
- **El permiso nuevo trae los datos del plan geoespacial (`LV-153`).** En el alta
  hay un selector "Traer los datos de un plan geoespacial": al guardar, las
  casillas que dejaste en blanco se llenan con lo que dice ese KMZ — punto centro,
  radio, comuna, región y aeródromo más cercano con su distancia— y lo que
  escribiste a mano no se toca. Antes eso sólo pasaba al vincular un plan **desde
  la ficha del permiso ya creado**, así que al darlo de alta las ocho casillas se
  tipeaban con el KMZ delante. Se elige un plan ya subido, no se sube un archivo.
- **Botón "Guardar borrador" en el permiso (`LV-154`).** El formulario más largo de
  la app ya no es todo o nada: se puede dejar a medio llenar, salir, y al volver un
  aviso ofrece recuperar lo tipeado (con su fecha y hora) o descartarlo. Guardar el
  permiso de verdad borra el borrador. **Queda en ese navegador y nadie más lo ve**,
  y la pantalla lo dice: un borrador de verdad en la base habría exigido admitir
  permisos sin centro de costo, sin propósito y sin tipo de área, y decidir qué
  hacen con ellos el panel, las alertas, el calendario y el informe.

### Changed

- **El clima del panel: ahora eliges la ubicación (`LV-147`).** Un desplegable en
  la tarjeta ofrece los permisos vigentes y las faenas con coordenadas en ficha;
  el automático sigue siendo el próximo vuelo. El título cambia con lo elegido, así
  que "el clima donde vuelas ahora" dice la verdad — antes también lo decía cuando
  el pronóstico venía de una faena y no de ningún vuelo. Elegir ubicación no pierde
  el filtro por centro de costo, ni al revés. Sigue siendo una sola consulta al
  proveedor por carga de página, y la tarjeta ya no desaparece cuando el proveedor
  no responde: ahí es donde está el selector para probar otra ubicación.
- **El panel se ordena por lo que hay que hacer (`LV-148`).** Primero "¿podemos
  operar hoy?", después el trabajo pendiente, después la lista de vencimientos, y
  el clima más abajo — donde se consulta antes de volar, no al abrir sesión. Se van
  "Aeronaves activas" y "Operadores activos": eran el denominador de la tira de
  abajo dicho dos veces, y sus enlaces siguen en las tarjetas de flota y
  credenciales. Y el mismo tramo de urgencia se pinta igual en las dos pantallas:
  "vence en 30 días" era azul en la bandeja y ámbar en el panel.

- **La línea del permiso es solicitado → aprobado → caducado → archivado
  (`LV-155`).** "Completar" sale de la ficha: un permiso aprobado ya no tiene un
  botón de siguiente paso, caduca solo cuando se cierra su vigencia y de ahí se
  archiva. **Nada se borra**: el estado sigue existiendo para las filas que ya lo
  tienen y el filtro del listado lo sigue ofreciendo, así que los permisos con el
  período ya terminado se encuentran igual. Un permiso completado de antes muestra
  en su ficha hasta dónde llegó, no un flujo sin empezar.

### Fixed

- **Subir la Resolución de la JAC ya arregla la póliza "vencida" (`LV-159`).** La
  ficha de una aeronave decía "Póliza en ficha vigente hasta el 2026-08-08 ·
  Vencida" teniendo adjunta, dos secciones más abajo, la Resolución Exenta que la
  aprueba hasta 2027-08-24: nadie llevaba la fecha del papel al campo. Ahora la
  resolución manda —es el verificador de que la aeronave está autorizada hoy— y
  al cargarla la ficha toma su vigencia y queda como póliza vigente, con el salto
  registrado en el historial del trámite. No tira la fecha hacia atrás con un
  papel viejo, no reacciona a otros documentos y no cruza aeronaves. **Despliegue:
  correr `manage.py sync_jac_insurance` (primero sin `--apply`)** para las
  resoluciones que ya están cargadas — la señal sólo actúa al guardar.
- **Cada fila dice a qué centro de costo pertenece, y la bandeja se puede filtrar
  por faena (`LV-146`).** En las alertas el código va como chip bajo el nombre de
  la entidad; en los vencimientos del panel, al principio de la fila, con un guion
  cuando el registro no tiene faena asignada. El selector de faena de la bandeja
  reusa el mismo resolvedor que el filtro del panel, así que la columna y el filtro
  no pueden contradecirse. El CSV de alertas, que exportaba un nombre de tabla y un
  UUID en vez del registro, pasa a doce columnas legibles que empiezan por faena y
  entidad. Los documentos ahora respetan el filtro por faena: antes elegir un
  centro de costo recortaba las otras cuatro fuentes y dejaba los documentos de las
  demás faenas en la lista. **Despliegue: correr `bootstrap_roles`** — Operations,
  Compliance y Maintenance necesitan leer el padrón de faenas para que el filtro les
  aparezca (el del calendario ya estaba vacío para ellos sin que nadie lo notara).
- **El panel ya no se cae con un filtro mal escrito en la URL (`LV-146`).**
  `?cost_center=abc` era un error 500: un valor que no es UUID revienta dentro de
  la consulta, y eso no lo cubría el "filtro que no resuelve es un no-op".
- **Un permiso no puede nacer aprobado sin la autorización de la DGAC
  (`LV-157`).** La regla existía desde `LV-64` pero sólo en el botón de aprobar,
  y `Estado` es un campo del formulario de alta: crear el permiso eligiendo
  "Aprobado" en el desplegable lo dejaba aprobado sin pasar nunca por la
  compuerta — y en el alta esa compuerta no se puede cumplir, porque no hay dónde
  adjuntar un documento a un permiso que todavía no existe. El alta ahora ofrece
  sólo "Solicitado" y "Denegado"; aprobar es siempre la transición guardada. Es la
  misma puerta trasera que `LV-101` cerró en la pantalla de edición.
- **Aprobar exige el número de la DGAC (`LV-156`).** La regla "un permiso aprobado
  necesita su número" vivía sólo en el formulario, y el botón que aprueba de verdad
  no la comprobaba: de ahí un permiso aprobado —y luego completado— que la lista
  mostraba como `DGAC: En proceso`. Ahora se rechaza con un mensaje que dice de
  dónde sale el número, y el campo explica que es el folio de la autorización
  firmada. No se lee del PDF: eso exigiría una dependencia de parseo que el
  proyecto no tiene, y con el papel en pantalla el número es un teclazo — lo que
  faltaba era que nadie pudiera saltárselo.
- **El roster del permiso se puede buscar, y ofrece sólo lo que puede volar
  (`LV-151`).** Los 41 operadores y las 16 aeronaves se ofrecían **en el orden en
  que la base devolvía las filas** —ni `Operator` ni `Aircraft` declaran orden— y
  sin filtrar lo archivado, así que un operador archivado y una aeronave retirada
  seguían apareciendo en un permiso nuevo. Ahora van en orden (nombre y matrícula),
  con un buscador que filtra las casillas en vivo, un contador de elegidas y un
  "sólo los elegidos" para verlas juntas. Busca sin tildes. Lo que el permiso ya
  eligió se conserva aunque hoy no calificaría: si una aeronave se retira después,
  sacarla del roster la habría borrado del permiso al guardar. El formulario, de
  paso, queda agrupado en cinco tramos en vez de diecisiete campos en una columna.
- **La columna "Habilitación" del padrón deja de decir "Vigente" para todos
  (`LV-152`).** Contaba como vigente toda habilitación con vencimiento vacío — o
  sea todas las que entraron por el import—, así que casi todo el padrón salía en
  verde con un dato que nadie había ingresado. Ahora la columna muestra la
  habilitación **tal como la dice la DGAC**, en texto libre, y ese campo subió en
  el formulario a donde se lo busca: justo después de la credencial. No se
  estandariza a propósito: la redacción varía.
- **Un duplicado avisa quién tiene el valor, en vez de devolver 500 (`LV-142`).**
  Tres caminos morían con `IntegrityError` y sin mensaje: el número de empleado de
  un operador, el código de un centro de costo —los dos porque su restricción de
  unicidad incluye el tenant, que no está en el formulario, y Django omite la
  restricción entera cuando alguno de sus campos falta— y el número de serie de una
  aeronave, que se normalizaba **después** de validar, así que `1581f5 fhc245`
  pasaba el formulario y reventaba contra `1581F5FHC245`. Ahora el error sale por
  el campo, nombra el registro que ya lo tiene, dice si está archivado y ofrece su
  ficha cuando quien mira puede leerla. La matrícula además se guarda y se compara
  en mayúsculas: `rpa-7126` y `RPA-7126` eran dos aeronaves distintas para la base.
  Sin migración: las 16 aeronaves de producción ya están en mayúsculas.
- **El RUT del operador se valida y se compara (`LV-143`).** Se guarda en una sola
  forma (`12345678-K`, sin puntos), se comprueba el dígito verificador y se avisa
  si otro operador de la misma organización ya lo tiene. Antes admitía cualquier
  texto y dos fichas de la misma persona con el RUT escrito distinto eran dos
  personas para la app. **Sin restricción de base de datos y sólo cuando el valor
  cambia**: en producción hay duplicados que vinieron del import del Capítulo 1, y
  exigir un RUT válido para guardar cualquier edición habría dejado esas fichas
  congeladas. Se resuelven con `find_duplicate_operators --apply`.

### Added

- **El KMZ entrega sus datos apenas se sube, sin separarlo (`R10.1`).** La
  ficha del plan geoespacial trae ahora **"Datos para SIGO"**: el punto centro
  en grados, minutos y segundos, el radio en metros, y el **aeródromo más
  cercano con su distancia en kilómetros**. Antes esa información sólo aparecía
  al **separar** el plan en solicitudes, así que un archivo con una sola
  circunferencia —el caso normal— tenía que pasar por una acción pensada para
  el excepcional. **Separar queda para lo que es**: el botón sólo aparece cuando
  hay más de una circunferencia, y dice cuántas.
- **Un plan ya subido se puede cruzar con su permiso (`R10.2`).** La ficha del
  permiso sólo dejaba **importar** un KMZ nuevo; ahora también se puede vincular
  uno que ya está en la app. Al vincularlo, **el plan rellena la ubicación del
  permiso** —coordenadas, radio y nombre del área— y dice exactamente qué
  rellenó. Nunca pisa lo que ya estuviera escrito: si el permiso trae una
  coordenada del papel DGAC, esa manda. Y el historial del vínculo ya registra
  **quién** lo hizo.
- **El Capítulo 1 del manual se puede cargar de nuevo sin duplicar nada
  (`LV-133`, `LV-134`).** La **Rev 17** dejó de numerar las fichas de dotación y
  el importador la leía como un archivo vacío — decía "no se extrajo ningún
  operador" sobre un documento con 48. Corregido, y verificado contra el archivo
  real: 17 aeronaves y 48 operadores. Y ahora **agrega sólo lo que falta**
  (`--skip-existing`): lo que ya está en la base se salta y se informa, sin
  tocarlo. Si una serie ya existe bajo otra matrícula, la corrida se detiene y lo
  nombra: eso no es un registro nuevo, es la misma aeronave con dos datos que no
  coinciden.
- **Una sola fila por circunferencia (`LV-132`).** `R10.8` mostraba la
  circunferencia envolvente **al lado** de la dibujada, y en un área casi
  circular eso se leía como el mismo dato dos veces — con el riesgo de mezclar el
  centro de una con el radio de la otra, que es la combinación que **no** cubre
  el área. Ahora la fila muestra directamente lo que se puede declarar, y el
  radio promedio de lo dibujado queda como referencia en chico.
- **El plan entrega la comuna, la provincia y la región del punto central
  (`LV-141`).** SIGO pide la comuna como casilla propia y hasta ahora se tipeaba a
  mano con el KMZ delante. Sale de los **límites oficiales de la Biblioteca del
  Congreso Nacional**, que viajan con la app (no se consulta ningún servicio
  externo). Verificado contra las faenas reales: los siete KMZ de CC 738 dan
  Salamanca / Choapa / Coquimbo, El Mauro da Los Vilos, Talabre da **Calama**.
  Como el aeródromo más cercano, **se propone y se confirma**: la BCN publica su
  cartografía como referencial, así que cerca de un límite la respuesta puede ser
  la comuna vecina, y la pantalla lo dice.
- **Cada plan geoespacial tiene su número: `PG-2026-001` (`LV-138`).** El título
  hacía de identificador y venía en dos formas distintas según cómo se hubiera
  importado el plan, así que no se podía citar ni ordenar. Ahora el número va en
  su **propia columna** —correlativo anual, como el folio del permiso— y el título
  vuelve a ser el comentario: el código del centro de costo y el nombre del KMZ.
  Los planes que ya existían reciben su número en orden de creación. Requiere la
  migración `geo/0005`.
- **El permiso guarda el aeródromo más cercano y su distancia (`LV-137`).** El plan
  geoespacial los calcula y la solicitud SIGO los guardaba, pero el permiso —la
  ficha donde uno consulta el trámite— los perdía en el camino: había que volver
  al plan para saber qué se declaró. Al vincular un plan, ahora también llegan
  esos dos datos. Y el expediente **ya no manda a importar un KMZ nuevo**: ofrece
  vincular el plan que ya existe en la app, que es el que trae la información —
  importar queda para cuando de verdad no hay ninguno en esa faena. Requiere la
  migración `operations/0021`.
- **La pestaña Flota dice qué aeronave es (`LV-139`).** Mostraba la matrícula pero
  no el modelo ni el número de serie, y con cuatro Matrice 4 Enterprise en la
  flota eso no identifica el equipo que está en faena.
- **Se puede archivar un plan o un permiso, con doble verificador (`LV-135`).**
  No había ninguna forma de sacar un plan o un permiso de la lista: la única
  salida era el admin de Django. Ahora se **archivan** —no se borran: la fila
  sigue ahí y vuelve con "Restaurar"— y antes de hacerlo la app muestra **qué
  cuelga**: para un plan, las solicitudes SIGO nacidas de él y cuántas ya están
  presentadas; para un permiso, sus vuelos, planes, documentos y solicitudes.
  Nada se archiva en cascada. Y un permiso **ya aprobado por la autoridad** exige
  un motivo escrito que queda en la auditoría con tu nombre y la fecha.
- **El mapa usa la pantalla que tiene, y se puede ampliar (`LV-136`).** Medía 480
  píxeles fijos, así que en un monitor grande sobraba la mitad del alto y dibujar
  era arrastrar el lienzo en vez de mirarlo. Ahora **crece con la ventana**, y el
  botón **"Ampliar"** le da la pantalla completa para trabajar — con `Escape` para
  volver. Es la misma tarjeta ocupando todo, no un mapa aparte: los controles de
  dibujo, las capas y "Guardar" son los mismos, así que no hay dos editores que
  puedan quedar diciendo cosas distintas.
- **El listado de planes gana filtros (`LV-135`).** Era la única lista de la app
  sin ninguno: ahora busca por título y centro de costo, filtra por estado y deja
  ver lo archivado. Los dos listados muestran **lo vigente por defecto**.
- **Un área que no es circunferencia ya trae la que hay que declarar (`R10.8`).**
  SIGO acepta una circunferencia con su punto central por solicitud, y la mayoría
  de las áreas reales son polígonos a mano alzada: la app avisaba y dejaba el
  trabajo de sacar centro y radio en Google Earth. La ficha del plan agrega ahora
  una fila **"↳ la circunferencia más chica que la encierra"**, con sus mismas
  cinco casillas y **su propio aeródromo más cercano** —porque la distancia se
  mide desde el centro que se va a declarar—. Es la circunferencia **mínima**, no
  una aproximación: un radio de más pide espacio aéreo que después hay que
  justificar. Sobre un círculo no aparece nada, y la solicitud sigue naciendo con
  lo dibujado: cambiar lo que se presenta al Estado es decisión tuya.
- **El aeródromo más cercano se calcula sobre 15 posiciones, no 6 (`R10.7`).** El
  catálogo copiado del selector de SIGO traía los nombres pero casi ninguna
  coordenada, así que "el más cercano" se elegía entre seis. Las posiciones ahora
  vienen del **AIP de la DGAC**, cruzadas por designador OACI, y de paso
  corrigieron dos que estaban movidas (`SCEL` 737 m, `SCBA` 417 m). **No se
  agregaron aeródromos nuevos**: la casilla de SIGO sólo acepta lo que su propio
  selector ofrece, así que el AMC que la app propone es el más cercano **entre
  esos**, y para mejorarlo hay que capturar el resto del selector. Requiere
  correr `manage.py import_aip_aerodromes` una vez.
- **El plan geoespacial y la solicitud SIGO reciben documentos (`R10.5`).** Los
  papeles llegan **antes** que el permiso —el KMZ del cliente, el correo que pide
  el vuelo, la carta AIP con la que se confirmó el aeródromo, la constancia de lo
  presentado en SIGO— y hasta ahora el único registro del que se podían colgar
  era el permiso, que en esa etapa todavía no existe. Es la misma sección de
  documentos que ya llevan la aeronave, el operador, el centro de costo y el
  permiso: agrupada por categoría, con **Ver** sin salir de la ficha. Sin
  migración.

### Changed

- **Los iconos del menú dejan de repetirse (`R10.3`).** Cuatro pares se veían
  iguales — *Operadores* con *Asignaciones de operador*, *Aeronaves* con
  *Asignaciones de aeronave*, *Permisos* con *Mantenciones*, y las dos entradas
  de administración. Las asignaciones conservan su sujeto (la persona, el dron)
  y ganan una **flecha** común que las identifica como asignación; Mantención
  pasa a una llave inglesa y el centro de administración a un medidor.
- **Los documentos del permiso se ven como en el resto de la app (`R10.6`).** La
  ficha del permiso de vuelo armaba su bloque "Documentos" con marcado propio,
  anterior a la sección compartida que usan la aeronave, el operador y el centro
  de costo — y por eso era la única que se había quedado sin la **agrupación por
  categoría**, sin **"Subir varios"** y sin el **"Ver"** que abre el PDF sobre la
  ficha en vez de bajarlo al disco. Justamente la ficha donde más papeles se
  juntan: carta a la DGAC, autorización de operación, resolución de la JAC,
  correspondencia. Ahora es la misma sección, una sola vez.
- **La bandeja de alertas abre en lo que hay que hacer (`LV-118`).** Abría
  mostrando **todo**, resuelto incluido, así que la pantalla de trabajo diario
  mezclaba los pendientes con el historial. Ahora abre en **"Sin resolver"** y
  ordena por urgencia —lo vencido hace meses arriba, no lo que vence en 30
  días—, con el color de cada fila bajando de intensidad según el tramo. Lo
  resuelto **no se borró ni se escondió**: sigue a un clic en el filtro, que es
  donde corresponde para una evidencia de auditoría.

### Fixed

- **El expediente del permiso ahora lleva a resolver lo que falta (`LV-130`).**
  Decía "faltan cuatro cosas" y ahí terminaba: cerrar cada una exigía saber dónde
  se cierra. Cada renglón pendiente trae ahora **el atajo que lo cierra** — el
  formulario de carga con el tipo de documento ya elegido, la ficha de la
  aeronave o del operador cuya vigencia falta, la del plan al que le falta la
  revisión meteorológica, el formulario de vuelo con el permiso puesto. Si son
  varios los registros que fallan, el atajo lleva al listado y no al primero, y
  no se ofrece nunca un atajo que tu usuario no pueda ejecutar.
- **"Solicitudes SIGO" ya no te manda al listado de planes (`LV-131`).** El botón
  "Separar un plan" del encabezado no separaba nada: era navegación con cara de
  acción, y desde que el KMZ entrega sus datos solo, separar sirve únicamente
  cuando el archivo trae más de una circunferencia. En su lugar la pantalla dice
  para qué es —**lo presentado en SIGO y cuánto lleva esperando**— y el estado
  vacío explica de dónde nacen las solicitudes, con el enlace ahí.
- **Un KMZ de Trimble ya no se lee como "sin círculo" (`R10.4`).** Los archivos
  que exporta **Trimble Business Center** dibujan la circunferencia como un
  trazado cerrado y no como un polígono, y la app sólo miraba polígonos: siete
  KMZ reales de una faena —con su círculo perfectamente dibujado— salían **sin
  radio y con un aviso de "sin círculo" que era falso**, así que no había nada
  que llevar a SIGO. Ahora cuenta como circunferencia cualquier anillo cerrado,
  venga como polígono o como trazado. Un trazado **abierto** se sigue ignorando a
  propósito: es un camino, no un área, y tomarlo por área convertiría una ruta en
  una circunferencia de vuelo. La comprobación de que el anillo sea realmente
  redondo no cambió.
- **El panel deja de dar cinco respuestas a la misma pregunta (`LV-129`).**
  Seis lugares hablaban de vigencias con números que no cuadraban entre sí.
  Ahora **"vencidos" quiere decir lo mismo en todas partes**: los que aparecen
  en seguros y credenciales suman exactamente los de la tarjeta de
  vencimientos. Lo que antes iba sumado como *"faltantes o vencidos"* se separa
  en **vencidos** y **sin fecha cargada**, que son dos trabajos distintos — y el
  segundo es el que ninguna alerta va a recordarte, porque una vigencia que
  nadie cargó no vence. Las dos tarjetas de vencimientos se funden en una, con
  el desglose debajo, y la sección enlaza a la bandeja de alertas en vez de
  traerse su filtro: ahí es donde se resuelve con motivo y queda historial.
  Además, **"Alertas pendientes" ya respeta el filtro por centro de costo** —
  antes elegir una faena cambiaba todas las tarjetas menos ésa.
- **El registro DGAC de una aeronave ya se puede subir (`LV-121`).** El tipo
  "Registro / matrícula de aeronave" exigía una fecha de vencimiento, pero el
  certificado que emite la DGAC **no la trae** — es una inscripción, no una
  vigencia. Había que inventar un vencimiento para poder adjuntar el PDF, y esa
  fecha inventada terminaba generando una alerta por algo que no caduca. Ahora
  el tipo no la pide. Los tipos que sí vencen (seguros, credenciales,
  resoluciones) la siguen exigiendo igual.
- **El panel ya no arrastra lo que se resolvió (`LV-122`).** Al empezar a
  mostrar lo vencido, empezó también a mostrar lo vencido **que alguien ya
  revisó y cerró** — como una credencial resuelta con el motivo "fuera de CC con
  operación RPA", que se quedaba ahí para siempre porque esa fecha ya no cambia.
  La lista sólo podía crecer. Ahora una fila desaparece del panel cuando su
  alerta se resuelve, y **vuelve sola si el documento se renueva**: la
  vigencia siguiente es un caso nuevo, no el mismo resuelto otra vez.
- **El panel escondía lo ya vencido (`LV-120`).** La sección de vencimientos
  listaba sólo lo que está por vencer, así que un seguro que caducó hace un mes
  —o tres— no aparecía en ninguna parte del Panel de operaciones, aunque su
  alerta sí estuviera en la bandeja. Ahora **lo vencido va primero**, en rojo, y
  tiene su propia tarjeta de conteo al lado de "Vence en 30 días", que sigue
  contando sólo el futuro. La sección pasa a llamarse **Vencimientos**: seguía
  diciendo "próximos" mientras mostraba el pasado. Lo que ya no aparece es lo
  que tampoco genera alerta —una aeronave dada de baja, un permiso caducado y
  cerrado—, con la misma regla que usa el motor de alertas, para que el panel y
  la bandeja no puedan contradecirse.
- **Una alerta resuelta decía mal por qué se había levantado (`LV-118`).**
  Mostraba el vencimiento que el registro tiene **hoy**, no el que la disparó:
  dos alertas de una aeronave, levantadas porque su póliza había vencido en
  agosto, aparecían diciendo "vencimiento 2027-08-04" después de que alguien
  renovara el seguro. Para un auditor eso es una alerta levantada por una
  vigencia del año siguiente, o sea nada. Ahora cada fila conserva la fecha que
  la originó.
- **El trabajo diario avisa si quedan alertas repetidas (`LV-118`).** Desde
  `LV-111` el sistema ya no crea dos alertas del mismo caso, pero no decía nada
  de las que habían quedado escritas antes — se descubrieron mirando la
  pantalla. Ahora la corrida de las 06:00 las nombra. No borra ni resuelve
  ninguna: sólo deja de depender de que alguien las vea.

### Added

- **La solicitud de seguro a la JAC tiene dónde guardarse (`LV-121`).** Faltaba
  la mitad que **va**: el formulario que se manda a la JAC pidiendo la
  aprobación del seguro. Con sólo la resolución que vuelve, la carpeta de una
  aeronave no podía mostrar que un trámite está **presentado y esperando** —
  que es justamente uno de los cuatro estados que el seguro tiene en la ficha.
  Mismo par que ya existe para la DGAC: la carta que va, la autorización que
  vuelve.
- **La Resolución Exenta de la JAC ya tiene dónde guardarse (`LV-117`).** El
  catálogo tenía la póliza y su certificado, pero no **el papel con que la JAC
  aprueba el seguro** —el que deja a la aeronave como *autorizada*—, así que no
  había forma de adjuntarlo al historial de la aeronave. Nuevo tipo
  **"Resolución Exenta JAC (aprueba seguro RPA)"**, en el grupo *Documentos de
  la aeronave* (al lado del seguro, que es de lo que habla, y no entre las
  presentaciones DGAC: la JAC es otro organismo) y **con vencimiento**, porque
  la resolución trae término de vigencia y caduca con la póliza — la alerta de
  documentos por vencer la vigila sin configurar nada. **No** reemplaza la
  vigencia del seguro de la ficha: esa fecha sigue siendo la de la aeronave, y
  cargar el PDF no la actualiza sola.

- **Los documentos se ven y se cargan mejor (`LV-84`, `LV-85`, `LV-86`).** El
  listado de una ficha ahora dice emisión, vencimiento (con aviso si ya venció) y
  si esa versión fue reemplazada, y cada fila lleva **Ver** y **Descargar** al
  lado. **Ver abre el documento dentro de la página** —PDF e imágenes— con el
  visor del propio navegador, sin traer nada de afuera. Y se pueden **subir
  varios archivos de una vez** contra el mismo registro: si uno no sirve, el
  aviso dice cuál y no se carga ninguno a medias.
- **Los permisos vencidos se cierran solos (`LV-83`).** Un trabajo diario marca
  como **Caducado** todo permiso cuya vigencia terminó y que seguía en
  *Solicitado* o *Aprobado*, conservando entero su historial. **Caducado no es
  Completado**: completar significa que se voló lo autorizado y que está el PDF
  firmado de la DGAC, mientras que caducar sólo significa que se acabó el plazo
  — y un permiso puede caducar sin haber volado nunca. La barra de estado
  muestra hasta dónde llegó antes de cerrarse, así que un permiso caducado que
  había sido aprobado sigue mostrando que la DGAC lo autorizó.
- **Trazabilidad visible en mantención (`LV-82`).** La ficha de una mantención
  muestra ahora la misma barra de estado que el permiso y el seguro, **con el
  camino que ese registro realmente tomó**: el corto cuando se resuelve en casa,
  y la cadena completa de taller cuando el equipo sale. El historial pasa a
  decir los estados **en español** (antes mostraba los códigos internos como
  `at_workshop`) y **en qué rol** actuó cada persona.
- **El seguro JAC con su ciclo real y su trazabilidad (`LV-81`).** El estado del
  seguro deja de ser "en trámite o vigente" y pasa a los cuatro pasos que existen
  de verdad: **faltante o por renovar → en trámite → presentado en SIGO,
  esperando la JAC → póliza vigente**, con la **misma barra de estado y el mismo
  historial** que ya tiene el permiso de vuelo (quién movió cada paso, en qué
  rol y cuándo). Con esto, un seguro comprado y esperando la autorización de la
  JAC deja de verse igual que una aeronave sin seguro — en la ficha y en la
  lista de aeronaves. **Se puede registrar una renovación** sin perder la
  vigencia de la póliza actual, que antes era imposible. Marcar "la JAC lo
  autorizó" ahora **exige la fecha de vigencia**, para que el estado de la app no
  se adelante al papel. Las aeronaves que decían "vigente" sin ninguna fecha
  quedan corregidas a "faltante" al migrar.
- **El clima, en el panel y con temperatura (`R8.4`).** El pronóstico deja de
  estar sólo en la ficha de un plan geoespacial: el panel muestra el clima del
  **próximo vuelo**, tomando las coordenadas del propio permiso. Ahora incluye
  **temperatura** máxima y mínima y un **icono de la condición real del día**
  (despejado, nublado, lluvia, nieve…), y el **viento va en m/s**, la misma
  unidad en que el fabricante publica la resistencia al viento del equipo. El
  filtro por centro de costo que ya tenía el panel **cambia la ubicación** del
  pronóstico, para lo cual el centro de costo pasa a tener coordenadas de faena
  (opcionales). Sigue siendo **una sola llamada cacheada por página**, y la
  tarjeta simplemente no aparece cuando no hay ubicación en ficha o el proveedor
  no responde.
- **Ubicación estructurada en el permiso de vuelo (`OPS-4`, diferido en su
  momento).** Región, comuna y nombre del área, más un par de coordenadas
  opcional con radio y altitud máxima. **Complementa** el campo de texto libre,
  que conserva la redacción exacta de la autorización DGAC; todo opcional, así
  que un permiso antiguo cuyo papel sólo decía "Chuquicamata" no queda
  retroactivamente incompleto. Un punto a medio ingresar (latitud sin longitud)
  se rechaza: no se puede dibujar en un mapa y fallaría en silencio.
- **Iconos en el pronóstico meteorológico (`R8.3`).** Viento, ráfagas,
  precipitación y probabilidad de lluvia se distinguen de un vistazo.
- **La unión con AeroLink funciona de punta a punta (`X.4d`).** El endpoint que
  faltaba está implementado en el repo de AeroLink (pendiente de PR) y verificado:
  AeroControl sincroniza las baterías **contra el servicio real**, enlazándolas a
  su aeronave por número de serie.
- **Sincronización del inventario de baterías desde AeroLink (`X.4b`).** El
  comando `sync_batteries` llena la tabla de baterías (ciclos, salud, firmware)
  que hasta ahora estaba vacía a propósito, enlazando cada una a su aeronave por
  número de serie. Se puede probar hoy con `--from-file`, antes de que AeroLink
  publique su endpoint; el contrato quedó escrito en el ADR-0002.
- **Trazabilidad también en el plan geoespacial (`LV-72`).** El mismo bloque que
  el permiso, porque un plan también avanza por revisión. La ficha de aeronave
  no lo lleva: su estado va y vuelve entre activa y mantención, que no es un
  avance.
- **Trazabilidad del permiso al estilo SIGO (`LV-72`).** La ficha del permiso
  abre con el avance del trámite en pasos y, debajo, el historial numerado con
  **acción, usuario, rol, fecha y notas** — la misma forma que los operadores ya
  leen en el sistema de la DGAC, y el orden en que un auditor pide la evidencia.
  Sin datos nuevos: el historial ya se registraba, faltaba mostrarlo así.
- **Los 5 indicadores operacionales que pide la guía ISO (`R7.7b`).** A los dos
  que ya estaban se suman precisión de los levantamientos, tasa de re-vuelos y
  horas de vuelo sin incidentes, que dependían de las dos funciones nuevas de
  esta misma tanda.
- **No conformidades (`R7.6b`, ISO 10.2).** Registro de re-vuelos, entregables
  rechazados, incidentes y hallazgos de auditoría, con causa raíz, acción
  correctiva y verificación de eficacia a los 30 días. **Cerrar exige la causa y
  la acción**; y **rechazar un entregable abre la no conformidad solo**, que era
  el disparador que faltaba. Incluye el reporte a la DGAC (fecha y folio) para
  los eventos que exigen notificar a la autoridad.
- **Control de calidad del entregable (`R7.4`, ISO 9001 8.5.1/8.6).** Registro de
  GSD y RMSE logrados **contra los requeridos por el contrato**, con validación
  interna firmada antes de liberar. Liberar por debajo del criterio acordado
  exige un motivo escrito, que queda visible. Los umbrales se cargan en la ficha
  del centro de costo: **un contrato sin umbrales no impone ningún control**, y
  sus entregables quedan "sin evaluar" en vez de juzgarse contra un número
  inventado.
- **Indicadores operacionales en el reporte (`R7.7a`, ISO 9001 9.1.1).**
  Disponibilidad de flota (meta 90%) y cumplimiento de plazos, con valor, meta y
  estado. Sin datos nuevos.
- **Límite de jornada de vuelo (`R7.5a`, ISO 45001).** Aviso al registrar un
  vuelo que lleva al piloto sobre las **8 horas** del día, y un reporte diario de
  los excesos de la jornada anterior. Avisa, nunca rechaza: el registro se
  escribe después del vuelo, y negarlo sólo perdería la evidencia.
- **Verificación de eficacia de las acciones correctivas (`R7.6a`, ISO 10.2).**
  Resolver una alerta dejaba de ser el final: a los **30 días** el sistema
  pregunta si la acción realmente sirvió, y escala a Dirección lo que nadie
  confirmó. La confirmación la hace una persona; el trabajo programado sólo
  persigue lo pendiente.
- **La revisión meteorológica queda registrada como evidencia (`R8.2`, ISO 8.1).**
  Hasta ahora el pronóstico se mostraba y se perdía: no había forma de acreditar
  que se revisó el clima antes de volar, y un pronóstico **no se puede consultar
  de nuevo después** (el proveedor responde otra corrida del modelo, o rechaza la
  fecha pasada). Ahora se guardan los valores tal como se leyeron, con sus
  unidades, por acción explícita de una persona.
- **Filtro por tipo de entidad en la lista de alertas (`LV-76`).** La vista ya
  filtraba por tipo, pero no había forma de usarlo desde la pantalla.
- **Exportación CSV donde faltaba.** Log de auditoría, usuarios y roles, planes
  geoespaciales, documentos de la empresa y registros operacionales. El log de
  movimientos exporta la **etiqueta** del recurso, no el UUID crudo.

### Changed

- **El logo pasa a ser de la misma familia que AeroLink y AeroPlanner.** Las tres
  aplicaciones hermanas ya compartían un mismo dron dibujado igual —mismos
  brazos, mismos cuatro rotores, mismo fuselaje— y cambiaban sólo el motivo de
  abajo, que dice a qué se dedica cada una. El de AeroControl era otro dron: más
  grande, con otra geometría, ocupando todo el lienzo, y por eso desentonaba
  puesto al lado de los otros dos. Ahora usa el dron común y su motivo propio es
  **un escudo con un visto bueno**, que es de lo que trata la aplicación:
  conformidad y control. **El color no cambia**: sigue siendo el turquesa
  `#2EC4B6` de siempre.
- **El README dice en qué versión estamos y con quién convive.** Declaraba
  `v0.4.0-beta` y 709 pruebas cuando ya se había cerrado `0.5.0-beta` y hay
  1440; ambos números quedan corregidos. Además incorpora la sección
  **Aplicaciones hermanas**, que hasta ahora no existía en ninguna parte del
  README: qué hace AeroPlanner, qué hace AeroLink, por dónde se comunican con
  AeroControl y —sobre todo— que **son independientes y no comparten base de
  datos**.
- **La pantalla para subir documentos, ordenada (`LV-95`).** El selector de tipo
  de documento deja de ser una lista plana de dieciocho nombres y queda
  **agrupado**: documentos del personal, de la aeronave, presentaciones y
  autorizaciones DGAC, registros operacionales, mantención y calibración, y
  documentos de la empresa. El orden anterior no era orden — era el orden en que
  se habían creado. El formulario, además, pregunta en el orden en que se
  trabaja: **a qué pertenece → qué documento es → el archivo → su vigencia**, y
  recién al final lo opcional; el **título pasó al final**, porque se genera solo
  a partir de las tres primeras respuestas y antes abría la pantalla pidiendo
  algo que todavía no se podía contestar. Los tipos que ya existían quedan
  clasificados solos al actualizar; al crear un tipo nuevo, la categoría se elige
  ahí mismo.
- **El panel responde "¿puedo operar hoy?" (`LV-89`).** Los dos gráficos que
  ocupaban un tercio de la pantalla para repetir números que ya estaban arriba
  se reemplazan por **tres indicadores**: flota disponible (con su meta del 90%),
  seguros al día y credenciales al día — cada uno con **cuántos faltan**, no sólo
  el porcentaje, y cada uno clickeable hacia la lista que hay que arreglar. El
  encabezado queda con un solo botón, "+ Nuevo permiso": los otros dos repetían
  el menú lateral, y uno de ellos decía "Abrir registro" y llevaba a centros de
  costo. La tarjeta de clima suma la **ventana de luz diurna** y el índice UV,
  que no cuestan una consulta extra y sí importan: tu póliza cubre **jornada
  diurna**.
- **El tablero Kanban dejó de aparecer donde todavía asomaba (`LV-78`).** Se dio
  de baja el 2026-08-12, pero seguía dibujándose en el **panel** (un gráfico de
  sus etapas, todos los días), en el **calendario**, en el **buscador** y en el
  **centro de administración**. Ninguna de esas pantallas llevaba a ningún lado,
  porque el tablero ya no está en el menú. Además se quitaron las dos formas de
  **reencenderlo sin querer**: el formulario de reglas de alerta ya no ofrece
  crear tarjetas automáticas, y el procedimiento de despliegue ya no incluye el
  comando que recrea el tablero. **No se borró nada**: el tablero y sus datos
  siguen ahí, sólo dejó de mostrarse y de poder encenderse solo.
- **Dos listas más fáciles de barrer (`LV-87`, `LV-88`).** En **operadores**, si
  la credencial está adjunta pasa a ser **su propia columna** con una figura de
  sí/no, en vez de una insignia metida en la celda de la fecha (que parecía
  calificar a la fecha). En **movimientos de recursos**, la página muestra por
  defecto **los últimos 30 días** —con un selector visible que llega hasta "todo
  el registro"—, junta "desde/hasta" en una sola columna de **trayecto**, y cada
  recurso enlaza a su ficha.
- **Una alerta, una fila (`LV-75`).** Se eliminó el agrupado por regla + fecha:
  su premisa ("misma fecha ⇒ misma causa") ya se había mostrado falsa contra
  datos reales, y la fila agrupada seguía afirmándola además de dejar su columna
  de acciones sin botón. El **motivo de cierre ahora se lee en la lista** en vez
  de vivir escondido en un tooltip.

### Fixed

- **El CI vuelve a arrancar: nunca había corrido una sola vez.** Desde que el
  workflow nació (`8cfbd75`, 2026-07-22) las rutas de trabajo se definían con
  `${{ runner.temp }}` en el bloque `env:` **del job**, donde ese contexto no
  existe — sólo se permiten `github`, `needs`, `strategy`, `matrix`, `vars`,
  `secrets` e `inputs`. GitHub abortaba el workflow al evaluarlo: fallo en 0 s,
  sin jobs y sin log, con el mensaje genérico *"This run likely failed because
  of a workflow file issue"*. Las **100 corridas** que devuelve el historial
  están en `failure` por esta causa. Las rutas se exportan ahora vía
  `$GITHUB_ENV` en un paso, donde `$RUNNER_TEMP` sí existe, y los directorios se
  crean explícitamente. De paso, el *preflight* de staging llamaba a
  `verify_backup` con comillas escapadas (`\"$BACKUPS_DIR\"`) dentro de un
  bloque `run: |`, donde YAML no procesa escapes: bash recibía las barras
  invertidas literales, el `ls` no encontraba nada y el comando se ejecutaba
  **con la ruta vacía** sin que el paso fallara. Con esto, *"un PR por bloque,
  con CI verde"* (`AGENTS.md`) deja de ser inalcanzable y la promesa del README
  sobre Ruff, Bandit y pip-audit en CI pasa a ser cierta.
- **Editar un permiso ya no permite cambiarle el estado por la puerta de atrás
  (`LV-101`).** El formulario de edición ofrecía el estado como un desplegable
  cualquiera: por ahí se podía marcar **Aprobado sin la autorización firmada de
  la DGAC**, retroceder en el flujo, y el historial quedaba atribuido a
  `system` en vez de a la persona. En su lugar hay un botón **"Corregir
  estado"** que **exige un motivo escrito**, deja quién y por qué en el
  historial, y **mantiene la exigencia del PDF firmado** — corregir no es un
  atajo para saltarse el papeleo, es dejar claro que lo anotado estaba mal.
- **Documentos agrupados y filtrables por categoría (`LV-104`).** En la ficha de
  una aeronave, un operador o un permiso, los documentos aparecen **agrupados**
  (documentos de la aeronave, del personal, autorizaciones DGAC…) en vez de una
  sola lista por fecha. Y en **Documentos de la empresa** se puede filtrar por
  categoría, que ofrece sólo las que realmente tienen documentos. Pensado para
  cuando entren los cientos de archivos del repositorio `Z:`.
- **Expediente operativo del permiso (`LV-107`).** La ficha de un permiso abre
  ahora con la respuesta a **"¿esta operación está completa y documentada?"**:
  autorización DGAC firmada, carta de permiso, seguro de cada aeronave,
  credencial de cada operador, plan geoespacial, revisión meteorológica y vuelos
  registrados — todo en una lista, sin abrir cinco pantallas. **Lo que falta se
  nombra**: no dice "faltan vigencias", dice qué aeronave y por qué. Y distingue
  *vencido* (rojo) de *sin dato cargado* (ámbar), que son problemas distintos.
- **El calendario sale del menú (`LV-103`).** Decisión tomada: la mitad de lo
  que mostraba eran vencimientos, que ya llegan a **Alertas** — donde además se
  resuelven y queda registrado el motivo. **No se borró nada**: la pantalla
  sigue existiendo para quien tenga el enlace, y devolverla al menú es revertir
  un comentario. Si dentro de unas semanas nadie la echa de menos, se retira del
  todo.
- **La bandeja de alertas, mejor repartida (`LV-110`).** El motivo con que se
  resolvió una alerta tiene ahora **columna propia** ("Resolución"), junto a su
  estado, en vez de ir apretado en letra chica debajo de los botones. Y los
  botones de acción miden todos lo mismo, así que la columna deja de verse
  dentada.
- **Ver un documento sin salir de la ficha (`LV-92`).** "Ver" abre el PDF o la
  imagen **encima** de la página que estabas mirando, así que revisar la carpeta
  de una aeronave antes de una auditoría deja de ser entrar y volver por cada
  archivo. También se agregó "Ver" en **Documentos de la empresa** y en
  **Registros operacionales**, donde antes había que descargar para mirar.
- **Los dos gráficos del panel vuelven a dibujarse (`LV-109`).** Estaban vacíos:
  el panel intentaba construir dos gráficos que ya se habían retirado de la
  página, y ese error impedía que se dibujaran los que sí quedaban.
- **Cancelar una carga de documento ya no te deja tirado (`LV-99`).** Volvía a
  la lista general de documentos, que no está en el menú: desde ahí no había
  cómo seguir. Ahora vuelve **a la ficha desde la que empezaste**, igual que si
  hubieras guardado.
- **La pantalla de reemplazo dejó de ofrecer dos campos que ignoraba
  (`LV-100`).** "Tipo de entidad" y "Registro asociado" se veían editables, pero
  reemplazar un documento nunca lo mueve de registro. Ahora el registro se
  **muestra**, en vez de fingir que se elige.
- **El botón "Filtrar" de Documentos de la empresa vuelve a su tamaño
  (`LV-105`).** Se estiraba a lo alto de dos filas de controles.
- **La bandeja de alertas deja de hacerse más lenta con cada alerta
  (`LV-106`).** Consultaba la base **una vez por fila** para resolver de qué
  registro hablaba cada alerta, así que la pantalla se degradaba justo con lo
  que la hace útil: medido, pasaba de 24 consultas con 5 alertas a 84 con 25.
  Ahora el número no crece con las filas. No cambia nada de lo que se ve.
- **Los errores de los formularios en ventana emergente ahora se ven
  (`LV-108`).** Al guardar un formulario inválido dentro de un modal —crear,
  editar, resolver una alerta— el servidor respondía diciendo qué estaba mal y
  **la pantalla no mostraba nada**: la ventana se quedaba quieta, sin error y
  sin cerrarse. Afectaba a todos los modales de la app.
- **Un antivirus que no puede revisar ya no acusa al archivo (`LV-96`).** Si el
  escáner no logra dar un veredicto —típico en un ClamAV recién instalado,
  mientras baja su base de firmas— la subida se sigue rechazando (nada se guarda
  sin revisar), pero **el mensaje dice que es un problema del servidor**, no que
  tu archivo tenga una amenaza. Antes los dos casos se veían idénticos, así que
  la salida era reintentar con otro archivo para siempre. Los mensajes además
  aparecen **en español**, y el fallo del escáner queda registrado con su código
  de salida para poder responder "¿fue el antivirus?" mirando el log.
- **`sqlparse` al día (dos CVE).** Dependencia interna de Django: 0.5.5 → 0.6.0.
  Lo detectó el gate de seguridad del proyecto, no un incidente.
- **Las tablas se leen bien con lector de pantalla (`T5.8`).** Los encabezados de
  las 33 pantallas con tabla ahora declaran si encabezan una columna o una fila.
  No cambia nada de lo que ves; cambia lo que oye quien usa la app sin mirarla.
- **El respaldo se toma de forma consistente aunque estés usando la app
  (`LV-116`).** Antes se copiaba el archivo de la base tal cual, y si alguien
  guardaba algo mientras la copia avanzaba podía quedar a medio camino entre dos
  estados. Importa porque el respaldo "de las 22:00" corre en realidad a las
  **18:00 hora de Chile**, en plena jornada. Ahora se toma con el mecanismo
  propio de SQLite, que garantiza un punto consistente.
- **El respaldo se comprueba solo, todos los días (`LV-115`).** Hasta ahora nadie
  miraba un respaldo hasta el día que hacía falta. Ahora el último se **abre como
  base de datos** y se consulta: si no serviría para restaurar, llega un correo
  con los pasos a seguir. Verificar la suma de control no bastaba — una copia
  tomada mientras la aplicación escribía puede estar rota **y tener la suma
  correcta**. No reemplaza el ensayo completo de restauración.
- **Aviso cuando un trabajo programado deja de correr (`LV-114`).** Si el
  respaldo, el motor de alertas o el resumen diario se atrasan o fallan, ahora
  llega un correo a Dirección diciendo cuál y desde cuándo — antes había que
  entrar al centro de administración a mirarlo, que es lo que nadie hace cuando
  todo parece estar bien. **Si todo está al día no escribe nada.**
- **Las alertas dejan de perseguir aeronaves dadas de baja (`LV-113`).** Una
  aeronave retirada de la flota con el seguro vencido mantenía su alerta para
  siempre, y no había nada que hacer con ella. Ahora los registros que ya no
  operan quedan fuera de todas las reglas, no sólo de algunas.
- **La bandeja de alertas tiene un orden (`LV-112`).** Lo abierto primero y lo
  más antiguo arriba, en vez del orden que quisiera la base de datos. De paso
  esto hace fiable el paginado: sin un orden declarado, pasar de página podía
  repetir o saltarse filas.
- **Una póliza vencida ya no se dibuja como vigente (`LV-81b`).** En la ficha de
  la aeronave, la insignia decía "Vencida" pero la barra de estado seguía
  mostrando **"Póliza vigente"** como alcanzado — dos cosas incompatibles en la
  misma pantalla. Ahora ese paso dice **"Póliza vencida"**, y los pasos
  anteriores siguen en verde: que la póliza haya vencido no borra que el trámite
  se hizo.
- **Una alerta resuelta ya no vuelve a aparecer (`LV-111`).** Si resolvías una
  alerta, el trabajo nocturno la creaba de nuevo esa misma noche —el dato seguía
  vencido— y la bandeja mostraba dos filas del mismo caso, una resuelta y otra
  abierta. Ahora se queda resuelta. **Con una excepción a propósito**: si el
  documento o la credencial se renueva, el vencimiento siguiente **sí** genera
  una alerta nueva, porque es un caso nuevo y esconderlo sería peor.
- **No se podía subir un documento desde "Nuevo documento" (`LV-94`).** Al elegir
  el tipo de entidad, la lista de **"Registro asociado" no se llenaba nunca**, y
  sin registro no hay documento que guardar. Pasaba en la pantalla de carga, en
  la de reemplazo y en la de carga por lote; **no** pasaba al entrar desde la
  ficha de una aeronave u operador, porque ahí los dos datos vienen en el enlace
  — por eso el problema podía convivir con un uso diario normal. La carga por
  lote, además, ahora también permite elegir el registro cuando se llega a ella
  directamente.
- **Pantallas que salían en inglés dentro de la interfaz en español (`LV-80`).**
  Los títulos de crear/listar ("New Document") y el nombre de la pestaña del
  navegador. Afectaba a 6 módulos.
- **Alertas que no se callaban (`LV-90`).** Una regla que vigilara el estado de
  una aeronave seguía alertando sobre aeronaves **dadas de baja**, para siempre.
  Ahora cada modelo declara dónde termina su ciclo, en vez de que el motor de
  alertas lleve una lista aparte que alguien tenía que acordarse de actualizar.
- **Los números de serie se normalizan a mayúsculas (`X.4c`).** El contrato con
  AeroLink lo exigía desde el principio y sólo se aplicaba la parte de los
  espacios. Sin esto, una batería no habría encontrado su aeronave —y una
  cargada a mano se habría duplicado— **sin ningún error visible**.
- **Subir la autorización DGAC ya no obliga a repetir las fechas del permiso
  (`LV-79`).** El formulario las propone desde el registro enlazado —permiso de
  vuelo y habilitación— y avisa de dónde salieron, para corregirlas si el
  documento dice otra cosa.
- **18 etiquetas de formulario que se veían en inglés** dentro de la interfaz en
  español (alertas, reglas de alerta, tipos de documento, historial de
  mantención y los cuatro formularios del tablero). Se agregó además el test que
  las caza: una etiqueta derivada por Django no es un literal del código, así
  que nada la comparaba contra el catálogo.

## [0.5.0-beta] - 2026-08-11

Trabajo acumulado desde `v0.4.0-beta` (2026-08-04), desplegado y verificado en
producción (`p340`) el mismo día.
Cierra completos los **BLOQUE R1, R2, R3, R5 y R6** de la revisión post-auditoría,
más `R4` parcial, la base ISO de `R7`, `R8.1` y las fases 1-2 del contrato con
AeroLink (`X.1`–`X.3`).

> **Nota sobre el alcance de la beta.** `v0.4.0-beta` declaró que de ahí en
> adelante el foco era *estabilizar lo que ya existe, no agregar módulos nuevos*.
> Esta tanda **sí agrega capacidad nueva** (baterías, API del padrón, clima,
> exportación PDF), porque salió de los bloques post-auditoría que el usuario
> priorizó explícitamente el 2026-08-07. No es una desviación silenciosa: es un
> cambio de prioridad decidido, y queda anotado acá para que la próxima
> definición de alcance no herede una premisa vencida.

### Added

- **Inventario de baterías con ciclos y salud (`R7.2`, ISO 7.1.3).**
  `registry.Battery` con serial como llave de cruce, ciclos, salud, firmware y
  —clave— `source`/`synced_at` para saber de dónde vino el dato y qué tan fresco
  es. **Es un espejo de solo lectura, no el maestro**: el ADR-0002 asigna el
  inventario de baterías a AeroLink porque DJI reporta los ciclos de forma nativa
  y un conteo llevado a mano se desvía de inmediato. Queda **vacío a propósito**
  hasta que aterrice `X.4`, y el estado vacío lo explica en pantalla para que no
  se lea como un error.
- **API de solo lectura del padrón para AeroLink (`X.3`, ADR-0002 Fase 1).**
  Aeronaves, operadores y centros de costo expuestos para que AeroLink resuelva
  seriales sin duplicar el inventario. Scope nuevo sobre el DRF que ya existía,
  no una aplicación nueva.
- **Pronóstico de viento y ráfagas sobre el área de vuelo (`R8.1`, ISO 8.1).**
  En la ficha del plan geoespacial, para el día en que empieza el permiso
  vinculado (no "hoy", que sería peor que nada para un plan del mes que viene).
  **La llamada se hace del lado del servidor**, así que la CSP no cambia; se
  eligió Open-Meteo porque no requiere API key; y **está apagado por defecto**
  (`WEATHER_ENABLED`), de modo que un despliegue que no lo active conserva la
  propiedad de cero llamadas salientes.
- **Exportación PDF del reporte de cumplimiento (`R6.4`).** Con `reportlab`
  (puro Python, sin paquete de sistema que instalar en la VM). Junto a
  CSV/XLSX/DOCX, que ya existían.
- **Comparación contra el período anterior en el reporte web (`R6.4`).** Ya
  existía en el correo ejecutivo; ahora la web y el correo leen la **misma**
  función en vez de dos copias.
- **Agrupar alertas del mismo origen y resolverlas juntas (`R6.3`).** Una póliza
  de flota que vence en una fecha y cubre varias aeronaves se ve como una fila,
  con un botón que pide **un motivo compartido** — antes había que escribir el
  mismo motivo N veces.
- **Resolver una alerta exige un motivo / causa raíz (`R6.2`, ISO 10.2).**
  `Alert.resolution_reason`. Los llamadores automáticos siguen sin motivo a
  propósito: no hay humano a quien preguntarle.
- **Recordatorio del día 15 de revisiones mensuales pendientes (`R6.5`).**
  Comando nuevo que escala a Dirección lo que nadie firmó. **Nunca crea ni
  modifica una revisión**, solo reporta — así un fallo del cierre de fin de mes
  no queda enmascarado como "todo en orden".
- **"Documentos de la empresa" como repositorio real (`R4.6`).** Búsqueda por
  título, filtro por categoría y exportación CSV, donde antes había un listado
  plano sin filtros.
- **Cuatro tipos de documento nuevos (`R7.3`, `R4.8`).** Certificado de
  calibración GNSS/RTK (vigencia vigilada, ISO 7.1.5), Certificado AOC,
  Procedimiento o manual de la empresa, y Aviso Mensual de No Operación.
- **Habilitaciones en la ficha del operador (`R5.8`).** Con tipo, fechas e
  insignia de vencido, reemplazando el texto libre que decía lo mismo sin fecha.
  La sección del menú se ocultó (la vista sigue viva).
- **Flujo real de mantención con taller externo (`R5.1`).** Camino largo
  `enviado → en taller → terminado → en tránsito → completado` junto al corto
  original, ligado al historial del equipo: la aeronave se marca "en mantención"
  y vuelve a "casa matriz" sola, reusando la señal que ya generaba el rastro de
  movimientos.
- **Ficha de aeronave como expediente (`R5.4`, `R7.1`).** Historial de
  mantenciones completadas y **horas de vuelo acumuladas** (ISO 7.1.3).
- **Asignación múltiple de aeronaves y selectores con modelo y serie
  (`R5.5`/`R5.6`).**
- **Seguimiento del trámite del seguro JAC (`R5.7`).** Distingue "en trámite" de
  "sin seguro pedido", que antes se veían igual.
- **Importador del repositorio documental de `Z:` (`R4.1`/`R4.3`/`R4.5`).** Con
  modo informe obligatorio antes de `--apply`, y campos de procedencia
  (`content_sha256`, `source_reference`, `R4.2`) para que una reimportación no
  duplique.
- **Columna, búsqueda y CSV del registro de movimientos (`R5.3`).**
- **Diseño de las 4 cláusulas ISO que quedaban (`R7.4`–`R7.7`).**
  [docs/dev/iso-r7-design-plan.md](docs/dev/iso-r7-design-plan.md) — entregable
  de diseño, no implementación, que es lo que el bloque pedía.

### Changed

- **`Aircraft.serial_number` es único y normalizado (`X.1`).** Es la llave de
  cruce con AeroLink y con las carpetas de `Z:`. Las 4 discrepancias contra el
  repositorio se resolvieron **contra el registro físico, no adivinando**: 2 eran
  espacios espurios, y en las otras 2 el valor correcto era el que ya tenía la
  app (las carpetas de `Z:` son las que están mal).
- **Insignia "Sin PDF" en la lista de operadores (`R4.7`).** La fecha de vigencia
  DGAC se tipea a mano y no decía nada sobre si el PDF de la credencial estaba
  cargado; ahora sí.
- Dependencia nueva: `reportlab>=4.2,<5`. **Requiere `uv sync` al desplegar.**

### Fixed

- **Completar la tarjeta del tablero ahora sí resuelve su alerta (`R6.1`).** El
  cierre era unidireccional, así que una acción correctiva podía quedar
  inconsistente entre las dos vistas. Detalle no obvio: tuvo que ser `post_save`,
  no `pre_save`, o la segunda escritura de `Alert.resolve()` se perdía.
- **Los movimientos de recursos registran quién los hizo (`R5.2`).** Un registro
  de movimientos sin autor no sirve como evidencia ante un auditor. Cubrió
  también un tercer caso que el plan no listaba: editar la ubicación de una
  aeronave.
- **Orden de operaciones de la migración `0028` (`X.1`).** Reventaba con
  aeronaves de serial en blanco. Se descubrió corriendo contra el demo: la copia
  del respaldo con que se probó primero no tenía ninguna, así que ahí el error
  era silencioso.
- **Paginación desactualizada tras buscar en la lista de documentos.** La página
  completa no renderizaba el contenedor que el intercambio htmx necesita, así que
  el paginador quedaba obsoleto en silencio.

### Security

- **La descarga de documentos tiene test de aislamiento entre organizaciones
  (`V.3`/F-05).** El control ya estaba en el código; lo que faltaba era la
  prueba, y un control de seguridad sin prueba está a un refactor de regresar en
  silencio. **Con esto se cierra uno de los dos pendientes que `v0.4.0-beta`
  declaró para la 1.0** (el otro, `T2.1`, ya estaba cerrado).
- **Validación de esquema en la llamada de clima (`R8.1`).** `urlopen` acepta
  `file://`, así que una URL mal configurada habría sido una lectura de archivo
  local. Lo detectó `bandit` y se corrigió validando el esquema, no silenciando
  el aviso.

### Revisión en vivo sobre producción, el mismo día (LV-66 a LV-73)

El usuario revisó `p340` con datos reales inmediatamente después del despliegue.
Lo encontrado ahí:

- **[P0] Se arregló una pérdida de datos silenciosa en todas las fechas
  (`LV-73`).** Cada `<input type="date">`/`time`/`datetime-local` se mostraba
  **vacío aunque la base tuviera el dato**, y guardar el formulario **lo
  borraba**: el valor se emitía en formato chileno (`21/08/2026`) y esos campos
  sólo aceptan ISO, así que el navegador lo descartaba. Editar cualquier dato de
  una aeronave borraba la vigencia del seguro JAC, y con ella su alerta, su fila
  del calendario y su aporte al reporte. Afectaba a **todos** los formularios de
  escritura. Se encontró abriendo el navegador para verificar otra cosa — ningún
  test lo habría visto, porque el HTML *contenía* el valor.
- **Renovar una vigencia ahora cierra su alerta sola (`LV-71`)**, dejando el
  motivo *"Vigencia renovada al AAAA-MM-DD (cierre automático)"*. Antes había que
  renovar **y** resolver a mano, y eso aplicaba a la mayoría de las alertas
  reales. El cierre queda trazable para ISO 10.2 sin que nadie lo escriba.
- **Se quitó el "Resolver" conjunto de las alertas agrupadas (`LV-68`).**
  Agrupar por (regla + fecha) asumía que una fecha compartida implica una causa
  compartida; los datos reales mostraron dos aeronaves con pólizas distintas
  venciendo el mismo día, y un motivo único firmado sobre hechos independientes
  es evidencia falsa. El agrupado visual se mantiene; cada alerta se resuelve por
  separado.
- **"Seguimiento de alertas" salió del menú (`LV-69`/`LV-69b`)** por decisión del
  usuario, junto con los botones que mandaban trabajo ahí. La lista de alertas
  quedó autocontenida. La vista sigue viva por URL.
- **Comando `refresh_geoplan_titles` (`LV-70`)** para los títulos de planes
  geoespaciales congelados con el formato de permiso anterior a `R2.2`.

### Interno

- `HANDOFF.md` pasó de ~900 a 72 líneas: había derivado a bitácora de sesiones,
  que su propio encabezado prohíbe. El contenido operativo se movió a
  `docs/compliance-setup.md` y los gotchas acumulados a una sección
  **"Lecciones operativas"** en `AGENTS.md`.
- El runbook de la VM se corrigió con el despliegue real: **`set -a` no es
  opcional** al cargar el entorno (sin él `manage.py` cae a `dev`), y el usuario
  de systemd es `levdigital01`, no `aero`.

## [0.4.0-beta] - 2026-08-04

Primera versión **beta**: de aquí en adelante el foco es estabilizar lo que ya
existe, no seguir agregando módulos nuevos. Cubre el bloque de planificación
geoespacial (KMZ/KML) y el de seguimiento operativo completos (BLOQUE
GEO/OPS), más ~30 hallazgos de una revisión en vivo con datos reales de la
DGAC (12 centros de costo, 41 operadores, 15 aeronaves). Pendiente,
deliberadamente, de una versión 1.0: **V.3** (aislamiento de `Document` entre
organizaciones, bloqueado por la migración de tenancy T3.2) y **T2.1**
(cerrar el IDOR de checklist/etapa en el tablero) — sin efecto mientras haya
una sola organización, que es el caso actual; ver `MASTER_PLAN.md`.

### Added
- **Seguimiento de alertas: degradado de urgencia y contador de vencidas
  (B3.3/B3.4).** Cada tarjeta muestra ahora si vence en 7/15/30 días o si ya
  está atrasada — con color, peso y una etiqueta propia (no solo color, para
  quien no lo distingue), usando los mismos límites que el reporte de
  cumplimiento. Cada columna suma, junto al total, cuántas de sus tareas están
  atrasadas.
- **El centro de costo puede tener un contacto del día a día distinto del
  administrador (LV-58).** La lista ya mostraba el administrador de contrato;
  ahora, cuando el responsable directo es un operador del padrón o un contacto
  externo, aparece como subtítulo — antes esa información no se veía en
  ningún lado.
- **"Reportar accidente / daño" en la ficha de la aeronave (LV-46).** Un botón
  marca la aeronave como "Mal estado" y abre de inmediato una mantención de
  emergencia, sin tener que llenar un formulario antes — la alerta de
  "Mantenciones abiertas" ya existente la recoge sola.
- **Importar un plan geoespacial (KMZ/KML) desde el permiso, con un clic
  (LV-50/LV-60).** La ficha del permiso ganó un botón "+ Importar plan"; y al
  llegar desde ahí, el plan **hereda el título y el centro de costo del
  permiso** en vez de pedirlos de nuevo — un plan vinculado a un permiso es su
  área de vuelo, no un registro aparte. De paso se cerró un hueco real: nada
  impedía antes que un plan quedara en un centro de costo distinto al del
  permiso que dice cubrir; ahora se rechaza.
- **Aprobar un permiso de vuelo exige el PDF de la DGAC (LV-51).** No se puede
  pasar a "Aprobado" sin tener adjunta la autorización real que emite el SIGO
  — evita que el estado en el sistema se adelante al papeleo.

### Changed
- **El menú lateral sigue el flujo de trabajo, no la estructura de datos
  (LV-61).** Antes lo que se configura una vez (padrón, asignaciones) ocupaba
  los primeros dos grupos y lo que se usa a diario (permisos, alertas) quedaba
  abajo. Ahora: **Vuelo** (Permisos → Planificación geoespacial → Vuelos →
  Calendario, en el orden en que ocurre) · **Cumplimiento** ·
  **Mantenimiento** (renombrado "Mantenciones", ya no colisiona de nombre con
  "Registros operacionales") · **Padrón** al final.
- **El tablero "Plan de acción" pasa a ser "Seguimiento de alertas" (LV-48),
  con su propio enlace en el menú (LV-55).** Ya no es un Kanban genérico: es
  donde se le hace seguimiento a la acción correctiva de cada alerta —el
  botón "Crear tarea" de una alerta y el reporte de aeronaves dañadas
  desembocan ahí. Se le quitó además la pestaña "Vista de calendario", que
  duplicaba el calendario general de la app.
- **El nombre del administrador de contrato es obligatorio en Centros de
  costo (LV-56).** Era el único de los tres tipos de responsable sin esa
  validación (Operador y Contacto externo ya la tenían).
- **Columnas normalizadas en Centros de costo, Aeronaves, Operadores y
  Habilitaciones (LV-57), y en Permisos de vuelo (LV-53).** Las cuatro listas
  del padrón y la de permisos ya siguen la misma distribución que el resto de
  la app (búsqueda en vivo, columna de identidad con subtítulo, acciones
  consistentes) en vez de una plantilla plana propia sin filtros.
- **El calendario ya no tiene tres sistemas de navegación superpuestos y
  desconectados (LV-47).** Los botones "← Anterior / Siguiente →" no movían
  el calendario real (FullCalendar los ignoraba); se quitaron, y el respaldo
  para cuando falla el JavaScript ahora sí funciona cuando realmente se
  necesita, en vez de estar oculto siempre.
- **Ficha del centro de costo en secciones agrupadas (LV-36)** y **textareas
  que empiezan en 3 filas, no en un bloque enorme (LV-35)**, consistente en
  todas las fichas.
- La pestaña "Equipo" del centro de costo pasa a llamarse **"Operadores"**
  (confundía con equipamiento/drones; "Equipos habilitados" sigue siendo la
  flota) (LV-37).

### Fixed
- **El reporte de cumplimiento mostraba 0% aunque hubiera vencimientos reales
  (LV-49).** Las vigencias DGAC (credencial del operador, seguro de la
  aeronave) ya disparaban alertas reales, pero el reporte solo contaba
  documentos — ahora las suma con los mismos rangos de urgencia.
- **Cinco lugares donde un permiso sin folio mostraba "None" como título
  (LV-52).** La ficha, la lista, el registro de vuelo, la pestaña de permisos
  del centro de costo y el respaldo sin-JS del calendario usaban el campo
  crudo en vez del texto ya resuelto (con su alternativa correcta cuando no
  hay folio).
- **Un `?doc_type=` o `?cost_center=` con un valor inválido en la URL del
  reporte rompía la página con un error (LV-54).** Ahora se ignora, como
  cualquier otro filtro que no coincide con nada.
- **El botón "Crear tarea" de una alerta no funcionaba (LV-45).** Faltaba
  sembrar el tablero de cumplimiento en el entorno — quedó documentado en el
  procedimiento de despliegue para que no vuelva a faltar.
- **Seis títulos de lista en inglés o mal capitalizados (LV-62)**, entre
  ellos "Flight Records" en Vuelos, "Alert Rules" y "Kanban Boards" —
  encontrados con una auditoría de las 21 páginas de lista de la app.
- Un comentario multilínea `{# ... #}` se renderizaba literal sobre la barra
  del calendario, en vez de ocultarse (LV-41); y las pastillas grises se
  fundían con la tarjeta en tema oscuro por bajo contraste de borde (LV-42).
- Las tareas programadas de vigencias DGAC y cumplimiento mensual ya quedan
  cableadas al calendario de tareas de Windows, no solo documentadas (LV-43).
- **Cargar un documento desde una ficha te sacaba de ella.** Subir un documento
  desde un centro de costo (u operador/aeronave/permiso) redirigía a la lista
  general de Documentos —que además ya no está en el menú—; ahora vuelve a la
  **ficha de origen, a su pestaña Documentos**.
- **Contraste malo de las pastillas en tema claro y oscuro.** Las clases
  `*-subtle` de Bootstrap traen `!important` y colores que no siguen el tema de
  la app, así que muchas etiquetas (chips de habilitaciones, tipos de entidad,
  estados) fallaban de contraste en uno u otro modo. Se define una **paleta de
  pastillas propia por familia** (azul/verde/cian/ámbar/rojo/gris) con tonos
  elegidos para leer bien —contraste AA texto/fondo— en **ambos temas**.
- **Textos que salían en inglés en producción.** El catálogo compilado
  (`django.mo`) estaba desfasado del `.po` y el despliegue no lo recompila, así
  que los textos nuevos (registros operacionales, cumplimiento mensual,
  vigencias DGAC, etc.) se veían en inglés. Se recompiló el `.mo`; al tocar el
  `.po` hay que recompilarlo (con `polib`, la VM no tiene `gettext`).

### Changed
- **Responsable del centro de costo por tipo (LV-34).** Un selector
  **Administrador / Operador / Contacto externo** muestra solo el campo que
  corresponde (y limpia los demás), en vez de tres campos paralelos que había
  que saber cuál llenar.
- **Formulario de permiso de vuelo más práctico (LV-38/LV-39).** Los operadores
  (~40) y la flota (~14) se muestran en una **grilla de varias columnas con
  scroll** en vez de una lista vertical larga (mantiene la selección múltiple), y
  el **Estado** va al inicio con el **número de permiso opcional** hasta que esté
  aprobado, para armar el permiso antes de tener el folio DGAC.
- **Pasada de diseño de la revisión en vivo (legibilidad + panel).** Las
  etiquetas y pastillas (chips de habilitaciones, tipos de entidad, estados) se
  leen ahora como pastillas en tema **oscuro y claro** —contorno, cuerpo y más
  peso de fuente— en lugar de fundirse con el fondo. Botones y cabeceras de
  tabla ganan contraste en oscuro y las filas quedan parejas. En **Aeronaves** se
  fusionó *Fabricante* dentro de *Modelo*, el centro de costo muestra su código
  (nombre en tooltip) y se compactó la columna de seguro, para que la tabla
  quepa sin scroll. El **panel** se
  reordenó: KPIs con el **número protagonista** repartidos en una grilla pareja
  (sin que una tarjeta quede suelta), pastillas de tipo/estado con más presencia
  en oscuro (menos opacas), la activación de cumplimiento
  pasó a una **franja compacta con estados**, los vencimientos suben arriba y
  los gráficos sin datos se ocultan (sin recuadros vacíos ni el duplicado
  "Tareas por etapa"). El buscador dice **"Buscar en AeroControl"**, el
  calendario deja de repetir el mes, y la lista general de **Documentos** sale
  del menú (la carga ya vive en cada ficha/sección).

### Added
- **Listas de asignaciones con columnas reales + calendario más limpio + VLOS/
  paracaídas como lista (LV-31/LV-25).** Las **asignaciones de operador y de
  aeronave** dejan la tabla genérica y muestran columnas propias (Operador/
  Aeronave, Centro de costo, Estado, Propósito, Desde). En el **calendario**, un
  permiso de varios días ya no se pinta en cada casilla: aparece como un solo
  marcador en su inicio con "→ hasta DD-MM". Y en la ficha de aeronave, **VLOS**
  y **Paracaídas** pasan de texto libre a una **lista** con los valores en uso
  (normalización suave: editar una fila antigua nunca rechaza su valor).
- **Registros operacionales por vuelo + cierre de cumplimiento mensual (LV-30).**
  Nueva sección **"Registros operacionales"** (*Cumplimiento*) para la bitácora
  (REG-015), el checklist RPA (LVE-003) y la inspección de dron (LVE-002):
  documentos por vuelo colgados de un centro de costo, filtrables por CC, mes y
  tipo, con subida prellenada. Y una **"Cumplimiento mensual"**: a fin de mes el
  comando `check_monthly_records` crea una revisión pendiente por cada CC que
  voló (vuelos vs registros del mes) y avisa a Dirección; cada pendiente queda
  como **alerta viva** hasta que Dirección la marca **Cumple/No cumple** (con
  notas y export CSV). El panel muestra "Registros del mes: X/Y centros al día".
- **Vigencias DGAC en las fichas: credencial del operador y seguro JAC de la
  aeronave (LV-29).** Ahora se registra en la ficha la fecha de *Vigencia* de la
  credencial DGAC de cada operador y la del *Seguro JAC* de cada aeronave (datos
  del SIGO). Aparecen como **columna** en las listas (badge Vencida/Por vencer),
  suman al panel de **próximos vencimientos**, generan **alerta** con las dos
  reglas opcionales nuevas (`seed_alert_rules --with-optional`) y salen en el
  **calendario** dentro del carril "Vencimientos". Para cargarlas en lote está
  `load_dgac_vigencias` (idempotente, `--dry-run`, `--file` CSV, reporta los no
  coincidentes) y para avisar a cada operador de sus vigencias por vencer o ya
  vencidas, `notify_expiring_credentials` (email al operador; timer opcional).
- **Enviar una aeronave a mantenimiento, y que quede como alerta hasta
  resolverse.** La ficha de la aeronave muestra sus mantenciones abiertas y tiene
  un botón "Enviar a mantenimiento"; con la regla de alerta de mantenciones
  abiertas, esa aeronave queda marcada en Alertas y el panel hasta que la
  mantención se completa, momento en que la alerta se cierra sola.
- **Cada ficha guarda sus documentos, y la empresa tiene su repositorio.** Las
  fichas de aeronave y operador ahora muestran y permiten subir sus documentos
  (resolución JAC, aeronavegabilidad, seguro, credenciales…), igual que ya hacía
  la del permiso; el centro de costo también. Renovar una credencial que vence
  guarda el histórico (reemplazo versionado). La ficha del permiso lista además
  sus planes geoespaciales (KMZ), así que carta y área quedan juntas. Y hay una
  nueva sección **"Documentos de la empresa"** (accesible desde el panel) para el
  AOC, los procedimientos y los formularios, con descarga y control de
  vencimiento.
- **Dashboard más accionable y con vencimientos reales (T5.4).** Los indicadores
  de aeronaves, operadores y alertas ahora son enlaces a sus listas, y el panel
  de próximos vencimientos ya no muestra solo habilitaciones: suma **documentos
  y permisos de vuelo** por vencer, cada uno con enlace directo a su ficha.
- **Registrar un vuelo desde su permiso es más rápido (T5.5).** Al crear un
  registro de vuelo desde la ficha del permiso, este queda prellenado y los
  selectores de piloto y aeronave se acotan al roster de ese permiso —sin tener
  que buscar entre todo el padrón ni arriesgar una combinación inválida.
- **Búsqueda global accesible y que lleva al detalle (T5.2/T5.3).** La búsqueda
  global existía pero no había forma de llegar a ella; ahora hay una caja en la
  barra superior. Y sus resultados de centros de costo, aeronaves y operadores
  abren la ficha del registro en vez de la lista, así que encontrar algo es un
  clic hasta el detalle.
- **Seguimiento de contratos, recursos y permisos (BLOQUE OPS, OPS-0..OPS-8).**
  Asignaciones por recurso (`OperatorAssignment`/`AircraftAssignment`, un
  operador o aeronave por centro de costo y período, con validación de
  solape) reemplazan aditivamente el antiguo par `Assignment` (que sigue
  intacto). Un log de movimientos append-only (`ResourceMovementLog`) registra
  cada asignación, reasignación, liberación y cambio de ubicación física de
  aeronave (casa matriz/faena/mantenimiento). Ficha del contrato
  (`CostCenterDetail`) con seis pestañas separadas (Resumen/Equipo/Flota/
  Permisos/Documentos/Historial, cada una acotada por su propio permiso) y
  timeline propio en la ficha de Operador y Aeronave. `FlightPermission` ahora
  espeja la autorización DGAC real: varios operadores y aeronaves (M2M) y un
  rango de vigencia (`valid_from`/`valid_until`) en vez de uno de cada uno en
  un solo día, con adjuntos (cartas) sobre el pipeline de documentos existente
  y un log de cuándo se vincula a un plan geoespacial. Filtro global por
  centro de costo en el dashboard. Diseño en
  `docs/dev/ops-contract-tracking-plan.md`.
- **Editor geoespacial KMZ/KML (BLOQUE GEO, MVP GEO-0..GEO-10).** Importar un
  KMZ/KML crea un plan versionado (documento canónico "AeroKML JSON" inmutable
  por versión); un mapa Leaflet (vendorizado con SRI, sin CDN) lo visualiza por
  carpetas con mediciones; con permiso de edición, Leaflet-Geoman permite
  dibujar/editar geometrías y guardar como nueva versión (API de commit con
  concurrencia optimista y dedupe). Workflow por rol
  (borrador→edición→revisión→aprobado/rechazado) y export KML/KMZ que reabre en
  Google Earth, copiando los recursos embebidos del original. Todo el parseo,
  validación y versionado vive en el servidor; la isla JS es una vista
  reemplazable. Diseño en `docs/dev/geo-editor-plan.md`.
- Centro de costo acepta un **contacto externo** (nombre y correo) como
  alternativa al **Operador responsable** para el resumen de vencimientos.
  Antes, el único destinatario posible era alguien del padrón de operadores
  RPAS; en la práctica el responsable puede ser un administrador, secretaría
  o un SSO ajeno al sistema. Si ambos están configurados, se prefiere el
  operador; el contacto externo se usa cuando el operador no tiene correo o
  quedó archivado.
- **Comando `seed_alert_rules`**: siembra idempotente del conjunto de reglas de
  alerta recomendado para una operación RPAS bajo DGAC (documentos y permisos de
  vuelo por vencer a 30 días), con `--with-optional` para habilitaciones y
  mantenimiento. Espeja a `seed_document_types` y convierte el paso "crear las
  reglas a mano" de `docs/compliance-setup.md` en un comando repetible.
- **Asignación masiva de operadores a un centro de costo**: el botón "+ Nuevo"
  de *Asignaciones de operador* ahora toma varios operadores a la vez y los
  lleva al mismo centro de costo en una sola acción, en vez de uno por uno. Un
  operador ya asignado en otro centro de costo se **mueve** (cierra la
  asignación previa y abre la nueva), integrado con el log de movimientos.
- **Chips de "Equipos habilitados" con color por tipo** en la lista de
  Habilitaciones: un color estable por `QualificationType` para diferenciar cada
  familia (Mavic/Matrice/Phantom/…) de un vistazo; las vencidas siguen en rojo.

### Changed
- **Dependencias:** `django-crispy-forms` 2.6 → 2.7 (pack de render de
  formularios, suite completa verde) y `gunicorn` amplía su rango a `>=23,<27`.
  `ruff` se mantiene en 0.15.22 a propósito: 0.16.0 cambia su set de reglas por
  defecto (224 issues nuevos de orden de imports), un cleanup aparte, no un
  drop-in. El resto de PRs de dependabot ya estaban en `main`.
- **Los formularios Kanban ya no muestran el campo técnico "Orden"**: la
  posición de columnas, tarjetas, etiquetas e ítems de checklist se maneja con
  arrastrar y soltar y se asigna en el servidor (las nuevas se agregan al final),
  así que el input numérico de orden — que el usuario nunca escribía a mano —
  sale de los cuatro formularios. (Refactor rescatado de una rama paralela que
  había quedado sin fusionar.)
- **El formulario de asignación de operador ya no pide fechas**: lo relevante es
  el centro de costo y el estado, así que la fecha de inicio se autollena con hoy
  y las fechas salen del formulario.
- **El nombre del centro de costo vuelve a ser editable** desde el formulario
  (opcional). Se había quitado en la simplificación anterior, lo que dejaba
  congelado el nombre que muestra la lista y obligaba a usar el admin técnico
  para crear o corregir un nombre como "Casa Matriz".

### Security
- **Aislamiento por objeto entre organizaciones (F-03/F-06).** Las listas ya se
  acotaban por organización; ahora también la **ficha, la edición y el
  archivar/restaurar** de centros de costo, aeronaves y operadores: abrir por URL
  el registro de otra organización devuelve 404. Sin efecto con una sola
  organización (el caso actual), correcto al centralizar varias.

### Fixed
- **La búsqueda en vivo y la paginación ya funcionan bien en todas las listas
  (F-13).** Dos problemas resueltos: los controles de paginación quedaban con el
  número de páginas anterior tras buscar (ahora se actualizan en la misma
  respuesta, *out-of-band*); y las listas con columnas propias (centros de
  costo, aeronaves, operadores, habilitaciones, asignaciones) mostraban las
  columnas genéricas al buscar en vivo (ahora cada una conserva sus columnas).

## [0.3.0-alpha] - 2026-07-27

Revisión completa V.1-V.39 (`AUDIT_CLAUDE.md`) sobre seguridad, estabilidad,
desempeño y experiencia de uso, más el cierre de T2.3/T2.4/T2.5 y R.10/T5.1.
Pendiente de esa revisión, y a propósito: V.3 (⛔ depende de T3.2, la migración
de tenancy) y V.10-V.12 (⬜ requieren una decisión de política, no son un bug).

### Fixed (revisión 2026-07-25: seguridad y estabilidad)
- El export CSV del tablero de trabajo devolvía todas las tareas de todos los
  tenants; la edición de tareas no comprobaba el acceso de edición al tablero y
  permitía moverlas a tableros ajenos; `/api-token/` aceptaba intentos de
  contraseña ilimitados. Todo acotado, con throttling anon de 10/min.
- SQLite ahora abre con WAL y timeout de 20 s: el middleware de auditoría
  estaba perdiendo eventos en silencio cada vez que un job nocturno retenía el
  lock de escritura.
- Un job interrumpido ya no queda registrado como éxito: `JobRun` nace "en
  ejecución" y solo pasa a ok/error al terminar.
- Alerta y tarea de seguimiento se escriben en una transacción; resolver o
  reabrir una alerta ya no puede dejar la tarea desincronizada.
- La API valida los valores antes de guardar (una fecha malformada daba 500).

### Changed (revisión 2026-07-25: desempeño)
- El tablero Kanban renderiza con un número fijo de consultas (antes ~1 por
  tarjeta más ~3 por columna); el informe de cumplimiento cuenta en la base en
  vez de iterar documentos en Python y respeta el filtro de centro de costo que
  ignoraba; el feed del calendario se acota a 92 días; los exports CSV van en
  streaming; índices nuevos en las fechas del calendario y los pares genéricos.

### Fixed (revisión 2026-07-25: experiencia de uso)
- Tipos de documento y reglas de alerta ya se pueden **editar** desde la UI
  (antes el botón Editar era un 404 y corregir un error exigía el admin
  técnico). Los botones Ver/Editar solo aparecen donde la ruta existe.
- El Centro de administración se muestra a quien tiene permisos de ver su
  contenido, no solo a `is_staff`.
- Los mensajes de aprobar/rechazar/completar salen en español (eran
  inextraíbles para el catálogo); las validaciones de asignaciones pasan por el
  catálogo como el resto.
- Resolver o deshacer una alerta vuelve a la lista filtrada donde estabas, con
  confirmación; importar CSV confirma cuántas filas entraron y ofrece deshacer
  la importación desde la propia página (el revert existía pero no estaba
  enlazado en ninguna parte).
- El arrastre del Kanban avisa cuando está desactivado por cualquier filtro
  (antes se apagaba en silencio con estado, etiqueta o búsqueda).
- El badge de alertas se oculta en 0 (mostraba un "0" rojo permanente) y
  anuncia sus cambios a los lectores de pantalla.

### Added (revisión 2026-07-25: tanda E)
- **Archivar y restaurar desde la interfaz** para centros de costo, aeronaves,
  operadores, asignaciones y habilitaciones: botón en la página de detalle
  (permiso de borrado) y Restaurar en la lista filtrada por Archivado (permiso
  de cambio), con auditoría. Antes retirar un registro exigía el admin técnico
  y el filtro "Archivado" nunca devolvía nada útil.
- Archivar un centro de costo con operadores o aeronaves activos pide
  confirmación mostrando cuántos dependientes tiene y qué implica (sus
  vencimientos dejan de vigilarse). El resumen diario además reporta los
  centros archivados que aún tienen dependientes activos, en vez de callar; y
  ya no notifica a operadores responsables archivados.
- El dashboard detecta el módulo de cumplimiento sin configurar y guía los tres
  pasos en orden (tipos de documento → documentos → regla de alerta), con
  enlaces y marcas de avance. La tarjeta anterior exigía que *todo* estuviera
  vacío, así que con el padrón cargado nunca podía aparecer.
- Las tablas vacías distinguen "aún no hay nada" (con enlace para crear el
  primero) de "ningún registro coincide con los filtros" (con limpiar filtros).

### Fixed (revisión 2026-07-25: tanda E)
- Los botones Volver ya son enlaces reales: `javascript:history.back()` no
  hacía nada al llegar desde un correo del resumen o un marcador. El detalle
  ofrece Volver a la lista, Editar y Archivar.
- Los errores de validación en modales reciben el foco (el re-render HTMX de un
  formulario inválido no disparaba el evento de apertura y los errores
  aparecían sin anuncio).
- Deduplicados los dos bloques responsive en conflicto de `app.css` (56 vs
  58px, ancho por token vs fijo): editar el primero no cambiaba nada.
- Nombres de modelo traducidos en los mensajes ("Operador archivado", no
  "Operator archivado").

### Fixed (autorización de lectura)
- `/calendar/`, el feed de eventos, el tablero Kanban y sus dos fragmentos HTMX
  exigían solo sesión iniciada: un usuario sin ningún permiso veía todas las
  matrículas, operadores y centros de costo en los desplegables de filtro. Cada
  fuente de eventos se filtra ahora por el permiso `view_*` de su propio modelo,
  y cada desplegable por el del modelo que lista. El parámetro `?types=` se
  acota a lo permitido, así que una consulta manipulada no puede ampliar el feed.
- El rol **Viewer** se definía como "todo permiso cuyo código empieza con
  `view_`", lo que en la base real eran 35 permisos incluidos
  `authtoken.view_token`, `auth.view_user`, `sessions.view_session` y
  `core.view_auditevent`: el rol de solo lectura podía leer los tokens de API y
  la traza de auditoría. Ahora son 20 permisos operativos explícitos.

### Changed
- **`TIME_ZONE` pasa de `UTC` a `America/Santiago`** (configurable por entorno).
  El proyecto tenía dos nociones de "hoy" que discrepaban cuatro horas cada
  tarde: la fecha del sistema operativo (`date.today()`) y la de la zona del
  proyecto, que es la que usa la base para los filtros `__date`. Ahora el
  horizonte de vencimientos, el resumen diario, la ventana de alertas y el
  período del informe leen todos la misma fecha, y es la del calendario del
  operador.
- `.github/pull_request_template.md` con casillas derivadas del Definition of
  Done de `AGENTS.md`, sección de riesgo (datos existentes, permisos) y un
  apartado para declarar lo que el PR deja fuera.
- `openspec/`: los cinco changes completados pasan a `changes/archive/`, así que
  `changes/` solo contiene trabajo vivo.

### Fixed
- El informe de cumplimiento tomaba el fin del período de `date.today()` (fecha
  del sistema operativo) mientras filtraba `resolved_at__date`, que la base
  evalúa en la zona del proyecto. Con `TIME_ZONE="UTC"` y la máquina al oeste de
  Greenwich, las dos discrepan cuatro horas cada tarde y toda alerta resuelta en
  esa franja desaparecía del período sin aviso.

## [0.2.0-alpha] - 2026-07-24

Estabilización (`MASTER_PLAN.md` FASE 0 + higiene del Bloque 0), integración
Alertas⇄Kanban (BLOQUE 1, backend), notificaciones y operación programada
(BLOQUE 2), reportes ejecutivos (BLOQUE 6) y robustez de reglas (BLOQUE 4
parcial). Las dos líneas de trabajo paralelas (`codex/impeccable-ui-audit` y
`codex/stabilization-blocks-0-6`) quedaron fusionadas antes de este release.

### Added (BLOQUE 1 — Alertas ⇄ Kanban, backend)
- `AlertRule` puede generar una tarea Kanban: campos `create_kanban_task`,
  `target_board`, `target_stage` con validación de coherencia.
- `generate_alerts` crea una `KanbanTask` vinculada a la alerta
  (`source_object`), con prioridad por urgencia (vencida/≤7 días/resto),
  `due_date` del campo vigilado y responsable derivado cuando la entidad
  vigilada es o expone un operador. Idempotente.
- Al resolver una alerta —o al reemplazar el documento vencido— la tarea
  vinculada se mueve automáticamente a la etapa "completada" del tablero,
  registrando el movimiento en `AuditEvent`.
- Comando `init_dgac_board`: tablero "Cumplimiento DGAC" con sus etapas y
  etiquetas de trámite (idempotente).

### Added (BLOQUE 2 — Notificaciones y operación programada)
- Modelo `JobRun`: cada ejecución de `generate_alerts`, `send_alert_digest` y
  `backup` queda registrada con inicio, fin, resultado y resumen, así que se
  puede comprobar si las tareas programadas realmente corrieron. Visible en el
  admin en modo solo lectura.
- Comando `send_alert_digest`: envía a cada responsable de centro de costo un
  resumen de documentos y habilitaciones agrupados por urgencia (vencidos, 7,
  15 y 30 días), con `--dry-run` para revisar sin enviar. Si un centro de costo
  no tiene destinatario, lo informa y continúa con los demás.
- Configuración de correo por entorno (`EMAIL_*`, `DEFAULT_FROM_EMAIL`,
  `SITE_BASE_URL`). Sin `EMAIL_HOST` el correo se imprime en consola.
- Campo **Operador responsable** en centro de costo: destinatario de los
  resúmenes. El campo de texto anterior no permitía contactar a nadie.
- `scripts/schedule_tasks.ps1` para registrar los tres trabajos diarios en el
  Programador de tareas de Windows, y `docs/scheduled-operations.md` con el
  procedimiento completo y su equivalente en cron.

### Added (BLOQUE 6 — Reportes ejecutivos)
- **Reporte de estado documental** (`/compliance/report/`, enlazado en el panel
  lateral): porcentaje de documentos vigentes por centro de costo, vencimientos
  a 7/15/30 días, vencidos, alertas abiertas con su antigüedad y tiempo medio
  entre la detección de una alerta y su resolución. Filtros por centro de costo,
  tipo de documento y rango de fechas, con exportación a Excel, Word y CSV
  presentable ante jefatura o DGAC.
- Comando `compliance_report` con las mismas cifras, que además puede escribir
  el Excel en una carpeta indicada.
- Comando `send_executive_report --period week|month`: envía el informe
  ejecutivo comparando el período con el anterior (marcando si cada indicador
  mejoró o empeoró) y adjunta el Excel. Destinatarios del grupo *Dirección* o
  indicados con `--to`; `--dry-run` permite revisar antes de enviar. Registrado
  como tarea semanal.
- `bootstrap_roles` crea también el grupo *Dirección* (vacío y sin permisos: es
  una lista de destinatarios, no un rol), para que montar un entorno no dependa
  de leer el código del comando para descubrir que el grupo debe existir.

### Added (BLOQUE 4 parcial — Robustez de reglas y deuda de datos)
- Las reglas de alerta ya no aceptan texto libre: la entidad y el campo a
  vigilar se eligen de una lista validada contra los modelos reales, así que una
  regla mal escrita se rechaza al crearla en vez de fallar en silencio cada
  noche. Las reglas existentes se normalizaron automáticamente; las que no se
  pudieron resolver quedaron archivadas con una nota explicando el motivo.
- Comando `find_duplicate_operators`: lista los operadores que parecen ser la
  misma persona ingresada dos veces, con sus diferencias campo a campo y cuántos
  registros apuntan a cada uno. Con `--apply --group` fusiona un grupo: mueve
  todas las referencias al registro que se conserva, archiva el duplicado con
  nota y deja constancia en la auditoría. No borra nada y no tiene modo masivo.

### Changed
- `on_delete` de `Document`/`Alert`/`AlertRule`/`PermissionHistory`/
  `MaintenanceHistory` cambiado de `CASCADE` a `PROTECT`: el historial de
  cumplimiento ya no se puede perder por borrado en cascada.
- La vista de detalle ya no muestra columnas internas (identificador UUID,
  fechas de auditoría, marca de archivado, tenant) al usuario final.

### Fixed (legibilidad y contraste, revisión en vivo)
- Alertas y tarjetas Kanban mostraban `Qualification object (uuid)` por falta
  de `__str__` en varios modelos; ahora muestran la entidad legible.
- Lista de alertas rediseñada: entidad, regla y badge de vencimiento/atraso
  en lugar del UUID y el mensaje repetido.
- Contraste de los títulos de grupo del panel lateral: 3.79 → 8.06:1 (AA).
- El contador de alertas ya no desaparece al contraer el panel lateral.
- Badges de etapa del Kanban (las clases existían en las plantillas pero no
  en el CSS) y énfasis visual para tareas atrasadas, con icono además de color.
- Gráficos del panel: paleta ilegible en modo oscuro (1.16 → 5.03:1), etiquetas
  con valores crudos de base de datos, y conteos que incluían registros
  archivados. Los gráficos ahora recolorean al cambiar de tema.
- Calendario: los eventos del mes ya no se cortan a media palabra; etiqueta
  completa en el tooltip y colores adecuados en modo oscuro.
- Icono de "Vuelos" diferenciado del de "Aeronaves".
- Traducciones faltantes (~19 cadenas) y dos cadenas que no seguían la
  convención de idioma del proyecto.

### Fixed
- Dashboard: `TemplateSyntaxError` por bloque `extrahead` duplicado que
  causaba un 500 en toda sesión tras el login.
- Mantenimiento: el flujo de cierre (`in_progress → completed`) quedaba en
  un callejón sin salida porque `record_detail.html` nunca renderizaba
  `completion_form`; ahora se puede completar una mantención desde la UI.
- `scripts/verify.ps1` no comprobaba el código de salida de cada paso y
  podía reportar éxito con la suite de pruebas en rojo.

### Added
- Umbral de cobertura real (`fail_under=83` en `pyproject.toml`), reemplazando
  la medición sin consecuencias que tenía CI.
- Test que compila las 43 plantillas HTML (`apps/core/test_templates.py`)
  para atrapar errores de sintaxis que `manage.py check` no detecta.
- Pruebas para `apps/maintenance` (antes sin ninguna) y para
  `generate_alerts` (antes 0% de cobertura).
- Índices en `Alert(is_resolved, is_active)`, `Document(expiry_date,
  is_current_version)` y `KanbanTask(board, stage, order)`.
- Log JSON estructurado (`compliance.alerts`) cuando `generate_alerts`
  descarta una regla inválida.
- `AUDIT_CLAUDE.md` (auditoría técnica) y `MASTER_PLAN.md` (tablero de
  bloques de trabajo, fuente de verdad del roadmap).
- `AGENTS.md` ampliado: precedencia documental, contrato de permisos de
  lectura, Definition of Done por tipo de cambio, convención de ramas.

### Changed
- `docs/` reorganizado: documentación de producto en la raíz **de `docs/`**
  (`docs/SECURITY.md`, `docs/chapter1-import.md`, `docs/frontend-boundary.md`,
  `docs/postgresql-readiness.md`); notas internas y bitácoras de desarrollo
  movidas a `docs/dev/`.
- Rutas de ejemplo en `README.md`, `.env.example`, `ARCHITECTURE.md` y
  `docs/chapter1-import.md` genericizadas (ya no exponen la ruta personal
  del equipo de desarrollo original).
- `openspec/config.yaml` y `docs/dev/03-Roadmap.md` sincronizados con el
  estado real del proyecto (afirmaban falsamente que no había runner de
  tests configurado).
- Código reformateado con `ruff format` (sin cambios de comportamiento).

### Removed
- `.agents/skills/impeccable/` (tooling de terceros vendorizado, ~62.700
  líneas sin relación con el producto), `prompts/` (instrucciones
  obsoletas) y `.atl/skill-registry.md` (rutas absolutas de una máquina
  personal).

## [0.1.0-alpha] - 2026-07-23

Primera fase de estabilización, según `BACKLOG.md`. Estado del repo:
`main` en el merge del PR #9 ("resource planning, calendar and action
plan").

### Added
- Flujo de permisos de vuelo y bitácora de vuelos, con validación cruzada
  de aeronave, operador, fecha y horas.
- Calendario unificado de operaciones y mantenimientos; historial
  automático de cambios de estado.
- Tablero Kanban con arrastrar y soltar, prioridades, asignación a
  operadores y filtros persistidos en URL.
- Dashboard con gráficos (Chart.js) y exportación CSV con neutralización
  de fórmulas.
- Tema claro/oscuro, iconografía semántica, marca AeroControl e interfaz
  bilingüe ES/EN.
- Flujo de documentos: creación, versionado, reemplazo y descarga
  autenticada.
- Roles estándar (`bootstrap_roles`) con permisos por operación; pruebas
  de autorización (403) en escritura.
- Respaldo local con manifiesto, checksum SHA-256 y verificación;
  restauración con protección contra sobrescritura accidental.
- Entorno reproducible con `uv`, `pytest`, `ruff`, `bandit`, `pip-audit`,
  CI (GitHub Actions) y Dependabot.
- Importación validada de datos oficiales (Capítulo 1): centros de costo,
  aeronaves y operadores, con vista previa y reversión transaccional.
- API DRF de solo lectura + escritura acotada para tareas Kanban, con
  autenticación por token y documentación OpenAPI.

[Unreleased]: https://github.com/DovaCrii/AeroControl/compare/v0.4.0-beta...HEAD
[0.4.0-beta]: https://github.com/DovaCrii/AeroControl/compare/v0.3.0-alpha...v0.4.0-beta
[0.3.0-alpha]: https://github.com/DovaCrii/AeroControl/compare/v0.2.0-alpha...v0.3.0-alpha
[0.2.0-alpha]: https://github.com/DovaCrii/AeroControl/compare/v0.1.0-alpha...v0.2.0-alpha
[0.1.0-alpha]: https://github.com/DovaCrii/AeroControl/releases/tag/v0.1.0-alpha
