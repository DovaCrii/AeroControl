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
FOOTER_TOP_PX = 1060
FIRST_SHEET_ROW_TOP_PX = 515
CONTINUATION_ROW_TOP_PX = 205
#: Una fila de una sola línea en sus celdas multivaluadas.
ROW_BASE_PX = 45
#: Lo que suma cada línea envuelta de más. Es la diferencia medida entre la fila
#: de dos operadores (45 px, una línea de nombres) y la de cuatro (60 px, dos
#: líneas). Equivocarse por exceso deja un hueco en la hoja; por defecto, recorta
#: una fila — así que cuando haya duda, este número sube.
ROW_LINE_PX = 15
#: Cuántos nombres caben en una línea de la celda de operadores designados. La
#: columna es `1fr` de una rejilla de siete y el cuerpo baja a 8,2 px justamente
#: para que quepan (`.rpt-people`), así que entran dos nombres completos.
NAMES_PER_LINE = 2
#: Observación del período + leyenda de bandas, que cierran la sección y por eso
#: van sólo en la última hoja.
CLOSING_PX = 133
#: Una fila de margen por hoja. Absorbe el residuo de la estimación: la celda de
#: nombres envuelve según el ancho real de cada nombre, que esto no mide.
SAFETY_PX = ROW_BASE_PX


def row_px(row):
    """El alto estimado de una fila, por su contenido.

    Las dos celdas que crecen son las multivaluadas —operadores designados y
    aeronaves— y manda la más alta: van una al lado de la otra, así que la fila
    mide lo que mida la peor.

    Las aeronaves van una por línea (la plantilla las separa con `<br>`); los
    nombres van corridos y envuelven de dos en dos.
    """
    names = len(row.get("operators") or [])
    tails = len(row.get("aircraft") or [])
    name_lines = -(-names // NAMES_PER_LINE) if names else 1
    lines = max(name_lines, tails or 1, 1)
    return ROW_BASE_PX + ROW_LINE_PX * (lines - 1)


def sheet_budget_px(*, first, last, closing_px=CLOSING_PX):
    """Cuántos píxeles de filas caben en una hoja de la sección.

    `first` baja el techo porque esa hoja carga además el ciclo de vigencia y los
    cuatro indicadores; `last` lo baja porque cierra con la observación y la
    leyenda. Una sección de una sola hoja es las dos cosas, y ése es el caso más
    apretado.
    """
    top = FIRST_SHEET_ROW_TOP_PX if first else CONTINUATION_ROW_TOP_PX
    available = FOOTER_TOP_PX - top - (closing_px if last else 0) - SAFETY_PX
    return max(ROW_BASE_PX, available)


def paginate(rows, *, closing_px=CLOSING_PX):
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
        packed = _pack(rows, sheets, closing_px)
        if packed is not None:
            return packed
    # Inalcanzable: con `sheets == len(rows)` cada hoja lleva una fila, y
    # `sheet_budget_px` nunca devuelve menos que una fila base. Se deja explícito
    # en vez de un `assert` para que, si alguien baja `FOOTER_TOP_PX` por error,
    # el informe salga entero de una hoja en vez de salir vacío.
    return [rows]


def _pack(rows, sheets, closing_px):
    """Intenta meter `rows` en exactamente `sheets` hojas. `None` si no entran."""
    out, index = [], 0
    for sheet in range(sheets):
        budget = sheet_budget_px(
            first=sheet == 0, last=sheet == sheets - 1, closing_px=closing_px
        )
        chunk = []
        while index < len(rows):
            cost = row_px(rows[index])
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


def sheets_for(rows, *, closing_px=CLOSING_PX):
    """Las hojas de la sección, cada una con lo que la plantilla necesita saber.

    Devuelve `[{rows, first, last}]`. El **número de página** no se asigna acá a
    propósito: depende de cuántas hojas traen las otras secciones, y sólo la
    vista que arma el documento entero lo sabe. Repartirlo en dos lugares es cómo
    un informe termina con dos hojas numeradas igual.
    """
    chunks = paginate(rows, closing_px=closing_px)
    return [
        {
            "rows": chunk,
            "first": index == 0,
            "last": index == len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
