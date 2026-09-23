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
FIRST_SHEET_ROW_TOP_PX = 344
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
    return ROW_BASE_PX + ROW_LINE_PX * (max(tails, 1) - 1)


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
    *, first, last, closing_px=CLOSING_PX, first_top=FIRST_SHEET_ROW_TOP_PX
):
    """Cuántos píxeles de filas caben en una hoja de la sección.

    `first` baja el techo porque esa hoja carga además el ciclo de vigencia y los
    cuatro indicadores; `last` lo baja porque cierra con la observación y la
    leyenda. Una sección de una sola hoja es las dos cosas, y ése es el caso más
    apretado. `first_top` deja que otra sección —el anexo, `LV-248`— declare dónde
    empieza su primera fila.
    """
    top = first_top if first else CONTINUATION_ROW_TOP_PX
    available = FOOTER_TOP_PX - top - (closing_px if last else 0) - SAFETY_PX
    return max(ROW_BASE_PX, available)


def paginate(
    rows,
    *,
    closing_px=CLOSING_PX,
    estimate=row_px,
    first_top=FIRST_SHEET_ROW_TOP_PX,
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
        packed = _pack(rows, sheets, closing_px, estimate, first_top)
        if packed is not None:
            return packed
    # Inalcanzable: con `sheets == len(rows)` cada hoja lleva una fila, y
    # `sheet_budget_px` nunca devuelve menos que una fila base. Se deja explícito
    # en vez de un `assert` para que, si alguien baja `FOOTER_TOP_PX` por error,
    # el informe salga entero de una hoja en vez de salir vacío.
    return [rows]


def _pack(rows, sheets, closing_px, estimate, first_top):
    """Intenta meter `rows` en exactamente `sheets` hojas. `None` si no entran."""
    out, index = [], 0
    for sheet in range(sheets):
        budget = sheet_budget_px(
            first=sheet == 0,
            last=sheet == sheets - 1,
            closing_px=closing_px,
            first_top=first_top,
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
):
    """Las hojas de la sección, cada una con lo que la plantilla necesita saber.

    Devuelve `[{rows, first, last}]`. El **número de página** no se asigna acá a
    propósito: depende de cuántas hojas traen las otras secciones, y sólo la
    vista que arma el documento entero lo sabe. Repartirlo en dos lugares es cómo
    un informe termina con dos hojas numeradas igual.
    """
    chunks = paginate(
        rows, closing_px=closing_px, estimate=estimate, first_top=first_top
    )
    return [
        {
            "rows": chunk,
            "first": index == 0,
            "last": index == len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
