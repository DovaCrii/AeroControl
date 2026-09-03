# Plan UX/UI — AeroControl

> **Qué es este documento.** Una revisión del diseño completo de la aplicación —del
> login a la última opción de trabajo del menú—, las decisiones de mejora que salen
> de ella, y el orden en que conviene ejecutarlas. Se escribió el **2026-09-02**
> leyendo el código real: `templates/` (110 plantillas), `static/css/app.css`
> (2.571 líneas), `static/js/` y las rutas de `config/urls.py`.
>
> **No es autoritativo.** La fuente única de verdad del trabajo pendiente sigue
> siendo [MASTER_PLAN.md](../MASTER_PLAN.md). Las filas que se aprueben de acá se
> capturan allá con su ID `UX-nn`.
>
> **Qué no repite.** El eje competitivo *funcional* ya está analizado en
> [docs/dev/analisis-competencia-2026-08-14.md](dev/analisis-competencia-2026-08-14.md)
> y su conclusión sigue en pie: la única brecha funcional grande es la ingesta de
> vuelos (`X.4`). Este documento mira el otro eje —**cómo se ve y cómo se
> trabaja**— y sólo vuelve al mercado en §5, donde hay algo nuevo.

---

## 1 · Veredicto, en una página

**AeroControl no tiene un problema de diseño. Tiene un problema de escala del
diseño.**

Cada pantalla, mirada sola, está mejor resuelta que el promedio de una aplicación
interna: hay *skip link*, `focus-visible` en todos los controles propios,
`aria-expanded` escrito en la plantilla y no sólo en el JS, contrastes **medidos**
y anotados en el CSS con su ratio, estados vacíos con acción, y un nivel de
justificación por decisión —los comentarios `LV-nn`— que casi ningún producto
comercial tiene. Eso hay que decirlo antes de cualquier crítica, porque cambia el
tipo de trabajo que sigue: **no hay que rehacer, hay que consolidar.**

El problema aparece cuando se miran las pantallas *juntas*. Ahí se ve que:

1. **El sistema de diseño existe a medias.** Hay tokens de superficie, texto y
   color de acción (`--ac-*`), pero **no hay tokens de severidad**. El estado se
   escribe con utilidades de Bootstrap (`bg-success`, `bg-warning-subtle`,
   `badge bg-danger`) y el tema oscuro se repara después con **quince reglas `!important`**, una por insignia. Consecuencia concreta: "ámbar" no
   está garantizado que signifique lo mismo en la tabla de alertas, en el panel y
   en el mapa. En una aplicación de cumplimiento aeronáutico eso no es estética,
   es seguridad operacional.

2. **El título de página se dibuja de tres tamaños distintos.** `.page-header h1`
   pide `clamp(1.65rem, 2vw, 2.2rem)`; las pantallas que no usan ese contenedor
   —`generic/detail.html`, `alert_list.html`, `permission_detail.html`— renderizan
   `h1.h3` a 1.75 rem; y `core/administration.html`, `core/audit_log.html` y
   `core/users_roles.html` usan un `<h1>` pelado, que Bootstrap dibuja a 2.5 rem.
   Nadie lo decidió: es deriva.

3. **Hay seis funciones vivas que no están en el menú.** `document-list`,
   `qualification-list`, `kanban`, `calendar`, `flight-request-list` y
   `deliverable-list` conservan vista, URL, permisos y pruebas, y salieron del
   menú por decisiones documentadas y correctas (LV-7, LV-D8, LV-69, LV-78,
   LV-103, LV-150). Cada retiro fue razonable por separado; el saldo acumulado es
   que **una parte del producto sólo se alcanza escribiendo la URL a mano**. Eso
   necesita un lugar, no un octavo retiro.

4. **El listado no escala.** Sin orden por columna, sin columnas configurables,
   sin densidad conmutable, sin vistas guardadas y sin acciones en lote. Con 14
   aeronaves y 41 operadores no se nota. Con 400 filas de bitácora de vuelo —que
   es exactamente adonde va esto cuando `X.4` cierre— se nota el primer día.

5. **En móvil la aplicación se encoge, no se adapta.** La búsqueda global
   desaparece por completo (`d-none d-md-flex`), y una tabla de siete columnas en
   390 px se convierte en desplazamiento horizontal. El operador en faena —que es
   quien más necesita consultar si puede volar— es el usuario peor servido.

6. **No hay retroalimentación moderna de carga ni de éxito.** El indicador de
   búsqueda es la palabra "Buscando…", no hay *skeletons*, y al guardar en un
   modal el código hace `window.location.reload()`: la página entera se rehace y
   se pierde el punto donde estabas.

**La tesis del plan:** las seis cosas de arriba se arreglan con **un sistema de
diseño explícito y tres componentes compartidos** (encabezado de página, tabla de
trabajo, bandeja). No con un rediseño. El presupuesto estimado es de **3 a 5
sesiones de trabajo**, y la mayor parte del cambio ocurre en `app.css` y en cuatro
plantillas genéricas, no en 110.

---

## 2 · El recorrido, pantalla por pantalla

Se recorrió en el orden en que lo recorre una persona: entrar, mirar el panel,
abrir un listado, entrar a una ficha, resolver algo, planificar, y producir un
documento.

### 2.1 · Login — `templates/registration/login.html`

**Lo que está bien.** Es la única pantalla con su propio `<style>` embebido, y por
una vez eso es correcto: no hereda la barra ni el menú, carga rápido, y sus
variables (`--login-*`) están declaradas con su variante oscura completa. El foco
tiene `outline` de 3 px, los campos miden 44 px de alto (por encima del mínimo
táctil), y el error tiene `role="alert"` con `aria-live="assertive"`.

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| a | **No hay "mostrar contraseña".** | En un teclado táctil, en faena, con guantes, escribir una contraseña a ciegas es la primera fricción del día. Es un botón y ocho líneas de JS. |
| b | **No hay "olvidé mi contraseña".** | `password_change` existe (V.12) pero exige estar dentro. Quien queda fuera depende de que alguien entre al `/admin/`. |
| c | **La paleta del login no es la de la app.** `--login-accent: #087f78` está escrito a mano, duplicando `--ac-primary`. | Dos fuentes para el mismo color es exactamente la deriva que el propio CSS documenta haber sufrido con los `:root` duplicados. |
| d | **`?v=20260724-legibility` sobrevive sólo acá.** `base.html` carga `app.css` sin versión. | En producción `ManifestStaticFilesStorage` ya versiona por hash, así que el parámetro no hace nada. Es ruido que sugiere una política que no existe. |
| e | **No dice dónde está.** La leyenda es "Centro de Control de Operaciones Aéreas". | En una instalación local-first, quien entra necesita saber a **qué** instancia entra (`p340`, local, respaldo). Una línea con el entorno evita la peor equivocación posible: cargar evidencia en la máquina equivocada. |

### 2.2 · Panel — `templates/dashboard/index.html`

**Lo que está bien, y mucho.** Es la mejor pantalla de la aplicación y no por
poco. La tira de *readiness* contesta *"¿puedo operar hoy?"* con **fracciones y
faltante nombrado** en vez de porcentajes sueltos (LV-89), separa "vencido" de
"sin fecha" porque se arreglan distinto (LV-129), y agrega "esperando aprobación"
como tercer término porque espera a un tercero (LV-201). La regla de **ocultar
en cero salvo Alertas** (LV-122/R9.6) es exactamente la decisión correcta: una
tarjeta en cero todos los días enseña a no mirar la fila. El estado de
incorporación (`show_onboarding`) y la franja de activación de cumplimiento son
onboarding por *default* inteligente, que es el patrón que el mercado premia hoy.

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| f | **No hay "qué hay volando ahora".** El panel responde por vigencias y trabajo pendiente, no por actividad. | Es el elemento que distingue un panel de cumplimiento de un **centro de operaciones**. Con permisos vigentes y vuelos del día ya en la base, un contador "N operaciones hoy · M permisos vigentes" es una consulta, no una función nueva. |
| g | **El panel no tiene dueño.** Muestra el estado de la organización, no el trabajo de quien mira. | Un jefe de operaciones y un encargado de cumplimiento ven exactamente lo mismo. La bandeja personal (§3.3) es la respuesta. |
| h | **El clima no declara su frescura.** | Un dato meteorológico sin hora de consulta, presentado como actual, es un riesgo operacional, no un detalle de interfaz. |
| i | **Un solo filtro (faena) y sin memoria.** | Quien trabaja siempre la misma faena la elige todos los días. |
| j | **Las cifras no usan `tabular-nums`.** | `.summary-card strong` mide 2 rem: con cifras proporcionales, `11/14` y `8/16` no alinean entre tarjetas contiguas. Es una línea de CSS. |

### 2.3 · Listados — `templates/generic/list.html` y las 26 pantallas que lo usan

**Lo que está bien.** La búsqueda es incremental por HTMX con `delay:300ms` y
`hx-push-url` (la URL queda compartible), la paginación se actualiza *fuera de
banda* en el mismo intercambio (F-13), los botones Ver/Editar sólo aparecen si la
ruta **resuelve de verdad** (`has_detail_url`, tras cuatro listas que daban 404), y
el estado vacío distingue "no hay nada" de "el filtro no encontró nada" y ofrece
la acción correspondiente. Ese estado vacío es mejor que el de la mayoría de los
productos comparados.

**Lo que falta.** Esto es el núcleo del plan.

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| k | **Sin orden por columna.** | Es la primera cosa que una persona intenta en una tabla. Que no responda enseña que la tabla no es interactiva, y deja de intentarse el resto. |
| l | **Sin columnas configurables ni densidad conmutable.** | La tensión es real y está documentada en el propio CSS: la lista de alertas ya llegó a siete columnas y `LV-146` tuvo que meter la faena como *chip* en segunda línea para no gatillar desplazamiento horizontal. Eso es un síntoma, no una solución. |
| m | **Sin vistas guardadas.** | "Aeronaves con seguro vencido", "operadores con credencial venciendo en 60 días" y "permisos presentados sin respuesta" son consultas que se repiten cada semana y hoy se rearman a mano. |
| n | **Sin selección múltiple ni acciones en lote.** | Existe carga múltiple de documentos (LV-86) pero no archivar, exportar ni resolver en lote. |
| o | **La paginación no dice cuántos hay.** | `page_obj` tiene `paginator.count`. "Mostrando 21–40 de 137" es una línea de plantilla y cambia por completo la sensación de control. |
| p | **En móvil la tabla es desplazamiento horizontal.** 26 plantillas usan `table-responsive` y ninguna tiene alternativa apilada. | Siete columnas en 390 px no se leen. El patrón correcto es que bajo cierto ancho cada fila sea una tarjeta con las 3 columnas que importan. |
| q | **"Exportar CSV" está en el encabezado, junto a la acción primaria.** | Exportar es una acción de la *tabla* (respeta los filtros), no de la página. Compite visualmente con "+ Nuevo", que es lo que la persona vino a hacer. |

### 2.4 · Fichas de detalle — `generic/detail.html`, `aircraft_detail.html`, `operator_detail.html`, `permission_detail.html`

**Lo que está bien.** El patrón de ficha está bien pensado: identidad arriba con
su insignia de archivado, acciones a la derecha, tabla de campos, y luego
secciones apiladas por tema (seguro, documentos, mantención). El componente
`generic/_traceability.html` —los pasos del trámite más su historial— es el mejor
componente propio de la aplicación y ya se reutiliza en permisos, seguro JAC y
planes geo. `.status-step` incluso se apila en vertical bajo 576 px con el
conector corriendo por el borde izquierdo. Eso es diseño de verdad.

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| r | **Sin migas de pan.** El único camino de vuelta es "← Volver a la lista". | Llegando desde una alerta, desde el correo o desde la búsqueda global, no hay forma de saber en qué rama del menú estás parado. |
| s | **La ficha crece hacia abajo sin índice.** `aircraft_detail` apila cinco tarjetas; `plan_detail` tiene 440 líneas. | `app.js` ya sabe abrir pestañas por `#tab-…` (LV-40), pero sólo algunas fichas las usan. Falta decidir: o todas apiladas con índice lateral, o todas en pestañas. Hoy conviven las dos formas. |
| t | **Las acciones destructivas y las neutras se ven parecido.** "Editar" (`btn-outline-primary`) y "Archivar" (`btn-outline-danger`) tienen el mismo peso. | Archivar tiene confirmación en los flujos críticos (LV-135), pero la jerarquía visual debería decir antes lo que la confirmación dice después. |
| u | **La tabla de campos muestra todo por igual.** | En una ficha de aeronave, la matrícula, el estado y el vencimiento del seguro no valen lo mismo que el número de serie del payload. Falta una capa de "identidad y estado" antes del volcado de campos. |

### 2.5 · Alertas — `templates/compliance/alert_list.html`

Es la pantalla que el usuario declaró que trabaja a diario ("me estoy guiando de
alertas principalmente", LV-103), y por eso merece el escrutinio más duro.

**Lo que está bien.** La fecha que se muestra es la **congelada al disparar la
alerta** y no la que el registro tiene hoy (LV-118) — un detalle que casi
cualquier implementación equivoca y que aquí está resuelto y explicado. El motivo
de resolución tiene columna propia porque es evidencia ISO 10.2 y no una nota al
pie (LV-110). La entidad enlaza a su ficha, que es donde se resuelve. La
verificación de eficacia acompaña a "Resuelta" en vez de reemplazarla, porque son
dos afirmaciones distintas (R7.6).

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| v | **No usa `.page-header`.** Es un `d-flex` a mano, con `h1.h3`, sin *eyebrow* ni descripción. | La pantalla más visitada de la aplicación es la que peor sigue el patrón que el resto ya adoptó. |
| w | **La severidad se lee en dos columnas distintas.** "Vencimiento" trae el color de urgencia; "Resolución" trae el estado. | El ojo tiene que cruzar dos celdas separadas por una tercera para saber qué tan urgente es una fila. Un indicador de severidad en el **borde izquierdo de la fila** resuelve eso sin agregar columna. |
| x | **No hay orden por urgencia visible ni agrupación por tramo.** | Con 40 alertas, "vencido" y "vence en 28 días" conviven en la misma lista plana. |
| y | **Sin resolución en lote y sin dueño.** | Renovar una póliza que cubre cuatro aeronaves son cuatro modales. LV-68 quitó bien la resolución en lote *agrupada por fecha* porque la premisa era falsa; una **selección explícita** por casilla no tiene ese problema. |
| z | **El estado vacío es "No alerts found."** | Es la única pantalla donde el vacío es una **buena noticia** y se comunica como un error de búsqueda. Debería decir "Nada pendiente" y ofrecer ver las resueltas del mes. |

### 2.6 · Planificación geoespacial — `templates/geo/plan_detail.html`

**Lo que está bien.** Es la pantalla más ambiciosa y la que mejor resuelve la
tensión entre isla de JavaScript y cáscara servida por Django, siguiendo la regla
escrita en [docs/frontend-boundary.md](frontend-boundary.md). El encabezado usa
el patrón bueno (eyebrow con folio, título calculado, tercera línea con faena y
permiso enlazado). El mapa creció de 480 px fijos a `clamp(480px, 68vh, 900px)`
(LV-136). El botón "Separar" sólo aparece cuando hay algo que separar (R10.1). La
hoja de campo SIGO copia casilla por casilla (LV-149).

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| aa | **WCAG 2.2 §2.5.7 (movimientos de arrastre).** Editar vértices con Geoman es arrastre puro. | Es criterio **AA** desde 2.2 y exige alternativa de un solo puntero. En un editor de mapas la salida honesta es una tabla de coordenadas editable al lado del lienzo — que además sirve para transcribir a SIGO, o sea que paga dos veces. |
| bb | **440 líneas en una plantilla.** | Es la única pantalla donde la complejidad ya se nota en el archivo. Extraer parciales por sección la volvería mantenible sin cambiar nada visible. |
| cc | **El panel de capas mide 240 px fijos y el mapa no tiene modo pantalla completa propio.** | En un portátil de 1366 px el mapa efectivo queda estrecho: 280 de menú + 240 de panel. |

### 2.7 · Permisos, vuelos y mantención

**Lo que está bien.** `LV-154` resolvió el borrador local del formulario de
permiso —el más largo de la aplicación— con la decisión correcta explicada
(vive en el navegador, no como fila incompleta en la base). `LV-222` cambió el
roster de operadores de multicolumna a rejilla porque en multicolumna nada
relaciona la altura de un elemento con la de su vecino: ese diagnóstico es
correcto y la solución también. La mantención registra el camino real
casa↔taller (LV-82).

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| dd | **El borrador existe sólo en el formulario de permiso.** | El resto del CRUD vive en un modal único (`#generic-modal`) del que se sale con `data-bs-dismiss` **sin aviso**: lo tipeado se pierde en silencio. El patrón bueno ya está escrito; falta generalizarlo o, como mínimo, poner la guardia de "hay cambios sin guardar". |
| ee | **Formularios largos dentro de un modal `modal-lg`.** | Un roster de 40 operadores con `max-height: 15rem` y scroll propio, dentro de un modal que también hace scroll, dentro de una página que hace scroll: tres barras anidadas. Los formularios de más de ~8 campos deberían abrirse en página completa y dejar el modal para lo corto. |
| ff | **Sin `inputmode`, `enterkeyhint` ni `autocomplete`** en ningún campo (verificado: cero apariciones de `inputmode` en `templates/`). | En un teléfono, un campo de horas o de RUT abre teclado alfabético. Es un atributo por campo y no cambia nada en escritorio. |
| gg | **Sin "guardar y crear otro".** | Cargar cinco vuelos seguidos son cinco viajes de ida y vuelta al listado. |

### 2.8 · Informes y catastro — `compliance/report.html`, `registry/catastro.html`

**Lo que está bien.** Es el mejor encabezado de la aplicación y el modelo a
copiar: *eyebrow* + título + descripción a la izquierda, y los cuatro formatos de
salida (PDF, Excel, Word, CSV) a la derecha, todos arrastrando los filtros
aplicados. Los filtros tienen `<label for>` de verdad. Las tarjetas de resumen
usan el mismo componente que el panel.

**Lo que falta.**

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| hh | **No hay `@media print`** en las 2.571 líneas de `app.css` (verificado: cero apariciones). | Quien imprime el informe desde el navegador se lleva el menú lateral, la barra superior y los botones de exportación en el papel. Es el uso más probable de esta pantalla después de exportar. |
| ii | **Cuatro botones de formato con el mismo peso visual.** | Tres son `btn-outline-primary` y uno `btn-outline-secondary` sin criterio evidente. Uno debería ser el recomendado. |
| jj | **El informe no dice cuándo se generó ni con qué filtros, en pantalla.** | El archivo exportado sí lo lleva; la pantalla es la que se muestra en una reunión. |

### 2.9 · Centro de administración — `templates/core/administration.html`

**Lo que está bien.** La decisión de lista agrupada en vez de rejilla 2×2 está
explicada y es correcta (las alturas de tarjeta dependían de si un título se
partía). Y **es la única pantalla que usa un sprite SVG** (`<symbol>` con `<use>`)
en vez de repetir los `path` inline. Ese es el patrón correcto y debería ser el
de toda la aplicación.

**Lo que falta.** El acceso al `/admin/` de Django convive con el centro de
administración en el mismo menú, sin decir que uno es el operativo y el otro el
técnico. La etiqueta "Administración avanzada técnica" ya existe **dentro** de la
pantalla; el enlace del menú lateral dice sólo "Admin".

### 2.10 · Prueba de conocimientos — `templates/registry/assessment_take.html`

Es, junto al panel, la pantalla mejor diseñada. `LV-163` diagnosticó bien
—"todo pesaba igual, y sin jerarquía el ojo no sabe dónde entrar"— y respondió
con las tres cosas correctas: un solo elemento pesado por pregunta, la opción
entera como superficie clicable con estados, y avance visible con barra. No tengo
observaciones de fondo. La única: 25 preguntas en una página sin autoguardado
significa que un cierre accidental del navegador pierde el intento; el patrón de
`form-draft.js` aplicaría tal cual.

### 2.11 · Móvil y terreno

Esta es la brecha más grande del recorrido, y no es una pantalla: es la ausencia
de una.

| # | Hallazgo | Por qué importa |
| --- | --- | --- |
| kk | **La búsqueda global no existe bajo 768 px** (`d-none d-md-flex`). | Es la herramienta más rápida para llegar a algo, y desaparece justo donde la navegación cuesta más. |
| ll | **No hay PWA**: ni `manifest.json`, ni *service worker*, ni icono instalable (verificado: cero apariciones). | El estándar de mercado para este dominio es aplicación de campo **con modo sin conexión** (Airdata y DroneLogbook lo documentan). AeroControl no necesita una app nativa, pero sí que la faena pueda consultar sin señal lo último que cargó. |
| mm | **No hay pantalla de operador en faena.** | Quien está por volar quiere una sola respuesta —*¿puedo volar esta aeronave, hoy, en esta faena?*— y hoy tiene que armarla cruzando tres pantallas pensadas para escritorio. |
| nn | **La barra superior en móvil pierde el nombre de usuario** (`.navbar > .d-flex > .opacity-75 { display: none }`) pero conserva cuatro controles: cambiar contraseña, idioma, salir y tema. | Cuatro botones de utilidad ocupan la fila que debería llevar la búsqueda. |

---

## 3 · El sistema de diseño objetivo

Nada de lo que sigue es un rediseño. Es escribir explícitamente lo que la
aplicación ya hace bien de forma dispersa, para que deje de poder derivar.

### 3.1 · Tokens en tres capas

Hoy hay **una** capa (semántica, `--ac-*`) y la primitiva está implícita en los
hex escritos a mano. La propuesta:

```
primitivo   →  --c-teal-700: #087f78     (la paleta cruda, nunca se usa directo)
semántico   →  --ac-primary: var(--c-teal-700)
severidad   →  --sev-caution-bg / -fg / -border
componente  →  --badge-caution-bg: var(--sev-caution-bg)
```

**La capa que falta y que más rinde es la de severidad.** Cinco niveles, tomados
del vocabulario aeronáutico que los usuarios ya conocen:

| Token | Significado | Dónde manda |
| --- | --- | --- |
| `--sev-nominal` | Todo al día | Sin destaque. **El estado normal no se celebra.** |
| `--sev-advisory` | Informativo | Insignia discreta, no interrumpe |
| `--sev-caution` | Atención, no inmediata | Ámbar · entra a la bandeja |
| `--sev-warning` | Acción pronta | Rojo · notifica |
| `--sev-critical` | Acción inmediata / no volar | Rojo + bloquea el flujo |

Definidos una vez y usados en: insignia de tabla, borde izquierdo de fila, punto
del mapa, tarjeta del panel y fila de la bandeja. Es lo que garantiza que ámbar
signifique lo mismo en todas partes.

**Regla dura, no negociable: la severidad nunca depende sólo del color.** Siempre
color **+ forma de icono distinta + texto**. Daltonismo, sol directo sobre una
tablet en faena y monitores sin calibrar lo vuelven inseguro, y WCAG 1.4.1 lo
prohíbe. La aplicación ya lo cumple en la mayoría de los casos por accidente
(las insignias llevan texto); esto lo vuelve regla.

**Beneficio colateral medible:** las **quince reglas `!important`** que hoy reparan
el contraste de las insignias en tema oscuro desaparecen — el 50 % de todos los
`!important` del archivo. El tema oscuro
pasa a ser una redefinición de tokens, que es lo que siempre debió ser.

### 3.2 · Tipografía y densidad

| Decisión | Hoy | Propuesta |
| --- | --- | --- |
| Familia | `system-ui` sola | `system-ui` se conserva. **No se agrega fuente web**: local-first, sin CDN, y la ganancia no paga el peso. |
| Cifras | proporcionales | `font-variant-numeric: tabular-nums` en tablas, KPI y fechas. **Una línea de CSS**, efecto inmediato en toda la aplicación. |
| Escala | valores a mano (0.72 / 0.78 / 0.85 / 0.92 / 0.95 rem…) | Seis pasos con nombre: `--fs-xs` a `--fs-2xl`. |
| Espaciado | a mano (0.15 / 0.35 / 0.55 / 0.62 / 0.85 rem…) | Escala de 4 px: `--sp-1` a `--sp-8`. |
| Título de página | **tres tamaños distintos** según si la plantilla usa `.page-header` | Uno solo. `.page-header` obligatorio, con *eyebrow*, título y descripción. |
| Densidad de tabla | fija | Conmutador **cómoda / compacta**, recordado por persona. 40 px y 32 px de fila. |

### 3.3 · Los tres componentes que faltan

**1 · Encabezado de página** (`templates/generic/_page_header.html`). Ya existe
como CSS y como convención en las pantallas nuevas; falta como parcial obligatorio
con cuatro huecos: *eyebrow*, título, descripción, acciones. Migrar las ~15
plantillas que hoy arman su encabezado a mano.

**2 · Tabla de trabajo** (`templates/generic/_worktable.html`). Un solo componente
que resuelva de una vez para las 26 listas: orden por columna, selector de
columnas, densidad, selección múltiple con barra de acciones contextual,
"mostrando N–M de T", y **fila-tarjeta bajo 768 px**. El borde izquierdo de la
fila lleva el token de severidad cuando la lista tiene una.

**3 · Bandeja de trabajo** (`/bandeja/`). La pieza de producto que más cambia la
experiencia y la que el mercado premia. No es una pantalla nueva de datos: es una
vista sobre lo que ya existe —alertas, no conformidades, mantención por definir,
permisos esperando respuesta, entregables sin liberar— con tres cosas que hoy no
existen en ninguna de ellas: **dueño, prioridad por severidad y una acción
resolutiva en la propia fila.** Contesta *"¿qué me toca hacer?"*, que es la
pregunta que el panel deliberadamente no contesta porque contesta *"¿podemos
operar?"*.

---

## 4 · Accesibilidad: de WCAG 2.1 a 2.2

La aplicación ya trabaja contra 2.1 AA de forma deliberada, con los ratios
**medidos y anotados en el CSS** (`--ac-text-muted` corregido de 3.94 a 5.09;
`--ac-primary` documentado en 4.53 y por eso los enlaces usan el paso oscuro a
6.44; los ocho colores del menú verificados sobre el fondo correcto en LV-207).
Eso es más de lo que hace prácticamente todo el mercado, que no publica
conformidad alguna.

WCAG **2.2** agrega seis criterios en niveles A/AA. Contra ellos:

| Criterio | Nivel | Estado en AeroControl |
| --- | --- | --- |
| **2.5.7 Movimientos de arrastre** | AA | ❌ **Brecha real.** El editor geo (Geoman) y el Kanban (Sortable.js) son arrastre sin alternativa de un puntero. |
| **2.5.8 Tamaño de objetivo (24×24)** | AA | 🔄 Mayormente cumple: `.btn` está en 40 px y `.btn-sm` en 34 px. **A verificar**: `.pagination-sm .page-link` y el tirador de 6 px de la barra lateral (este último tiene alternativa por teclado, que es una de las excepciones válidas). |
| **2.4.11 Foco no oscurecido** | AA | ✅ Probable. La barra superior no es `fixed`; la lateral es `sticky` pero no cubre el contenido principal. |
| **3.2.6 Ayuda consistente** | A | ➖ No aplica todavía: no hay mecanismo de ayuda. Si se agrega, va en la misma posición en todas las pantallas. |
| **3.3.7 Entrada redundante** | A | 🔄 A revisar en el flujo plan → solicitud → permiso, donde varios datos se re-declaran. |
| **3.3.8 Autenticación accesible** | AA | ✅ Usuario y contraseña, sin prueba cognitiva ni CAPTCHA. |

Faltan además dos cosas que no son criterios pero se comportan como tales:

- **`@media print`** — cero apariciones. El informe de cumplimiento es un
  documento que se imprime.
- **`prefers-contrast` / `forced-colors`** — cero apariciones. En modo de alto
  contraste de Windows, las insignias con fondo `!important` se comportan de
  forma impredecible.

Ambas son baratas y ninguna es urgente. Lo urgente es **2.5.7**.

---

## 5 · El mercado en 2026, y dónde queda AeroControl

El análisis funcional de agosto sigue siendo válido y no se repite. Lo que
cambió, o lo que aquel documento no cubría:

### 5.1 · Correcciones al mapa competitivo

- **Skyward (Verizon) no existe.** Verizon cerró la unidad en mayo de 2022, sin
  transición para sus clientes. Deja de ser referente y pasa a ser **argumento
  comercial**: es el caso que justifica local-first, exportables y API abierta.
- **Kittyhawk = Aloft.** Misma empresa, renombrada en 2021.
- **AirHub** (europeo, Serie A de €4,4 M en abril de 2026) es hoy el competidor
  más parecido a lo que AeroControl quiere ser, y su producto se llama
  literalmente **"Drone Operation Center"**. Vale mirarlo: muestra vuelos
  activos, estado de flota por modelo con mantención vencida, y **registro de
  incidentes con severidad e investigador asignado**. Ese último patrón es
  exactamente la bandeja de §3.3.

### 5.2 · Dónde AeroControl ya gana, y conviene no perderlo

| Eje | Situación |
| --- | --- |
| **Cumplimiento chileno** | Ningún producto internacional modela la DAN 151. Las plantillas "DGAC" de DroneLogbook son genéricas. |
| **Trazabilidad auditable** | DroneLogbook cobra el *audit trail* sólo en su tier más caro (*Private Label*). AeroControl lo tiene de base, append-only. Para un producto de cumplimiento la trazabilidad debería ser el piso, no el techo — y acá lo es. |
| **Español real** | Airdata traduce a 8 idiomas por detección de navegador; nadie **localiza** la regulación. AeroControl escribe en español institucional chileno. |
| **Tema oscuro y accesibilidad medida** | Ningún fabricante del sector documenta tema oscuro, WCAG, paleta accesible ni contraste. La barra del sector está baja. |
| **Local-first** | Los datos no salen a la nube de un tercero. Es una decisión ya tomada y es diferenciadora, no una limitación. |

### 5.3 · Lo que el mercado da por sentado y acá falta

| Función | Quién la tiene | Estado acá |
| --- | --- | --- |
| Checklist prevuelo digital en móvil | Airdata, Aloft, DroneLogbook, Dronedesk, AirHub — **universal** | ❌ Existe como PDF escaneado |
| Modo sin conexión en terreno | Airdata y DroneLogbook lo documentan | ❌ |
| Ingesta automática de vuelos | Airdata (180+ aeronaves), DroneLogbook (80+ formatos) | ❌ Es `X.4`, ya identificado |
| Mantención por **horas de vuelo** | Dronedesk (días **y** horas), Auterion | ❌ Depende de lo anterior |
| Vistas guardadas / etiquetado | Aloft | ❌ |
| Contador de actividad en vivo | AirHub | ❌ |
| Vistas por rol distintas | **Auterion lo documenta explícitamente**: gerente ve KPIs, piloto ve sus registros, cumplimiento ve verificación | ❌ Todos ven lo mismo |

De esa lista, **la única que no depende de telemetría es el checklist digital**, y
es la que más rápido acerca el producto al estándar de mercado. Las demás cuelgan
de `X.4`.

### 5.4 · La oportunidad con fecha: DAN 151 Edición 4

> ⚠️ **Verificar antes de codificar.** Lo que sigue proviene de fuentes
> secundarias chilenas; el PDF oficial no pudo leerse desde el entorno de
> investigación y el nombre del archivo publicado sugiere una versión en
> consulta. **Confirmar contra el texto de la DGAC antes de convertir esto en
> reglas de negocio.**

La Ed. 4 alinea Chile con el modelo OACI/EASA de **categorías por riesgo**:
**Abierta** (bajo 2 kg, hasta 120 m, VLOS, sin autorización previa), **Específica**
(evaluación de riesgo + aprobación DGAC, cubre BVLOS) y **Certificada**
(certificación de aeronave, licencia profesional, auditorías).

La frase operativa es: *el piloto debe identificar en qué categoría cae su
operación **antes** de volar*. Eso convierte la clasificación en un **paso
obligatorio del flujo de planificación**, y AeroControl ya tiene todos los datos
para calcularla sola: masa de la aeronave (padrón), altitud planificada
(`LV-221` la pasó a metros), VLOS/BVLOS y proximidad a zona poblada (ya está en
el permiso como tipo de área).

**Propuesta `UX-30` (§6):** un clasificador en la ficha del permiso que muestre la
categoría **con su justificación** —"Específica, porque: BVLOS declarado + 2,4 kg"—
y que bifurque el flujo: Abierta sigue; Específica exige evaluación de riesgo
cargada antes de aprobar; Certificada exige además certificación y licencia
vigentes. Dronedesk vende esto como complemento pagado para el marco europeo.
Nadie lo tiene para Chile.

---

## 6 · Decisiones de mejora

Formato: **qué se decide · por qué · cómo se ve · cómo se sabe que quedó bien.**
Los IDs `UX-nn` son los que se capturan en `MASTER_PLAN.md`.

### Fase A — El sistema (desbloquea todo lo demás)

**`UX-01` · Tokens de severidad de cinco niveles.**
*Por qué:* hoy la severidad la dan utilidades de Bootstrap reparadas con quince
reglas `!important` en tema oscuro; nada garantiza que ámbar signifique lo mismo en dos
pantallas. *Cómo se ve:* `--sev-{nominal,advisory,caution,warning,critical}` con
sus tres variantes (fondo, texto, borde) en claro y oscuro. *Criterio:* ninguna
insignia de estado usa `bg-warning-subtle` directamente; las reglas `!important`
de insignias en `[data-theme="dark"]` bajan de 15 a 0; una prueba verifica que
cada par fondo/texto cumple 4.5:1 en ambos temas.

**`UX-02` · Escala tipográfica y de espaciado como tokens.**
*Criterio:* `--fs-*` y `--sp-*` declarados; ningún valor `rem` literal nuevo en
`app.css`; los existentes se migran al tocar cada bloque, no en una pasada.

**`UX-03` · `tabular-nums` en tablas, KPI y fechas.**
*Criterio:* una línea; `11/14` y `8/16` alinean entre tarjetas contiguas.

**`UX-04` · Encabezado de página único y obligatorio.**
*Por qué:* hoy hay tres tamaños de `h1` distintos según si la plantilla usa
`.page-header`. *Criterio:* existe `generic/_page_header.html`; ninguna plantilla
declara `<h1>` fuera de él; una prueba de plantillas lo verifica.

**`UX-05` · Sprite SVG global.**
*Por qué:* `base.html` lleva ~24 `path` inline y `administration.html` ya
demuestra el patrón correcto con `<symbol>`/`<use>`. *Criterio:* un solo
`icons.svg`; `base.html` pierde los `path`; los iconos se referencian por nombre.

**`UX-06` · `@media print` para informes y fichas.**
*Criterio:* imprimir `compliance/report.html` no incluye menú, barra ni botones;
las tablas no se cortan a mitad de fila; sale el sello de generación.

### Fase B — La tabla de trabajo

**`UX-07` · Componente `_worktable.html`.** ✅ **Hecho el 2026-09-03**, como
`generic/worktable.html`. Reemplaza el `<table>` a mano de `generic/list.html` y
de las listas específicas. Trae de una vez: orden por columna, "mostrando N–M de
T", selección múltiple, y el borde de severidad.
*Criterio:* las 26 listas lo usan; ninguna pierde función; la suite sigue verde.

⚠️ **Al medirlo, "las 26 listas" resultaron ser 16**, y conviene anotarlo porque
el número de esta fila se venía repitiendo sin contarlo: nueve ya pasaban por
`generic/list.html` y siete se escribían la cáscara a mano. Las dieciséis pasan
ahora por el componente. De las 58 `<table>` del árbol, el resto son fichas
—tablas de dato/valor— y no listas.

🔶 **Y `workboard/task_list.html` queda fuera a propósito, con test que lo fija.**
Tres razones: el tablero se da de baja por decisión del usuario (`LV-78`); su
tabla no tiene la forma de una tabla de trabajo (filas de agrupamiento,
`offcanvas`, `container-fluid`); y sobre todo **ya usa `?sort=` con otra
semántica**, así que migrarla haría que dos mecanismos se pisen sobre la misma
llave y el que perdiera fallaría en silencio.

**Es plantilla base y no `include`**, porque un `include` recibe variables y no
bloques: las nueve listas genéricas sobreescriben `list_header`, `list_colgroup` y
`table_body`, y convertirlas habría exigido aplanar cada encabezado a una lista
de diccionarios armada en Python.

**`UX-08` · Densidad conmutable (cómoda 40 px / compacta 32 px),** recordada por
persona en `localStorage` con el `try/catch` que el proyecto ya usa.

**`UX-09` · Selector de columnas,** persistido por lista y por persona.
✅ **Hecho el 2026-09-03**, con `UX-12`: las dos son *con qué estado alguien
vuelve a una lista*, así que las guarda un solo modelo (`core.ListPreference`,
migración `core.0008`).
*Criterio:* la lista de alertas puede mostrar la faena como **columna** en
escritorio y esconderla en pantalla angosta, en vez de vivir como *chip* de
segunda línea (que fue el parche de `LV-146`).

⚠️ **Se guardan las columnas ocultas, no las visibles**, y es la decisión que no
se ve al leer el campo: con las visibles, una columna nueva sería invisible para
todo el que alguna vez guardó una preferencia — la lista estrenaría la columna
mostrándosela sólo a quien nunca la configuró.

🔶 **El criterio de esta fila queda a medias, y hay que decirlo.** La mitad
"esconderla en pantalla angosta" **no** está: lo que hay es esconderla por
decisión de la persona, no automáticamente por ancho. Esconder por ancho es
`UX-10`, que ya apila la fila como tarjeta bajo 768 px, y la faena sigue siendo
un *chip* de segunda línea en la lista de alertas. Convertirla en columna es un
cambio de esa lista, no del selector, y no se hizo.

**`UX-10` · Fila-tarjeta bajo 768 px.** Cada fila se apila mostrando las tres
columnas que importan más su severidad. *Criterio:* ninguna lista requiere
desplazamiento horizontal en 390 px.

**`UX-11` · Acciones en lote con selección explícita por casilla.** Archivar,
exportar la selección y resolver alertas. *Criterio:* la barra contextual aparece
sólo con algo seleccionado y dice cuántos; **la selección es explícita, nunca
inferida por fecha o regla** (la lección de `LV-68`).

**`UX-12` · Vistas guardadas.** ✅ **Hecho el 2026-09-03**, junto con `UX-09` y en
el mismo modelo. Un filtro con nombre, propia o compartida.
*Criterio:* "Seguros vencidos" y "Credenciales a 60 días" se guardan y aparecen
como pestañas sobre la tabla. **Cumplido**, con test que lo comprueba en la lista
de alertas.

Una vista guarda **también sus columnas**: volver a "Seguros vencidos" con las
columnas de otra vista sería devolver algo que no es lo que se guardó. Y
compartir es **ofrecer, no ceder** — la ve todo el mundo, la edita y la borra sólo
quien la creó, con el filtro por autor en la consulta y no en un `if` posterior.

⚠️ Se adelantó a la fase 5 donde el plan la tenía, porque `UX-07` acababa de
crear el lugar donde vive la pestaña: hacerla después habría significado abrir
las mismas dieciséis plantillas dos veces.

### Fase C — La bandeja y el panel

**`UX-13` · Bandeja de trabajo `/bandeja/`.** Vista unificada sobre alertas, no
conformidades, mantención por definir, permisos esperando respuesta y entregables
sin liberar, con **dueño, severidad y acción en la fila**. *Criterio:* resolver
desde la bandeja produce exactamente la misma evidencia ISO 10.2 que resolver
desde la lista de alertas — es la misma vista, no un segundo camino.

**`UX-14` · Asignación de responsable** en alerta y no conformidad. *Por qué:* es
el patrón que AirHub ya tiene (investigador asignado) y lo que convierte una lista
en trabajo. *Criterio:* "Mis pendientes" filtra por persona.

**`UX-15` · Contador de actividad en el panel:** "N operaciones hoy · M permisos
vigentes". *Criterio:* sale de datos existentes, sin modelo nuevo.

**`UX-16` · Frescura declarada en datos externos.** El clima muestra su hora de
consulta. *Criterio:* ningún dato de terceros se presenta sin marca de tiempo.

**`UX-17` · Filtro de faena recordado** en panel y listados.

**`UX-18` · Estado vacío de alertas como buena noticia.** "Nada pendiente" con
enlace a las resueltas del mes, no "No alerts found."

### Fase D — Formularios y entrada

**`UX-19` · Guardia de cambios sin guardar en el modal genérico.** *Criterio:*
cerrar con `Esc` o con "Cancelar" habiendo tocado un campo pide confirmación.

**`UX-20` · Formularios largos en página completa, no en modal.** Umbral: más de
ocho campos o cualquier campo de selección múltiple. *Criterio:* el permiso de
vuelo y la carga de documentos dejan de anidar tres barras de desplazamiento.

**`UX-21` · `inputmode`, `enterkeyhint` y `autocomplete`** en todos los campos.
*Criterio:* un campo numérico abre teclado numérico en móvil.

**`UX-22` · "Guardar y crear otro"** en los formularios de alta repetitiva
(vuelos, documentos, movimientos).

**`UX-23` · Borrador generalizado.** Extender `form-draft.js` más allá del
formulario de permiso.

### Fase E — Terreno

**`UX-24` · Búsqueda global en móvil.** Hoy desaparece bajo 768 px. *Criterio:*
un icono de lupa en la barra que abre la búsqueda a pantalla completa.

**`UX-25` · Paleta de comandos (`Ctrl/⌘+K`).** Navegar, buscar entidad y ejecutar
acción. *Por qué:* quien trabaja alertas entra veinte veces al día; y **ningún
competidor del sector la documenta**, así que además se ve en una demostración.

**`UX-26` · PWA instalable con caché de sólo lectura.** Manifiesto, iconos y un
*service worker* que sirva **lo último consultado** cuando no hay señal, marcado
claramente como "datos del <fecha>". *Criterio:* en avión o sin señal se puede
consultar la última ficha de aeronave vista; **nunca se permite escribir sin
conexión** — un registro de cumplimiento creado offline y sincronizado tarde es
peor que no tenerlo.

**`UX-27` · Pantalla "¿puedo volar?"** para el operador en faena: una sola
respuesta con aeronave, operador y faena, y el motivo del bloqueo si lo hay, con
enlace a resolverlo.

**`UX-28` · Alternativa sin arrastre en el editor geo** (WCAG 2.2 §2.5.7): tabla
de coordenadas editable junto al lienzo. *Beneficio doble:* es también lo que se
transcribe a SIGO.

### Fase F — Producto

**`UX-29` · Checklist prevuelo digital.** Es el estándar universal del mercado y
la única brecha funcional grande que **no** depende de la telemetría. Formulario
configurable por tipo de aeronave, firmado, que queda como evidencia adjunta al
vuelo.

**`UX-30` · Clasificador de categoría DAN 151 Ed. 4** en el flujo del permiso,
con justificación visible y bifurcación del flujo. **Sujeto a verificar el texto
oficial primero.**

**`UX-31` · Vistas por rol.** Distinta página de inicio y distinto orden de menú
para jefatura, cumplimiento y operador — **sin ocultar** lo que el permiso
autoriza. *Por qué:* ocultar genera desconfianza; priorizar genera velocidad.

---

## 7 · Orden de ejecución

El orden **no** es por valor percibido; es por lo que desbloquea a lo demás y por
lo que se puede verificar sin desplegar.

| Tanda | Filas | Por qué acá | Tamaño |
| --- | --- | --- | --- |
| **1 · Cimiento** | `UX-01` `UX-02` `UX-03` `UX-04` `UX-05` `UX-06` | Todo lo demás se escribe contra estos tokens. Es CSS y plantillas genéricas: riesgo bajo, sin migraciones, y `UX-01` **borra deuda** (las 15+ reglas `!important`). | 1 sesión |
| **2 · La tabla** | `UX-07` … `UX-11` | Un componente que arregla 26 pantallas. `UX-10` es lo que vuelve usable el móvil sin escribir una app. | 1–2 sesiones |
| **3 · La bandeja** | `UX-13` `UX-14` `UX-18` `UX-15` `UX-16` `UX-17` | El mayor cambio de experiencia con el menor código nuevo: son vistas sobre datos que ya existen. | 1 sesión |
| **4 · Entrada** | `UX-19` … `UX-23` | Independiente de todo lo anterior; se puede intercalar. | 0,5 sesión |
| **5 · Terreno** | `UX-24` `UX-25` `UX-12` `UX-28` | `UX-28` cierra la brecha WCAG 2.2. | 1 sesión |
| **6 · Producto** | `UX-26` `UX-27` `UX-29` `UX-30` `UX-31` | Requieren decisión de negocio, no sólo diseño. **No empezar sin acordar alcance.** | por definir |

**Regla de trabajo:** cada tanda entra con `pwsh scripts/verify.ps1` en verde,
igual que todo lo demás. Ninguna fila de la tanda 6 empieza sin instrucción
explícita.

---

## 8 · Lo que se decide NO hacer, y por qué

Decir que no también es diseño.

- **No se separa el frontend.** [docs/frontend-boundary.md](frontend-boundary.md)
  ya lo resolvió y las condiciones para reconsiderarlo (dos clientes
  independientes, requisitos offline contractuales) **no se cumplen**. Todo este
  plan se ejecuta en Django + HTMX + Bootstrap. El único JavaScript nuevo es
  islas bajo las reglas ya escritas.
- **No se agrega fuente web.** `system-ui` es correcta para local-first, no pide
  red y no tiene costo de carga. La mejora tipográfica está en `tabular-nums` y en
  la jerarquía, no en la familia.
- **No se copia LAANC ni streaming.** La DGAC no publica API estable, y un dato de
  espacio aéreo desactualizado es peor que ninguno. El análisis de agosto ya lo
  decidió y sigue siendo correcto.
- **No se compite por ingesta de telemetría.** 180 aeronaves y 80 formatos es una
  barrera de años. El camino es `X.4` con AeroLink — y nótese que **Dronedesk, un
  competidor real, resolvió lo mismo integrándose con Airdata en vez de
  replicarlo**.
- **No se permite escritura sin conexión.** Ver `UX-26`. Un registro de
  cumplimiento creado offline y sincronizado tarde compromete la trazabilidad,
  que es justo lo que este producto vende.
- **No se rediseña el panel.** Es la mejor pantalla de la aplicación. Se le agrega
  actividad y frescura; su estructura no se toca.

---

## 9 · Cómo se sabe que funcionó

Métricas verificables, no impresiones:

| Qué | Hoy | Meta |
| --- | --- | --- |
| Reglas `!important` de insignias en tema oscuro | 15 (de 30 en todo el archivo) | 0 |
| Tamaños distintos de `<h1>` | 3 | 1 |
| Listas que exigen desplazamiento horizontal en 390 px | 26 | 0 |
| Pantallas con `@media print` | 0 | informes y fichas |
| Criterios WCAG 2.2 AA con brecha conocida | 1 (§2.5.7) | 0 |
| Vistas vivas sin puerta en la interfaz | 6 | 0 (en menú, en bandeja, o retiradas de verdad) |
| Clics para resolver una alerta desde el inicio de sesión | 3 (panel → alertas → resolver) | 2 (bandeja → resolver) |

---

## 10 · Bitácora

- **2026-09-02** — Documento creado. Revisión completa del recorrido, del sistema
  visual y del mercado. 31 filas propuestas, ninguna ejecutada. Pendiente:
  aprobación del usuario y captura en `MASTER_PLAN.md`.

### Fuentes de la sección de mercado

Airdata ([precios](https://airdata.com/pricing) · [funciones](https://airdata.com/features) · [idiomas](https://app.airdata.com/global)) ·
DroneLogbook ([precios](https://www.dronelogbook.com/hp/1/pricing.php)) ·
Aloft ([Air Control Enterprise](https://help.aloft.ai/en/articles/9460286-air-control-enterprise) · [seguridad](https://www.aloft.ai/security/) · [Kittyhawk→Aloft](https://www.aloft.ai/blog/kittyhawk-io-is-now-known-as-aloft/)) ·
Dronedesk ([funciones](https://dronedesk.io/features)) ·
FlytBase ([cloud](https://flytbase.com/cloud/)) ·
Auterion ([gestión de flota](https://docs.auterion.com/vehicle-operation/auterion-suite-fleet-management)) ·
AirHub ([Drone Operation Center](https://www.airhub.app/all-features/drone-operation-center) · [Serie A](https://dronelife.com/2026/04/08/drone-operations-software-company-airhub-closes-e4-4m-series-a/)) ·
Cierre de Skyward ([The Robot Report](https://www.therobotreport.com/verizon-shutting-down-skyward-drone-management-company/)) ·
WCAG 2.2 ([Understanding](https://www.w3.org/WAI/WCAG22/Understanding/) · [2.5.8 Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)) ·
DAN 151 Ed. 4 ([PDF DGAC — verificar](https://www.dgac.gob.cl/wp-content/uploads/2026/04/DAN-151-ED4-24MAR2026-Opinin.pdf) · [análisis Aerotest](https://aerotest.cl/blog/test/dan-151-edicion-4-claves-de-las-nuevas-categorias-oaci-para-pilotos-de-drones-en-chile))
