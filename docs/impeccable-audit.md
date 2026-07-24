# Impeccable UI audit — AeroControl

Fecha: 24 julio 2026  
Rama: `codex/impeccable-ui-audit`

## Resultado

Impeccable queda incorporado como skill de proyecto en
`.agents/skills/impeccable/`. Se mantuvo sin hooks automáticos hasta validar
que los hallazgos sean útiles para el flujo diario.

El detector mecánico revisó `templates/` y `static/` y encontró cinco avisos.
Son señales para revisar, no cambios automáticos.

| Dimensión | Puntaje | Evidencia |
| --- | ---: | --- |
| Accesibilidad | 3/4 | Skip link, landmarks, labels, focus-visible y soporte de teclado; quedan algunos controles compactos y enlaces activos sin `aria-current`. |
| Rendimiento | 3/4 | Interfaz ligera; se cargan Chart.js y dependencias CDN en la plantilla base y se anima `width` al colapsar el sidebar. |
| Theming | 3/4 | Tokens y modo oscuro existen, pero login y algunas reglas antiguas mantienen colores literales. |
| Responsive | 3/4 | Hay breakpoints y overflow controlado para Kanban/tabs; revisar touch targets de botones pequeños. |
| Integridad de implementación | 3/4 | Sistema visual coherente; tres bordes de acento y una transición de layout fueron marcados como patrones a revisar. |
| **Total** | **15/20** | **Bueno: conviene una pasada focalizada, no un rediseño total.** |

## Hallazgos priorizados

### P1 — Internacionalización incompleta en flujos críticos

Ubicaciones: `templates/generic/confirm_delete.html`,
`templates/compliance/document_replace.html` y parte de
`templates/operations/flightrecord_detail.html`.

Hay textos visibles en inglés aunque el idioma inicial del producto es español
de Chile. Esto afecta comprensión y consistencia en archivado, reemplazo de
documentos y bitácora.

Acción: convertir el texto a `{% translate %}` y completar el catálogo español.

### P2 — Transición de ancho del sidebar

Ubicación: `static/css/app.css:707`.

El detector marca `transition: width` y `flex-basis`. Es intencional para la
barra colapsable, pero puede provocar recálculo de layout durante la animación.

Acción: medir en navegador; si produce tirones, conservar la transición solo
para el contenedor necesario o migrar la composición a una transformación.

### P2 — Bordes de acento detectados como patrón repetido

Ubicaciones: `static/css/app.css:246`, `:949` y `:952`.

El borde superior de las columnas y el borde lateral de las tarjetas expresan
estado y separación del Kanban. Son falsos positivos aceptables mientras no se
repitan como decoración en todas las superficies.

Acción: conservar por ahora y revisar en una prueba visual del Workboard.

### P2 — Jerarquía tipográfica del login

Ubicación: `templates/registration/login.html:18`.

El detector observa tamaños cercanos entre título, subtítulo y etiquetas.

Acción: consolidar los tamaños en tokens compartidos cuando se haga la próxima
pasada de tipos, sin cambiar la identidad del login.

## Pendientes funcionales que siguen bloqueados por datos o decisión

- Resolver los cuatro grupos de operadores con datos contradictorios.
- Asignar oficialmente aeronaves y operadores a centros de costo.
- Modelar habilitaciones DGAC con vigencia y evidencia documental.
- Definir compatibilidad operador–aeronave antes de autorizar vuelos.
- Registrar la tarea semanal de backup con la ruta real del medio externo.

No se deben resolver esos puntos inventando relaciones a partir de la fuente.

## Siguiente orden recomendado

1. Corregir la internacionalización P1.
2. Revisar visualmente Workboard y login en claro/oscuro y móvil.
3. Ejecutar de nuevo el detector sobre los archivos modificados.
4. Ejecutar la suite y abrir PR de esta rama.
5. Mantener los pendientes de datos para cuando exista confirmación oficial.
