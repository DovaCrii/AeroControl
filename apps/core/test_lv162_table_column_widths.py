"""LV-162: el reparto de columnas de los listados normalizados.

Reportado por el usuario con captura el 2026-08-27, mirando Operadores: el
encabezado "CENTRO DE COSTO" se salía **encima** de "HABILITACIONES".

La causa no era un ancho mal puesto sino el reparto al revés de lo que pide el
contenido. `col-flex` existe para absorber el sobrante y se le había dado al dato
más corto —el código de la faena, cinco caracteres—, así que absorbió el sobrante
más chico: 93 px medidos en el navegador, para un encabezado de 125. Y al revés,
la habilitación —texto libre de la DGAC, lo único que de verdad necesita ancho—
se truncaba en cuatro de las diez filas.

**El sistema de anchos de `LV-57` no tenía ningún guardián**, y por eso pudo
derivar: `LV-152` convirtió la habilitación de insignia a texto libre y movió su
`col-text`, pero nadie movió el `col-flex`. Estos tests son ese guardián.

Se lee el archivo y no una página renderizada: el reparto es una decisión de la
plantilla, y varias de estas listas están tras un permiso que una página
cualquiera no ejercita.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / "templates"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

_COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL)


def _without_comments(markup):
    """Los bloques comentados no se dibujan, así que no cuentan como columnas."""
    return _COMMENT.sub("", markup)


def _block(markup, name):
    match = re.search(
        r"\{%\s*block\s+" + name + r"\s*%\}(.*?)\{%\s*endblock\s*%\}",
        markup,
        re.DOTALL,
    )
    return match.group(1) if match else ""


def _normalized_lists():
    """Cada plantilla que opta por los anchos normalizados, con sus columnas.

    Devuelve (ruta relativa, [roles de cada <col>], [encabezados]).
    """
    found = []
    for path in TEMPLATES.rglob("*.html"):
        markup = _without_comments(path.read_text(encoding="utf-8"))
        if "table-normalized" not in _block(markup, "list_table_class"):
            continue
        colgroup = _block(markup, "list_colgroup")
        roles = re.findall(r'<col\s+class="([^"]+)"', colgroup)
        headers = re.findall(
            r"<th\b[^>]*>(.*?)</th>", _block(markup, "list_header"), re.DOTALL
        )
        found.append((path.relative_to(TEMPLATES).as_posix(), roles, headers))
    return found


def test_the_normalized_lists_are_actually_being_read():
    """El guardián del guardián: si el parseo deja de calzar, todo lo de abajo
    pasaría en verde sin haber mirado una sola columna."""
    lists = _normalized_lists()

    assert len(lists) >= 4, [name for name, _r, _h in lists]
    names = {name for name, _roles, _headers in lists}
    assert "registry/operator_list.html" in names
    assert all(roles for _name, roles, _headers in lists)


@pytest.mark.parametrize("name, roles, headers", _normalized_lists())
def test_every_declared_role_has_a_width_in_the_stylesheet(name, roles, headers):
    """Un `<col class="col-loquesea">` sin regla en `app.css` **no es un error
    visible**: se comporta como `auto`, y con dos columnas `auto` el sobrante se
    parte entre ellas. Pasó exactamente eso mientras se arreglaba esta fila —el
    navegador tenía el CSS viejo, `col-icon` todavía no existía, y las dos
    columnas de la derecha salieron con 265 px cada una— así que este test es el
    que caza una clase mal escrita."""
    stylesheet = CSS.read_text(encoding="utf-8")

    for role in roles:
        for token in role.split():
            assert f".table-normalized .{token}" in stylesheet, (
                f"{name}: '{token}' no tiene ancho declarado, así que queda auto"
            )


@pytest.mark.parametrize("name, roles, headers", _normalized_lists())
def test_the_colgroup_covers_every_column(name, roles, headers):
    """`generic/list.html` agrega el `<th>` de Acciones **fuera** del bloque, así
    que el colgroup lleva un `<col>` más que encabezados. Si sobran encabezados,
    las columnas de la cola se quedan sin ancho y vuelven al reparto
    automático."""
    assert len(roles) == len(headers) + 1, (
        f"{name}: {len(roles)} <col> para {len(headers)} <th> + Acciones"
    )
    assert roles[-1] == "col-actions", f"{name}: la última columna no es la de acción"


@pytest.mark.parametrize("name, roles, headers", _normalized_lists())
def test_exactly_one_column_absorbs_the_slack(name, roles, headers):
    """La regla del sistema, escrita en el comentario de `app.css` desde `LV-57`
    y nunca comprobada: cada lista deja **una** columna sin ancho para que los
    porcentajes no tengan que sumar exacto. Con ninguna, el sobrante se reparte
    solo y los porcentajes mandan; con dos, se parte entre ambas y ninguna queda
    con el ancho que su contenido pide."""
    flexible = [role for role in roles if role in {"col-flex", "col-chips"}]

    assert len(flexible) == 1, f"{name}: {len(flexible)} columnas flexibles"


def test_on_the_operator_list_the_slack_goes_to_the_free_text_column():
    """La decisión de esta fila, fijada por posición.

    La habilitación es texto libre que escribe la DGAC (`LV-152`), o sea la única
    columna de esa lista cuyo largo no se puede acotar. Es la que tiene que
    absorber el sobrante; dárselo al código de la faena es lo que produjo la
    colisión que el usuario reportó.
    """
    name, roles, headers = next(
        entry
        for entry in _normalized_lists()
        if entry[0] == "registry/operator_list.html"
    )

    flex_at = roles.index("col-flex")
    assert "Qualifications" in headers[flex_at], headers[flex_at]
    # Y el código de la faena vuelve a un ancho declarado.
    cost_center_at = next(i for i, h in enumerate(headers) if "Cost center" in h)
    assert roles[cost_center_at] == "col-compact"


def _every_normalized_table():
    """LV-254: las listas normalizadas de **las dos familias de bloques**.

    `_normalized_lists` sólo lee `list_*`, así que no veía las que heredan
    directamente de `generic/worktable.html` (planes geo, documentos, no
    conformidades), que declaran `worktable_table_class`/`worktable_colgroup`.

    Devuelve (ruta relativa, [roles], cantidad de columnas del encabezado). En la
    familia `list_*`, `generic/list.html` agrega el `<th>` de Acciones fuera del
    bloque; en la `worktable_*`, la lista lo escribe (o no) dentro del suyo.
    """
    header_cell = re.compile(r"<th\b|\{%\s*worktable_th\b")
    found = []
    for path in TEMPLATES.rglob("*.html"):
        markup = _without_comments(path.read_text(encoding="utf-8"))
        for family, actions_outside in (("list", 1), ("worktable", 0)):
            if "table-normalized" not in _block(markup, f"{family}_table_class"):
                continue
            roles = re.findall(
                r'<col\s+class="([^"]+)"', _block(markup, f"{family}_colgroup")
            )
            columns = (
                len(header_cell.findall(_block(markup, f"{family}_header")))
                + actions_outside
            )
            found.append((path.relative_to(TEMPLATES).as_posix(), roles, columns))
    return found


def _widths():
    """Los anchos tal como los declara `app.css`: `{rol: (valor, unidad)}` y el
    `min-width` de la tabla. Se leen del archivo para que el cálculo de abajo no
    se quede con números viejos el día que alguien cambie un ancho."""
    stylesheet = CSS.read_text(encoding="utf-8")
    widths = {
        role: (float(value), unit)
        for role, value, unit in re.findall(
            r"\.table-normalized \.(col-[\w-]+)\s*\{\s*width:\s*([\d.]+)(%|px);",
            stylesheet,
        )
    }
    table_rule = re.search(r"\.table-normalized\s*\{([^}]*)\}", stylesheet)
    min_width = float(re.search(r"min-width:\s*(\d+)px", table_rule.group(1))[1])
    return widths, min_width


def test_every_normalized_table_is_being_read():
    tables = {name for name, _roles, _columns in _every_normalized_table()}

    for expected in (
        "registry/operator_list.html",
        "geo/plan_list.html",
        "compliance/document_list.html",
    ):
        assert expected in tables, sorted(tables)


@pytest.mark.parametrize("name, roles, columns", _every_normalized_table())
def test_every_table_declares_one_col_per_column(name, roles, columns):
    assert len(roles) == columns, f"{name}: {len(roles)} <col> para {columns} columnas"
    stylesheet = CSS.read_text(encoding="utf-8")
    for role in roles:
        assert f".table-normalized .{role}" in stylesheet, f"{name}: {role} sin ancho"
    flexible = [role for role in roles if role in {"col-flex", "col-chips"}]
    assert len(flexible) == 1, f"{name}: {len(flexible)} columnas flexibles"


# Un nombre de dos palabras a 14 px. Por debajo, la columna que existe para el
# texto largo es la más angosta de la fila.
MIN_FLEX_PX = 120


@pytest.mark.parametrize("name, roles, columns", _every_normalized_table())
def test_the_flexible_column_keeps_room_at_the_narrowest_width(name, roles, columns):
    """⚠️ **El defecto que el guardián del `colspan` no podía ver.**

    La columna flexible se queda con lo que sobra después de los porcentajes y
    los anchos fijos. La lista de permisos de `LV-246` sumaba 90 % + 110 px, y
    medido en el navegador a 910 px «Operadores» tenía **0 px** — con el
    `colspan` exacto, una columna por encabezado y todo lo demás en verde.

    Se calcula al ancho mínimo de la tabla, que es donde el sobrante es menor, y
    se suma la casilla de selección que `worktable.js` inyecta con su `<col>`.
    """
    widths, table_px = _widths()
    percent = widths["col-select"][0]
    fixed_px = 0.0
    for role in roles:
        if role in {"col-flex", "col-chips"}:
            continue
        value, unit = widths[role]
        if unit == "%":
            percent += value
        else:
            fixed_px += value

    slack = table_px * (1 - percent / 100) - fixed_px

    assert slack >= MIN_FLEX_PX, (
        f"{name}: a {table_px:.0f} px la columna flexible queda con {slack:.0f} px "
        f"({percent:.0f} % + {fixed_px:.0f} px fijos)"
    )


def test_the_normalized_header_wraps_instead_of_overflowing():
    """`.table th` fija `nowrap` a propósito, y el comentario que lo justifica
    cierra con "la tabla vive en .table-responsive, así que un encabezado ancho
    scrollea en vez de romper el layout". Eso es cierto con reparto automático y
    **falso** con `table-layout: fixed`: el encabezado no ensancha la tabla, así
    que no scrollea, se sale encima de la vecina.

    Medido: a 900 px —el `min-width` de esta tabla— "Centro de costo" pide 125 px
    y su columna da 108, así que sin esta regla la colisión vuelve en cuanto
    alguien angosta la ventana, con los anchos bien repartidos y todo.
    """
    stylesheet = CSS.read_text(encoding="utf-8")
    rule = re.search(
        r"\.table-normalized thead th\s*\{([^}]*)\}", stylesheet, re.DOTALL
    )

    assert rule, "falta la regla que deja envolver al encabezado"
    assert "white-space: normal" in rule.group(1)
    assert "overflow-wrap: break-word" in rule.group(1)
