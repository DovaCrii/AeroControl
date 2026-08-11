# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto usa versionado `alpha`/`beta`/semántico informal mientras
está en fase de estabilización (ver [MASTER_PLAN.md](MASTER_PLAN.md)).

## [Unreleased]

Trabajo acumulado desde `v0.4.0-beta` (2026-08-04): **59 commits**, de los cuales
30 ya están en `main` y 29 en la pila de ramas de la sesión del 2026-08-11.
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
