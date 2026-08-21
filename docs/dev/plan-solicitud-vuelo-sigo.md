# Solicitud de vuelo SIGO: del KMZ a la petición, con seguimiento — 2026-08-20

> **Pedido del usuario, prioridad máxima.** Textual: *"es en la planificación de
> vuelo en conjunto con el permiso de vuelo, en la etapa ahora más pulida, con el
> proceso completo como se debe hacer […] será lo mejor del MVP: debe estar
> cruzado, tener barra de progreso accesible, un flujo claro y tener el
> seguimiento de lo que solicita, además dejar la trazabilidad clara — no es
> necesario la comparación entre modificaciones pero sí dejar nota de los
> cambios"*. Evidencia aportada: capturas del formulario real de SIGO
> ("Información Vuelo") y el KMZ real de MLP
> (`Tabla_Coordenadas_Quebradas_STR_MLP_radio_30m.kmz`).

## 1 · El proceso real, leído de las capturas

SIGO → Solicitud de vuelo → **"Información Vuelo"**, tipo **"OPERACIÓN ÁREA NO
POBLADA"**. Lo que el formulario pide, en orden:

1. **Pares (Área de Trabajo, Objetivo del Vuelo)** — se eligen de dos listas y
   se agregan a una tabla; puede haber más de un par por solicitud.
2. **Comuna** y **Área** (texto libre).
3. **Aeródromo más Cercano (AMC)** — de la lista de SIGO — y **Distancia al AMC
   en kilómetros**.
4. **Punto Centro** — latitud y longitud **en grados, minutos y segundos**, en
   seis casillas separadas.
5. **Radio** (metros o millas náuticas) y **Altura** (metros o pies).
6. **Hora Desde / Hora Hasta**.
7. **Mapa**: un KMZ de **20 MB máximo** que debe contener **una sola
   circunferencia con su punto central**.

La restricción que da forma a todo: **una solicitud por circunferencia** ("solo
puede ser de una en una"). El trabajo real llega al revés — el KMZ de MLP trae
**47 pares punto+círculo** (39 quebradas + 8 botaderos, carpetas
`Puntos` / `Radios de 30 m`) — así que hoy preparar las solicitudes significa
abrir Google Earth, aislar círculo por círculo, convertir coordenadas a GMS a
mano, estimar la distancia al aeródromo y transcribir. **Ese trabajo manual es
lo que esta etapa elimina.**

## 2 · Lo que AeroControl hace con esto

Por cada KMZ multi-círculo que se sube:

1. **Separar en secciones**: cada punto con su circunferencia, conservando el
   nombre real ("Quebrada km 13.760").
2. Por sección, calcular y mostrar **la hoja SIGO**: todo lo que el formulario
   pide, en el formato en que lo pide, listo para copiar casilla por casilla —
   centro en GMS (grados/minutos/segundos separados, con hemisferio), radio en
   metros estimado del polígono real, **AMC más cercano y distancia en km**, y
   el **KMZ individual descargable** (una circunferencia + su punto, <20 MB).
3. **Registrar la solicitud** con los campos restantes (pares
   trabajo/objetivo, comuna, área, horario, altura) y llevarle **flujo con
   barra de progreso**: preparada → ingresada en SIGO → **vinculada al permiso
   de vuelo** que la DGAC responda.
4. **Trazabilidad**: notas de cambio append-only (quién, cuándo, qué nota) —
   sin comparación entre versiones, por decisión explícita del usuario.

## 3 · Lo que ya existe y se reusa (nada de esto se reescribe)

| Pieza | Dónde | Qué aporta |
|---|---|---|
| Parser KML/KMZ endurecido | `apps/geo/kml/` (`parse`, `kmz`, `canonical`) | Leer el KMZ multi-círculo con los límites y defensas ya probados (GEO-1) |
| Generador KML | `apps/geo/kml/build.py` | Escribir el KMZ individual de cada sección — falta sólo el envoltorio ZIP (`build_kmz`) |
| Documento canónico versionado | `GeoPlanVersion` | El patrón de guardar geometría como JSON en la base y generar el archivo al vuelo — las secciones no multiplican archivos en disco |
| Stepper de estados | `StatusFlowMixin` (`LV-72`) | La misma barra de progreso que ya tienen permiso, seguro y mantención |
| Historial de estados | `track_status_changes` + patrón `GeoPlanHistory` | Quién movió cada paso, cuándo y en qué rol |
| Vínculo plan↔permiso | `GeoPlanPermissionLink` (OPS-7) | El patrón append-only para "cuándo se vinculó y a cuál" |
| Ubicación estructurada del permiso | `FlightPermission` (OPS-4: lat/lon/radio/altura/comuna) | La solicitud aprobada **rellena** el permiso, no lo duplica |
| Vocabulario cerrado + catálogo editable | `PURPOSE_CHOICES` (R3.1), `DocumentType`/`QualificationType` | El molde para los catálogos de SIGO |

## 4 · Diseño

### 4.1 · Motor de secciones — `apps/geo/sections.py` (R9.1)

Funciones puras sobre el documento canónico, sin modelos ni vistas:

- **`split_sections(document)`** → lista de secciones `(nombre, centro,
  radio_m, punto, polígono, avisos)`. Empareja cada punto con su circunferencia
  por **cercanía del centroide del polígono al punto** (el nombre no es
  confiable: en el KMZ real los polígonos viven en otra carpeta). Un punto sin
  círculo o un círculo sin punto **no se descarta ni se inventa**: sale como
  sección con aviso, porque un KMZ a medias debe verse a medias.
- **`estimate_radius_m(centro, anillo)`** → media de las distancias
  centro→vértices. Si la dispersión supera un umbral, aviso: "esto no es una
  circunferencia" — SIGO exige círculo, y callarlo entregaría una solicitud
  inválida.
- **`to_dms(grados_decimales, eje)`** → (grados, minutos, segundos, hemisferio)
  — las seis casillas de SIGO tal cual, sin signo (el hemisferio va aparte,
  como letra).
- **`haversine_km(a, b)`** → distancia geodésica. Sin dependencia nueva: para
  distancias AMC (decenas–cientos de km) el error de la esfera es irrelevante
  frente al requisito.
- **`build_section_document(sección)`** → documento canónico mínimo (punto +
  polígono) que `build_kml_bytes` convierte en el KMZ individual.

### 4.2 · Catálogo de aeródromos (R9.2)

Modelo `Aerodrome` en `registry` (es padrón de referencia): `code` (OACI,
único), `name`, `latitude`/`longitude` **opcionales**, editable en la app.
Comando `seed_aerodromes` idempotente por `code` con **la lista extraída de las
capturas de SIGO** — decisión del usuario: *"son solo esas las disponibles de
momento, se debe respetar"*. La lista de SIGO es global (trae Abu Dhabi y
Taranto); el cálculo de cercanía sólo considera **los que tienen coordenadas**,
y la pantalla dice cuántos quedan fuera por no tenerlas.

**Coordenadas: sólo verificables.** El seed trae coordenadas únicamente para
los aeródromos chilenos de posición conocida y notoria (SCEL, SCFA, SCER, SCQP,
SCTC, SCBA); el resto queda en blanco para completar desde la ficha. **Antes
del primer uso real, la persona verifica el AMC elegido contra la carta AIP** —
la app calcula y propone, el papel manda (misma regla que `LV-93` dejó
escrita: hay que decir cuál papel arbitra qué).

### 4.3 · La solicitud — `FlightRequest` en `operations` (R9.3)

Una fila por sección/solicitud SIGO. Campos espejo del formulario:

- `request_type` (vocabulario cerrado; hoy sólo "Operación área no poblada" —
  las capturas no muestran otro, y no se inventa lo que no se vio).
- `work_pairs`: lista de pares (trabajo, objetivo) de los dos vocabularios
  sembrados de las capturas — **Área de Trabajo**: Agrícolas (Cap. E DAN 137),
  Fotografía y Filmación Aérea (Cap. J), Instrucción de Vuelo (Cap. G), Otros,
  Publicidad y Propaganda Aérea (Cap. H); **Objetivo del Vuelo**: Batimetría,
  Fotografía y Filmación, Fotogrametría, Inspección AT, Inspección Obras
  Civiles, Magnetometría, Termografía Aérea, Vigilancia Aérea. Catálogos
  editables: la lista visible en las capturas estaba cortada arriba, y cuando
  aparezca un valor nuevo en SIGO se agrega desde la app, no con un despliegue.
- `commune`, `area_name`, `hour_from`, `hour_to`, `altitude_m`.
- Lo geométrico: `center_lat`, `center_lon`, `radius_m`, `section_content`
  (canónico JSON de la sección; el KMZ se genera al descargar), `source_plan`
  (FK a `GeoPlan`, opcional — de qué KMZ madre salió).
- `amc` (FK `Aerodrome`) + `amc_distance_km` — **propuestos por cálculo,
  editables**: guardar lo que la persona confirmó, no lo que la fórmula dijo.
- `flight_permission` (FK opcional) — el cruce con el permiso.
- `status` + `STATUS_FLOW` → la barra de progreso.

### 4.4 · El flujo (R9.4)

```
Preparada ──> Ingresada en SIGO ──> Vinculada al permiso ──> Cerrada
   │                                        (la DGAC respondió: el permiso
   └── (editable)                            existente toma el mando)
```

- **La solicitud no reemplaza al permiso.** El permiso sigue siendo el espejo
  del papel DGAC (`LV-64`, `LV-101`); la solicitud es la *preparación* y el
  *seguimiento de lo pedido*. Al vincularla, rellena la ubicación estructurada
  del permiso (OPS-4) en vez de duplicarla.
- **Notas de cambio**: `FlightRequestNote` append-only (autor, fecha, texto).
  Sin diff entre versiones — decisión del usuario. El historial de estados lo
  escribe la señal compartida, como en permiso/seguro/mantención.
- **Seguimiento**: el listado agrupa por estado; una solicitud "Ingresada en
  SIGO" hace visible cuánto lleva esperando (mismo espíritu que el estado
  `filed` del seguro, `LV-81`).

### 4.5 · Lo que NO se hace, y por qué

- **No se envía nada a SIGO automáticamente.** SIGO no expone API; la app
  prepara y la persona copia. Automatizar el navegador sería frágil y opaco.
- **No se comparan versiones de la solicitud** (decisión del usuario). Notas sí.
- **No se dibuja mapa** en esta etapa: el visor del plan geoespacial ya existe;
  la sección enlaza al plan madre.
- **No se inventan aeródromos ni coordenadas** fuera de lo verificable.

## 5 · Fases y estado

| Fase | Qué entrega | Estado |
|---|---|---|
| **R9.1** | Motor de secciones (`split_sections`, radio, GMS, haversine, KMZ individual) + `build_kmz` + tests contra la estructura del KMZ real | ✅ hecho 2026-08-20, 19 tests. El KMZ de MLP procesado como verificación |
| **R9.2** | `Aerodrome` + `seed_aerodromes` (lista de las capturas) + `nearest_aerodromes` | ✅ hecho 2026-08-20, 8 tests. Migración `registry/0035` |
| **R9.3** | `FlightRequest` + catálogos SIGO + `create_requests_from_plan` + `sigo_sheet` + `section_kmz` | ✅ modelo y servicios hechos 2026-08-20, 19 tests. Migración `operations/0019`. **Falta la capa de pantallas** |
| **R9.4** | Flujo con stepper, vínculo a permiso (rellena OPS-4), notas de cambio, historial | ✅ modelo y servicios hechos 2026-08-20. `link_to_permission` rellena sin pisar; quinto usuario de `track_status_changes`. **Falta la capa de pantallas** |
| **R9.5** | Vistas, plantillas y menú · vista previa de separación · hoja SIGO · descarga del KMZ · vínculo desde la pantalla | ✅ hecho 2026-08-20, 23 tests. Verificado en el navegador con el KMZ real |
| **R9.6** | El expediente del permiso muestra su solicitud de origen · el panel muestra lo presentado y sin respuesta, con los días de espera | ✅ hecho 2026-08-20, 12 tests. Verificado en el navegador |

**Con R9.6 el bloque R9 queda cerrado.** El círculo completo: el KMZ entra, se
separa, cada sección se prepara y se presenta, el panel persigue lo que espera
respuesta, y cuando la DGAC contesta la solicitud se vincula al permiso — cuyo
expediente ya puede responder *"¿la DGAC autorizó lo que pedimos?"*.

### Dos decisiones de R9.6

- **La espera no es una alerta.** El motor de alertas vigila **vencimientos**, y
  una solicitud presentada no vence: espera. Va en el panel, como la mantención
  sin planificar de `LV-8e` — una ausencia que ninguna regla de fecha puede ver.
- **Sin umbral de "atrasada".** Se cuentan todas las presentadas y se muestran
  los días de cada una, ordenadas de más antigua a más reciente. Poner "atrasada
  a los N días" exigiría un plazo de respuesta de la DGAC que nadie confirmó, y
  un umbral inventado que resulta corto enseña a ignorar la tarjeta.
- **Un permiso sin solicitud es "por confirmar", no "faltante".** Todos los
  permisos que existen hoy se tramitaron antes de que la app registrara la
  solicitud; marcarlos incompletos los declararía defectuosos de forma
  retroactiva por una función que no existía. Mismo criterio que `LV-107` aplicó
  al plan geoespacial.

**Verificado de punta a punta con el archivo real** (2026-08-20), contra la base:
el KMZ de MLP produce **47 solicitudes**, las 47 con AMC propuesto
(`SCER - Ad. Militar Quintero`, 125.9 km), la hoja SIGO entrega las seis
casillas (`31° 53' 39.81" S` / `70° 42' 7.95" W`), el KMZ adjunto son 794 bytes
con exactamente un punto y un polígono, y al vincular rellenó cinco campos del
permiso (`latitude`, `longitude`, `radius_km`, `commune`, `max_altitude_ft`)
dejando el historial `prepared → filed → linked`.

### Decisiones que aparecieron al implementar

- **La distancia al AMC se congela**, no se recalcula al mostrar: es el número
  que se escribió en el formulario del Estado, y corregir mañana la coordenada
  de un aeródromo no puede cambiar lo que dice una solicitud ya presentada.
  Misma lección que `LV-118` dejó en la bandeja de alertas.
- **`link_to_permission` rellena, nunca pisa**: si el permiso ya trae una
  coordenada puede venir del papel DGAC, que tiene más autoridad que lo
  preparado antes de presentar.
- **Dos `msgctxt` nuevos**: "Filed in SIGO" y "Closed" ya existían en el
  catálogo en masculino (el seguro, el contrato de un centro de costo) y acá el
  sujeto es *la solicitud*. Tercera vez que la misma palabra inglesa cae en dos
  géneros del español; el patrón ya estaba (`LV-61`, `LV-83`).
- **El KMZ de sección se genera al descargar**, no se guarda: 47 solicitudes
  serían 47 binarios reconstruibles exactamente desde el canónico.
- **No hay "+ Nueva solicitud".** Una solicitud nace de separar un KMZ; el
  formulario en blanco obligaría a tipear el centro y el radio —el trabajo que
  este flujo quita— y dejaría la solicitud sin el adjunto que SIGO exige.
- **La vista previa es obligatoria antes de crear.** Con el archivo real son 47
  filas de las que 6 traen problema de dato; crear sin mirarlas enterraría ese
  hallazgo bajo las otras 41.
- **Un plural sin traducir pasa el gate y se ve en inglés.** El test del
  catálogo mira los literales de `{% translate %}`, no los `blocktranslate` con
  `count`, que gettext guarda como `msgid_plural`. Se descubrió mirando la
  página, no la suite: el encabezado decía *"This plan yields 47 flight
  requests"* dentro de una interfaz en español. Las cuatro entradas plurales
  quedaron en el catálogo a mano.

## 5b · Lo que el KMZ real destapó al primer uso

Procesar `Tabla_Coordenadas_Quebradas_STR_MLP_radio_30m.kmz` con el motor
encontró **tres pares de puntos sobre coordenadas idénticas**:

| Puntos | Lectura |
|---|---|
| `Quebrada km 29.832 (registro 1)` y `(registro 2)` | Duplicado declarado en el propio nombre; probablemente intencional |
| **`Quebrada km 46.272` y `Quebrada km 46.924`** | **Quebradas distintas —650 m según sus nombres— en el mismo lugar: una fila mal transcrita en la tabla de origen** |
| `Botadero 7` y `Botadero 8` | Mismo caso |

El segundo y el tercero son errores de dato que habrían viajado al formulario
del Estado: la solicitud se presentaría por el sitio equivocado. El motor no
puede saber cuál de los dos dice la verdad, así que marca **el grupo completo**
con `duplicate_center` y lo arbitra la persona contra la tabla.

Dos defectos del propio motor salieron de acá y quedaron con test: un
rectángulo pasaba por circunferencia (sus cuatro esquinas equidistan del
centro — se miden también los puntos medios de las aristas), y los puntos
coincidentes rompían el emparejamiento (ambos círculos reclamaban el mismo
punto y uno quedaba huérfano al lado de su gemelo).

## 6 · Verificación contra el caso real

El KMZ de MLP (47 pares en `Quebradas (39)` + `Botaderos (8)`) es el caso de
aceptación de R9.1: separar debe producir **exactamente 47 secciones**, cada
una con nombre real, radio ≈30 m (el archivo lo declara en su propio nombre), y
ningún aviso de desemparejado. Cualquier cambio futuro al motor corre contra
esa estructura (sintética, en tests) antes de tocar producción.
