"""LV-381 F0: la barra lateral queda fija y el modo icono muestra todos los destinos.

Cuatro defectos medidos en el navegador sobre `origin/main 21ba8fc`:

- V1: `.sidebar` era `sticky` pero el `d-flex` del padre la estiraba hasta el alto
  de la pagina (8641 px), asi que el `sticky` no tenia recorrido y el menu se iba
  con el scroll. La barra superior tampoco era fija.
- V2: en modo icono faltaban 17 de 24 destinos: la regla de LV-170 que muestra los
  grupos plegados perdia contra `[hidden] { display: none !important }` de
  Bootstrap (el mismo choque de LV-209). El test de LV-170 solo comprobaba que el
  *texto* de la regla existiera, que es como paso inadvertido.
- V3: sin desplazamiento propio, Administracion caia bajo el borde en 1366x768.
- V4: `.sidebar-label:first-of-type` calzaba con cada titulo de grupo y borraba la
  linea que separa los grupos.

La prueba de V2 **ejecuta** la cascada en vez de buscar texto: lee la declaracion
`!important` de Bootstrap y exige que la regla del rail tambien lo sea y tenga mas
especificidad. Una regla igual de sensata sin `!important` es exactamente la que
fallaba.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
APP_CSS = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "static" / "vendor" / "bootstrap" / "bootstrap.min.css").read_text(
    encoding="utf-8"
)
BASE = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
_COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL)
MARKUP = _COMMENT.sub("", BASE)


def _rule_body(css: str, selector: str) -> str:
    """Cuerpo de la primera regla cuyo selector es exactamente `selector`."""
    pattern = re.compile(
        r"(?:^|[};])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", re.M
    )
    match = pattern.search(css)
    assert match, f"no hay una regla con el selector {selector!r}"
    return match.group(1)


def _specificity(selector: str) -> tuple[int, int, int]:
    """(ids, clases/atributos/pseudoclases, elementos) de un selector simple."""
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+", selector))
    stripped = re.sub(r"#[\w-]+|\.[\w-]+|\[[^\]]+\]|::?[\w-]+", " ", selector)
    elements = len(re.findall(r"(?<![\w-])[a-zA-Z][\w-]*", stripped))
    return ids, classes, elements


def test_the_sidebar_has_room_to_stick_and_scrolls_on_its_own():
    """V1/V3: sin `align-self` y alto propio el `sticky` no hace nada."""
    body = _rule_body(APP_CSS, ".sidebar")

    assert "position: sticky" in body
    assert "align-self: flex-start" in body
    assert re.search(r"top:\s*var\(--ac-sidebar-top,\s*61px\)", body)
    assert re.search(r"height:\s*calc\(100dvh\s*-\s*var\(--ac-sidebar-top", body)
    assert "min-height: calc(100vh - 58px)" not in APP_CSS


def test_only_the_group_zone_scrolls():
    body = _rule_body(APP_CSS, ".sidebar-scroll")

    assert "overflow-y: auto" in body
    assert "min-height: 0" in body


def test_the_admin_footer_is_outside_the_scroll_zone():
    """El pie de administracion no se desplaza: va despues de cerrar el scroll."""
    scroll_open = MARKUP.index('<div class="sidebar-scroll">')
    admin = MARKUP.index('<div class="nav-admin-zone">')
    between = MARKUP[scroll_open:admin]

    assert between.rstrip().endswith("</div>")
    assert between.count("<div") == between.count("</div>")
    # Y el tirador del ancho, tambien fuera: dentro se iria con el contenido.
    assert MARKUP.index('class="sidebar-resizer"') > admin


def test_the_top_bar_is_fixed_too():
    # Hay dos reglas con este selector (la segunda es la que manda): se leen todas.
    bodies = re.findall(
        r"(?:^|[};])\s*\.navbar-dark\.navy\s*\{([^}]*)\}", APP_CSS, re.M
    )
    body = "\n".join(bodies)

    assert "position: sticky" in body
    assert "top: var(--ac-banner-h, 0px)" in body


def test_the_icon_rail_rule_beats_the_bootstrap_hidden_rule():
    """V2, ejecutado: la regla del rail tiene que ganar la cascada de verdad."""
    bootstrap_hidden = re.search(
        r"\[hidden\]\s*\{\s*display:\s*none\s*!important", BOOTSTRAP
    )
    assert bootstrap_hidden, "Bootstrap ya no declara [hidden] con !important: revisar"

    selector = ".sidebar.is-collapsed .nav-group-items[hidden]"
    declaration = _rule_body(APP_CSS, selector)
    ours = re.search(r"display:\s*flex\s*(!important)?", declaration)

    assert ours, "la regla del rail ya no fija display:flex"
    # Ambas importantes: decide la especificidad, y la nuestra es mayor.
    assert ours.group(1) == "!important", (
        "sin !important pierde contra [hidden]{display:none!important}: "
        "en modo icono faltan 17 de 24 destinos"
    )
    assert _specificity(selector) > _specificity("[hidden]")


@pytest.mark.parametrize("name", ["costcenter-list", "operator-list", "battery-list"])
def test_every_group_keeps_its_rows_in_the_rail(name):
    """Los grupos siguen siendo `.nav-group-items` con `id`, para el JS y el rail."""
    assert f"{{% url '{name}' %}}" in MARKUP


def test_group_titles_keep_their_separator_line():
    """V4: el selector `:first-of-type` ya no puede calzar con cada titulo."""
    assert not re.search(r"\.sidebar-label:first-of-type\s*\{", APP_CSS)
    assert ".nav-shortcuts-label,\n.nav-admin-label { border-top: 0" in APP_CSS


def test_the_rail_separates_groups_with_a_line_since_it_hides_the_titles():
    assert ".sidebar.is-collapsed .nav-group + .nav-group" in APP_CSS
