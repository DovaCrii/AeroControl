"""Reparto de las tablas del informe en hojas A4, para que nada se pierda.

**El problema que resuelve, medido y no supuesto.** La hoja del informe mide
1123 px fijos (A4 a 96 dpi, la medida en la que se dibujó el diseño). El
2026-09-08, con 15 permisos vigentes, el cuerpo de la página 3 terminaba en
**1487 px**: 427 px por encima del pie y 364 px fuera de la hoja, donde
`overflow: hidden` los recortaba. Un papel que va firmado a la DGAC diciendo
«detalle permiso a permiso» y que pierde filas sin avisar es lo más grave que
este informe puede hacer, y lo encontró el usuario mirando la pantalla.

`report-a4.css` cerró la mitad estructural —la hoja es una columna flex, así que
el contenido **no puede** taparel pie— y este módulo cierra la otra: repartir las
filas en tantas hojas como hagan falta.

## De dónde salen los números

Medidos en el navegador sobre la página 3 renderizada, el 2026-09-08, con el
caso peor de contenido (cuatro operadores designados por permiso, que hace que la
celda envuelva a dos líneas):

| | |
|---|---|
| Donde empieza el pie | 1060 px |
| Donde cae la primera fila, en la hoja con el ciclo y los indicadores | 515 px |
| Donde caería en una hoja de continuación (encabezado + rótulos + cabecera) | 205 px |
| Alto de una fila con uno o dos operadores | 45 px |
| Alto de una fila con tres o cuatro | 60 px |
| Cierre de la sección (observación del período + leyenda) | 133 px |

## Por qué se reparte por píxeles y no por número de filas

⚠️ **Porque las filas no miden todo lo mismo, y darlo por sentado ya falló.** El
primer reparto usaba un solo `ROW_PX = 45`, medido sobre filas de uno o dos
operadores. Al probarlo con permisos de **cuatro** operadores designados —lo que
tiene producción— la celda de nombres envolvió a tres líneas, la fila pasó a
**60 px**, y la hoja volvió a recortar la última: 70 px por debajo del pie. Un
promedio disfrazado de caso peor.

Así que cada fila se estima por su contenido, con los coeficientes de arriba, y
se llena la hoja hasta gastar su presupuesto. Las dos celdas que crecen son las
multivaluadas —operadores designados y aeronaves—, y manda la más alta de las
dos.

⚠️ **Sigue siendo una estimación, y por eso el documento declara el total.** La
celda de nombres envuelve según el ancho real de cada nombre, que esto no mide.
Dos cosas contienen el residuo: una fila de margen por hoja, y el rótulo
«Detalle permiso a permiso · N vigentes» repetido en cada hoja de la sección —
con el total escrito, quien revisa cuenta y nota que falta algo. Un recorte
silencioso pasa inadvertido; uno contra un total declarado, no.
"""

#: Todo en píxeles de la hoja de 1123, tal como se midió. Se dejan como números
#: y no como fracciones porque son medidas de un diseño concreto: expresarlas en
#: porcentajes sugeriría que el diseño escala, y no lo hace.
#:
#: ⚠️ **LV-248 · re-medidos el 2026-09-23, y tres de cinco cambiaron.** La tabla de
#: arriba de este módulo es la medición del 2026-09-08 y se deja como historia. Lo
#: que cambió y por qué:
#:
#: | | Antes | Ahora | Por qué |
#: |---|---|---|---|
#: | Primera fila, hoja 1 de la sección | 515 | **344** | el ciclo de cuatro pasos (157 px) se mudó al resumen, por decisión del usuario |
#: | Primera fila, hoja de continuación | 205 | **229** | medida de nuevo: la de antes estaba **corta**, y el margen de seguridad la tapaba |
#: | Fila base | 45 | **27** (26,5) | el folio se partía en dos líneas porque `.rpt-table .c` pisaba la letra de 9 px del diseño; restaurada, la fila es de una línea |
#: | Línea de aeronave de más | 15 | **12** (11,7) | la celda vuelve a su 8,4 px |
#:
#: Con esto la sección de permisos de producción —11 vigentes y 3 en trámite—
#: cabe en **una** hoja: el informe pasa de 6 a 5 hojas más el anexo de la nómina.
FOOTER_TOP_PX = 1060
#: LV-260: 344 → **220**. Los cuatro contadores de arriba de la tabla salieron
#: (repetían los de la hoja ejecutiva); medido el 2026-09-25, la primera fila cae
#: en 217 px. Fila base sin cambios: 26,5 medido, 27 usado.
FIRST_SHEET_ROW_TOP_PX = 220
CONTINUATION_ROW_TOP_PX = 229
#: Una fila de una sola línea en sus celdas multivaluadas.
ROW_BASE_PX = 27
#: Lo que suma cada aeronave de más (van una por línea). Medido: 26,5 px con una,
#: 38,2 con dos. Equivocarse por exceso deja un hueco en la hoja; por defecto,
#: recorta una fila — así que cuando haya duda, este número sube.
ROW_LINE_PX = 12
#: LV-248: acá estaba `NAMES_PER_LINE = 2`, cuántos nombres cabían por línea en la
#: celda de operadores. La celda dejó de listarlos —dice «4 operadores»—, así que
#: la constante no tenía ya a quién medir. Los nombres viven en el anexo, con su
#: propia medida (`ROSTER_NAMES_PER_LINE`).
#: Observación del período + leyenda de bandas, que cierran la sección y por eso
#: van sólo en la última hoja.
CLOSING_PX = 133
#: Una fila de margen por hoja. Absorbe el residuo de la estimación: la celda de
#: nombres envuelve según el ancho real de cada nombre, que esto no mide.
SAFETY_PX = ROW_BASE_PX


#: LV-260: las matrículas van en línea, separadas por «·», en la columna que
#: ahora se lleva el ancho libre. Cuántas caben por renglón.
AIRCRAFT_PER_LINE = 4

#: LV-260 · La hoja que junta la cobertura por faena y el plan compacto.
#: **Medidos en el navegador el 2026-09-25** sobre el informe renderizado con la
#: forma de producción (12 faenas, cuatro fases, matriz de cuatro filas):
#:
#: | | medido | usado |
#: |---|---|---|
#: | Primera fila de faena, desde el borde de la hoja | 201 | 201 |
#: | Alto de una fila de faena | 22,2 | 23 |
#: | Total + concentración + separación hasta el plan | 62 + 14 | 76 |
#: | Plan compacto sin la matriz (título, apertura, fases, leyenda, ciclo) | 442,4 | 443 |
#: | Fila de la matriz | 23,4 | 24 |
#:
#: Con el margen de una fila (`SAFETY_PX`), comparten hoja **hasta 9 faenas**. Con
#: 12 no entran: medido, el plan terminaba en 1079 px, bajo el pie. Las fases son
#: texto editable (`LV-249`): si alguien las alarga mucho, este número se queda
#: corto — y lo que pasa entonces es que la hoja recorta contra su borde, así que
#: al editar las fases conviene mirar la vista previa.
COVERAGE_FIRST_ROW_TOP_PX = 201
COVERAGE_ROW_PX = 23
COVERAGE_TAIL_PX = 76
PLAN_BLOCK_BASE_PX = 443
PLAN_MATRIX_ROW_PX = 24


def plan_fits_with_coverage(cost_centres, matrix_rows):
    """¿Caben la tabla de faenas y el plan compacto en la misma hoja?

    La tabla crece con las faenas y el plan con las filas de la matriz; el resto
    del plan (fases, leyenda, nota del ciclo) es de alto fijo. Con margen de una
    fila, como el resto del reparto: equivocarse por exceso manda el plan a su
    hoja; por defecto, lo recortaría bajo el pie.
    """
    coverage = (
        COVERAGE_FIRST_ROW_TOP_PX
        + COVERAGE_ROW_PX * max(cost_centres, 1)
        + COVERAGE_TAIL_PX
    )
    plan = PLAN_BLOCK_BASE_PX + PLAN_MATRIX_ROW_PX * matrix_rows
    return coverage + plan + SAFETY_PX <= FOOTER_TOP_PX


def row_px(row):
    """El alto estimado de una fila de la tabla de permisos, por su contenido.

    ⚠️ **LV-248: los operadores ya no cuentan.** La celda mostraba a **todos** los
    operadores designados, y cada dos nombres sumaban una línea de 15 px: con los
    cuatro de producción era la causa directa de las hojas de más. El usuario pidió
    un informe *"más corto, con lo esencial"* y eligió recortar exactamente esto —
    la celda dice ahora «4 operadores» y la nómina completa va a un anexo al final
    (`roster_row_px`). Lo único que sigue creciendo es la de aeronaves, que va una
    por línea (la plantilla las separa con `<br>`).
    """
    tails = len(row.get("aircraft") or [])
    # LV-260: en línea, `AIRCRAFT_PER_LINE` por renglón (antes, una por renglón).
    lines = -(-tails // AIRCRAFT_PER_LINE) if tails else 1
    return ROW_BASE_PX + ROW_LINE_PX * (lines - 1)


#: LV-248 · El anexo de la nómina. **Medido en el navegador el 2026-09-23** sobre la
#: hoja renderizada, con nombres reales de producción:
#:
#: | | |
#: |---|---|
#: | Donde cae la primera fila | 218 px |
#: | Fila de 1 y de 4 nombres (una línea) | 26,5 px |
#: | Fila de 9 nombres (dos líneas) | 35,1 px |
#:
#: ⚠️ La primera medición daba **45 px para todas las filas**, con uno o con nueve
#: nombres: `.rpt-table .c` pisaba el cuerpo del anexo y el folio se partía en dos
#: líneas, así que la altura la decidía el folio y no los nombres. Una estimación
#: calibrada contra eso habría medido otra cosa; se corrigió el CSS y se volvió a
#: medir. Ver `report-a4.css`.
#:
#: Los tres se redondean **hacia arriba** —equivocarse por exceso deja un hueco;
#: por defecto, recorta—, y `ROSTER_NAMES_PER_LINE` queda en 4 aunque la medición
#: muestra que caben al menos cinco: cuatro nombres largos entran seguro en una
#: línea, y los nombres de producción no miden todos lo mismo.
ROSTER_FIRST_ROW_TOP_PX = 218
ROSTER_ROW_BASE_PX = 27
ROSTER_LINE_PX = 12
ROSTER_NAMES_PER_LINE = 4


def roster_row_px(row):
    """El alto estimado de una fila del anexo de operadores designados.

    Una fila por permiso: folio, faena y la nómina completa, que envuelve de a
    `ROSTER_NAMES_PER_LINE`. Equivocarse por defecto recorta una fila; por eso,
    como en la tabla de permisos, el margen de hoja (`SAFETY_PX`) absorbe el
    residuo y el rótulo declara el total.
    """
    names = len(row.get("operators") or [])
    lines = -(-names // ROSTER_NAMES_PER_LINE) if names else 1
    return ROSTER_ROW_BASE_PX + ROSTER_LINE_PX * (lines - 1)


def sheet_budget_px(
    *,
    first,
    last,
    closing_px=CLOSING_PX,
    first_top=FIRST_SHEET_ROW_TOP_PX,
    continuation_top=CONTINUATION_ROW_TOP_PX,
    safety=SAFETY_PX,
):
    """Cuántos píxeles de filas caben en una hoja de la sección.

    `first` baja el techo porque esa hoja carga además el ciclo de vigencia y los
    cuatro indicadores; `last` lo baja porque cierra con la observación y la
    leyenda. Una sección de una sola hoja es las dos cosas, y ése es el caso más
    apretado. `first_top` deja que otra sección —el anexo, `LV-248`— declare dónde
    empieza su primera fila.
    """
    top = first_top if first else continuation_top
    available = FOOTER_TOP_PX - top - (closing_px if last else 0) - safety
    return max(ROW_BASE_PX, available)


def paginate(
    rows,
    *,
    closing_px=CLOSING_PX,
    estimate=row_px,
    first_top=FIRST_SHEET_ROW_TOP_PX,
    continuation_top=CONTINUATION_ROW_TOP_PX,
    safety=SAFETY_PX,
):
    """Reparte `rows` en hojas, devolviendo una lista de listas.

    ⚠️ **Se busca el número de hojas por prueba creciente en vez de repartir de
    corrido**, y la razón es que el techo de la última hoja depende de que **sea**
    la última: repartir hacia adelante decidiría el presupuesto de una hoja antes
    de saber si le sigue otra, y el caso límite —lo que sobra entra justo en una
    hoja intermedia pero no en una final— quedaría mal repartido. Probar de una
    hoja hacia arriba es unas cuantas pasadas sobre una lista de decenas de
    filas: el costo es irrelevante y la respuesta es siempre correcta.

    Una lista vacía devuelve **una** hoja vacía, no cero: la sección existe en el
    documento y tiene que decir "ningún permiso vigente al corte" en su hoja.
    """
    rows = list(rows)
    if not rows:
        return [[]]
    for sheets in range(1, len(rows) + 1):
        packed = _pack(
            rows, sheets, closing_px, estimate, first_top, continuation_top, safety
        )
        if packed is not None:
            return packed
    # Inalcanzable: con `sheets == len(rows)` cada hoja lleva una fila, y
    # `sheet_budget_px` nunca devuelve menos que una fila base. Se deja explícito
    # en vez de un `assert` para que, si alguien baja `FOOTER_TOP_PX` por error,
    # el informe salga entero de una hoja en vez de salir vacío.
    return [rows]


def _pack(
    rows,
    sheets,
    closing_px,
    estimate,
    first_top,
    continuation_top=CONTINUATION_ROW_TOP_PX,
    safety=SAFETY_PX,
):
    """Intenta meter `rows` en exactamente `sheets` hojas. `None` si no entran."""
    out, index = [], 0
    for sheet in range(sheets):
        budget = sheet_budget_px(
            first=sheet == 0,
            last=sheet == sheets - 1,
            closing_px=closing_px,
            first_top=first_top,
            continuation_top=continuation_top,
            safety=safety,
        )
        chunk = []
        while index < len(rows):
            # ⚠️ LV-248: **una hoja que no es la última no se lleva la última fila.**
            # Sin esto, cuando todas las filas caben en la primera hoja —cuyo
            # presupuesto *no* descuenta el cierre, porque no es la última—, la hoja
            # final queda vacía, se descarta más abajo, y la primera pasa a ser la
            # última **sin el espacio del cierre**: la observación, la leyenda y las
            # solicitudes en trámite quedan bajo el pie, donde `overflow: hidden` las
            # recorta en silencio. Lo destapó acortar las filas: con los operadores
            # listados medían 60 px y once no cabían nunca en una hoja; con la
            # cantidad miden 45, y las once de producción (495 px) entraban justo en
            # los 500 de la primera. Guardar una fila para la última obliga a que la
            # hoja que carga el cierre tenga filas, y por lo tanto su presupuesto —el
            # que sí descuenta el cierre— se verifica.
            if sheet < sheets - 1 and index == len(rows) - 1:
                break
            cost = estimate(rows[index])
            if chunk and cost > budget:
                break
            budget -= cost
            chunk.append(rows[index])
            index += 1
        out.append(chunk)
    if index < len(rows):
        return None
    # Las hojas de más quedan vacías cuando el reparto sobra; se descartan para
    # no emitir una hoja en blanco con su pie numerado.
    return [chunk for chunk in out if chunk] or [[]]


def sheets_for(
    rows,
    *,
    closing_px=CLOSING_PX,
    estimate=row_px,
    first_top=FIRST_SHEET_ROW_TOP_PX,
    continuation_top=CONTINUATION_ROW_TOP_PX,
    safety=SAFETY_PX,
):
    """Las hojas de la sección, cada una con lo que la plantilla necesita saber.

    Devuelve `[{rows, first, last}]`. El **número de página** no se asigna acá a
    propósito: depende de cuántas hojas traen las otras secciones, y sólo la
    vista que arma el documento entero lo sabe. Repartirlo en dos lugares es cómo
    un informe termina con dos hojas numeradas igual.
    """
    chunks = paginate(
        rows,
        closing_px=closing_px,
        estimate=estimate,
        first_top=first_top,
        continuation_top=continuation_top,
        safety=safety,
    )
    return [
        {
            "rows": chunk,
            "first": index == 0,
            "last": index == len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]


# == LV-378 · El reparto del diseño 2 ==========================================
#
# La sección 2 del diseño 2 reparte **faenas**, no permisos: la unidad que no se parte
# es el bloque de una faena (cabecera, sublíneas y folios). Las constantes salen de
# **medir en el navegador** el informe renderizado (Edge, el caso ficticio de
# `v2_case.py` con once faenas; `getBoundingClientRect` sobre cada bloque), **no** de
# la propuesta del diseño, que daba 440 y 78:
#
# | | medido | usado |
# |---|---|---|
# | Tira de vencimientos: arriba de ella (cabecera, título, rótulo de dos líneas, leyenda) | 224,9 | 225 |
# | Separación entre bloques | 6 (faena) / 11 (sección) | |
# | Primera faena en una hoja de continuación | 224,9 | 225 |
# | Faena de una línea, detalle (aeronaves, operadores y folios) de un renglón (48 + 5 de margen) | 53 | 53 |
# | Renglón de detalle de más | 15,5 | 16 |
# | Faena con sublíneas: cabecera, y por cada sublínea con un renglón de detalle | 35,5 / 42 | 36 / 42 |
# | Bloque «sin operación»: título (28,3 + bordes) y fila de dos renglones | 30,3 / 43 | 31 / 44 |
# | Bloque «en trámite»: fila | 25,5 | 26 |
# | Bloque «vencidos sin cerrar»: fila | 27,5 | 28 |
# | Observación del período: rótulo + caja, y cada renglón de texto | 42 / 17,25 | 42 / 18 |
# | Pie | 1059,9 | `FOOTER_TOP_PX` |
#
# ⚠️ Sigue siendo una estimación: el ancho real de cada texto decide cuántos caben en un
# renglón. El detalle de 145 caracteres midió dos renglones y uno de 85 midió uno, así
# que `V2_DETAIL_CHARS_PER_LINE` se fija en **100**, por debajo de lo que caben (~112):
# equivocarse por exceso deja un hueco, por defecto recorta. Lo contienen el margen de
# una hoja (`V2_SAFETY_PX`), el total declarado en el rótulo de cada hoja y la
# invariante I8 (`invariants.py`). Y `TestThePrintedPdfIsWhatTheSheetsPredict` imprime a
# PDF con Edge y compara las páginas contra esta predicción.
V2_STRIP_TOP_PX = 225
V2_SECTION_GAP_PX = 11
V2_CONTINUATION_TOP_PX = 225
V2_GROUP_BASE_PX = 53
V2_DETAIL_LINE_PX = 16
V2_DETAIL_CHARS_PER_LINE = 100
V2_MULTI_HEAD_PX = 36
V2_LINE_PX = 42
V2_BLOCK_TITLE_PX = 31
V2_OUTSIDE_ROW_PX = 44
V2_AWAITING_ROW_PX = 26
V2_LAPSED_ROW_PX = 28
V2_OBSERVATION_BASE_PX = 42
V2_OBSERVATION_LINE_PX = 18
#: Caracteres por renglón de la observación (11,5 px en 690 px de ancho útil menos relleno).
V2_OBSERVATION_CHARS = 90
#: El pie de las hojas del diseño 2 va a 11,3 px y empieza en **1055,5**, no en 1060
#: (medido, con notas de dos renglones): el margen de seguridad absorbe la diferencia
#: en vez de pasar un tope distinto por todas las funciones.
V2_FOOTER_SHIFT_PX = 5
V2_MARGIN_PX = 30
V2_SAFETY_PX = V2_MARGIN_PX + V2_FOOTER_SHIFT_PX


def _detail_lines(line):
    """Renglones del detalle de una línea: aeronaves, operadores y folios en un párrafo.

    Por caracteres: el ancho real de cada texto decide cuántos caben. Se cuenta con
    `V2_DETAIL_CHARS_PER_LINE` por renglón (de más, no de menos) para no recortar.
    """
    tails = line.get("aircraft") or []
    folios = line.get("folios") or []
    chars = (
        len("Aeronaves: ")
        + sum(len(tail) + 3 for tail in tails)
        + len("12 operadores · Folios: ")
        + sum(len(folio) + 3 for folio in folios)
    )
    return max(1, -(-chars // V2_DETAIL_CHARS_PER_LINE))


def v2_first_top_px(strip_height):
    """Dónde cae la primera faena en la primera hoja: arriba de la tira, la tira (su
    alto varía con las filas de rótulos que pida) y la separación."""
    return V2_STRIP_TOP_PX + strip_height + V2_SECTION_GAP_PX


def group_px(group):
    """El alto estimado del bloque de una faena del diseño 2.

    Una faena de una sola línea (todos sus permisos con la misma vigencia, aeronaves
    y operadores) cuesta lo de base más las líneas de folios que pasen de una. Una
    faena con sublíneas cuesta su cabecera más, por cada sublínea, su cuerpo y sus
    propias líneas de folios de más.
    """
    lines = group["lines"]
    if len(lines) == 1:
        return V2_GROUP_BASE_PX + V2_DETAIL_LINE_PX * (_detail_lines(lines[0]) - 1)
    cost = V2_MULTI_HEAD_PX
    for line in lines:
        cost += V2_LINE_PX + V2_DETAIL_LINE_PX * (_detail_lines(line) - 1)
    return cost


def observation_px(note=""):
    """Alto de la observación del período: su rótulo y su caja, que crece con el texto."""
    lines = max(2, -(-len(note or "") // V2_OBSERVATION_CHARS))
    return V2_OBSERVATION_BASE_PX + V2_OBSERVATION_LINE_PX * lines + V2_SECTION_GAP_PX


def closing_px_v2(groups, note=""):
    """Lo que cierra la sección 2 v2 en su última hoja: los bloques de debajo y la
    observación del período. Cada bloque cuesta su título, sus filas y la separación."""
    cost = observation_px(note)
    for rows, per_row in (
        (groups["outside"], V2_OUTSIDE_ROW_PX),
        (groups["awaiting"], V2_AWAITING_ROW_PX),
        (groups["lapsed"], V2_LAPSED_ROW_PX),
    ):
        if rows:
            cost += V2_BLOCK_TITLE_PX + per_row * len(rows) + V2_SECTION_GAP_PX
    return cost


# -- La cobertura y el anexo del diseño 2 (PR 3) --------------------------------------
#
# Medidos en el navegador igual que los de arriba (ver la tabla en el commit y en
# `MASTER_PLAN.md`, `LV-378`). El plan compacto **no cambia** (es la misma sección 4 de
# siempre, en las clases de la hoja base): se usan sus medidas de arriba.
#
# | | medido | usado |
# |---|---|---|
# | Primera fila de faena (título, universo de dos renglones, barra, encabezado) | 284,1 | 285 |
# | Alto de una fila de faena | 27,9 | 28 |
# | Total + concentración (de tres renglones) + separaciones, sin faenas sin operación | 110,8 | 114 |
# | Bloque «sin operación»: relleno y línea del total legal | 40 | 40 |
# | Una faena sin operación más en ese bloque | 16,1 | 17 |
# | Anexo: primera fila (título, rótulo, encabezado) | 209,8 | 210 |
# | Anexo: fila de un renglón | 25,9 | 26 |
# | Anexo: renglón de más / nota bajo la tabla (con su separación) | 15 / 21 | 15 / 22 |
V2_COVERAGE_FIRST_ROW_TOP_PX = 285
V2_COVERAGE_ROW_PX = 28
V2_COVERAGE_TAIL_PX = 114
V2_COVERAGE_OUTSIDE_BLOCK_PX = 40
V2_COVERAGE_OUTSIDE_ROW_PX = 17
V2_ROSTER_FIRST_TOP_PX = 210
V2_ROSTER_CONTINUATION_TOP_PX = 210
V2_ROSTER_ROW_BASE_PX = 26
V2_ROSTER_LINE_PX = 15
V2_ROSTER_NOTE_PX = 22
#: Caracteres que caben en el renglón de operadores del anexo (296 px útiles a 11,5 px,
#: nombres de ancho medio): se cuenta con 44, por defecto, para no recortar.
V2_ROSTER_CHARS_PER_LINE = 44


def plan_fits_with_coverage_v2(cost_centres, matrix_rows, outside_rows=0):
    """¿Caben la tabla de faenas del diseño 2 y el plan compacto en la misma hoja?

    Igual que `plan_fits_with_coverage`, con las alturas del diseño 2: más altas
    (letra de 8,5 pt), la barra apilada arriba y, abajo, el total, las líneas de las
    faenas sin operación y la concentración. Con margen (`V2_SAFETY_PX`): equivocarse
    por exceso manda el plan a su hoja; por defecto, lo recortaría bajo el pie.
    """
    coverage = (
        V2_COVERAGE_FIRST_ROW_TOP_PX
        + V2_COVERAGE_ROW_PX * max(cost_centres, 1)
        + V2_COVERAGE_TAIL_PX
        + (V2_COVERAGE_OUTSIDE_BLOCK_PX if outside_rows else 0)
        + V2_COVERAGE_OUTSIDE_ROW_PX * outside_rows
    )
    plan = PLAN_BLOCK_BASE_PX + PLAN_MATRIX_ROW_PX * matrix_rows
    return coverage + plan + V2_SAFETY_PX <= FOOTER_TOP_PX


def roster_row_px_v2(row):
    """El alto estimado de una fila del anexo «registro permiso a permiso»."""
    names = row.get("operators") or []
    # Por caracteres y no por cantidad de nombres: a 11,5 px caben uno o dos por renglón
    # según su largo, y contar dos siempre recortaría las filas de nombres largos.
    chars = sum(len(name) for name in names) + 3 * max(len(names) - 1, 0)
    lines = max(1, -(-chars // V2_ROSTER_CHARS_PER_LINE))
    return V2_ROSTER_ROW_BASE_PX + V2_ROSTER_LINE_PX * (lines - 1)
