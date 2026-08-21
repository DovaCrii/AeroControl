# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto usa versionado `alpha`/`beta`/semántico informal mientras
está en fase de estabilización (ver [MASTER_PLAN.md](MASTER_PLAN.md)).

## [Unreleased]

### Added

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

### Changed

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

### Changed

- **La bandeja de alertas abre en lo que hay que hacer (`LV-118`).** Abría
  mostrando **todo**, resuelto incluido, así que la pantalla de trabajo diario
  mezclaba los pendientes con el historial. Ahora abre en **"Sin resolver"** y
  ordena por urgencia —lo vencido hace meses arriba, no lo que vence en 30
  días—, con el color de cada fila bajando de intensidad según el tramo. Lo
  resuelto **no se borró ni se escondió**: sigue a un clic en el filtro, que es
  donde corresponde para una evidencia de auditoría.

### Fixed

- **El registro DGAC de una aeronave ya se puede subir (`LV-121`).** El tipo
  "Registro / matrícula de aeronave" exigía una fecha de vencimiento, pero el
  certificado que emite la DGAC **no la trae** — es una inscripción, no una
  vigencia. Había que inventar un vencimiento para poder adjuntar el PDF, y esa
  fecha inventada terminaba generando una alerta por algo que no caduca. Ahora
  el tipo no la pide. Los tipos que sí vencen (seguros, credenciales,
  resoluciones) la siguen exigiendo igual.
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
