# Impeccable UI audit — AeroControl

Fecha: 24 julio 2026  
Rama: `codex/impeccable-ui-audit`

## Resultado

Impeccable queda incorporado como skill de proyecto en
`.agents/skills/impeccable/`. Se mantuvo sin hooks automáticos hasta validar
que los hallazgos sean útiles para el flujo diario.

El detector mecánico revisó `templates/` y `static/` y encontró cinco avisos
iniciales. Después de los lotes 1–4 quedan tres avisos, todos relacionados con
bordes visuales intencionales del Kanban.

| Dimensión | Puntaje | Evidencia |
| --- | ---: | --- |
| Accesibilidad | 4/4 | Skip link, landmarks, labels, foco visible, alertas anunciables y regiones Kanban etiquetadas. |
| Rendimiento | 4/4 | Chart.js se carga solo en dashboard y se eliminó la transición de `width`/`flex-basis` del sidebar; HTMX permanece global porque se usa en múltiples vistas. |
| Theming | 3/4 | Tokens y modo oscuro existen, pero login y algunas reglas antiguas mantienen colores literales. |
| Responsive | 3/4 | Hay breakpoints, overflow táctil controlado y scroll-snap para Kanban/tabs; falta una prueba visual automatizada en 320/768/1440 px. |
| Integridad de implementación | 3/4 | Sistema visual coherente; tres bordes de acento siguen marcados, pero expresan prioridad/estado y no son decoración general. |
| **Total** | **17/20** | **Bueno: los riesgos principales quedaron acotados y no se requiere rediseño.** |

## Hallazgos priorizados

### P1 — Internacionalización incompleta en flujos críticos — RESUELTO

Ubicaciones: `templates/generic/confirm_delete.html`,
`templates/compliance/document_replace.html` y parte de
`templates/operations/flightrecord_detail.html`.

Hay textos visibles en inglés aunque el idioma inicial del producto es español
de Chile. Esto afecta comprensión y consistencia en archivado, reemplazo de
documentos y bitácora.

Acción aplicada: se convirtió el texto a `{% translate %}` y se completó el
catálogo español en el detalle de vuelo, archivado y reemplazo de documentos.

### P2 — Transición de ancho del sidebar — RESUELTO

Ubicación: `static/css/app.css:707`.

El detector marca `transition: width` y `flex-basis`. Es intencional para la
barra colapsable, pero puede provocar recálculo de layout durante la animación.

Acción aplicada: se eliminó la transición de propiedades de layout y se
conservó únicamente la transición de fondo.

### P2 — Bordes de acento detectados como patrón repetido

Ubicaciones: `static/css/app.css:246`, `:949` y `:952`.

El borde superior de las columnas y el borde lateral de las tarjetas expresan
estado y separación del Kanban. Son falsos positivos aceptables mientras no se
repitan como decoración en todas las superficies.

Acción: conservar por ahora y revisar en una prueba visual del Workboard.

### P2 — Jerarquía tipográfica del login — RESUELTO

Ubicación: `templates/registration/login.html:18`.

El detector observa tamaños cercanos entre título, subtítulo y etiquetas.

Acción aplicada: se consolidó la jerarquía, se añadió un `h1`, se reforzó el
foco visible y se añadieron variables de color para claro/oscuro.

## Revisión final de lotes

- Lote 1: traducciones de detalle de vuelo — commit `dfbf968`.
- Lote 2: accesibilidad y jerarquía del login — commit `7a283e0`.
- Lote 3: responsive y semántica Kanban — commit `3db3d45`.
- Lote 4: carga diferida de Chart.js y auditoría final — pendiente de respaldo.

Validaciones finales ejecutadas: `manage.py check`, compilación de
traducciones, `git diff --check` y detector Impeccable. No se activaron hooks.

## Pendientes funcionales que siguen bloqueados por datos o decisión

- Resolver los cuatro grupos de operadores con datos contradictorios.
- Asignar oficialmente aeronaves y operadores a centros de costo.
- Modelar habilitaciones DGAC con vigencia y evidencia documental.
- Definir compatibilidad operador–aeronave antes de autorizar vuelos.
- Registrar la tarea semanal de backup con la ruta real del medio externo.

No se deben resolver esos puntos inventando relaciones a partir de la fuente.

## Siguiente orden recomendado

1. Respaldar el Lote 4 y actualizar el PR.
2. Revisar visualmente Workboard y login en claro/oscuro y móvil.
3. Mantener los pendientes de datos para cuando exista confirmación oficial.
