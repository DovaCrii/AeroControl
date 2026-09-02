"""LV-170: el menú se reparte en grupos que se pliegan, y ninguna fila se corta.

Pedido del usuario sobre la app desplegada. Tres cosas en una:

- **Padrón tenía nueve entradas de las veinte del menú**, así que era el grupo
  que empujaba a todos los demás fuera de la pantalla. Se parte: lo que se da de
  alta una vez (faenas, aeronaves, operadores, la prueba) se queda en *Padrón*;
  lo que se mueve todos los días (baterías, asignaciones, bitácora) pasa a
  *Inventario y movimientos*.
- **El catastro y el reporte se buscaban juntos y estaban separados** — uno en
  Padrón y el otro en Cumplimiento—, y por eso el usuario los confundió. Ahora
  comparten el grupo *Informes*.
- **La barra medía 248 px y cortaba cuatro filas.** Medido en el navegador con
  esta misma hoja: la más larga pide 248 px de texto y la barra incluye 24 de
  relleno, así que el mínimo real son **272**.

Se lee el archivo y no una página renderizada, como en `LV-162`: el reparto es
una decisión de la plantilla, y varias de estas filas están tras un permiso que
una petición cualquiera no ejercita.

**Lo que estos tests protegen no es el orden estético sino tres invariantes que
se rompen en silencio**: que un grupo plegado siga siendo alcanzable con la barra
en modo icono (donde su rótulo no se dibuja), que cada botón apunte al contenedor
que realmente pliega, y que ninguna fila vuelva a quedar sin grupo — una fila
suelta se dibuja pegada al grupo anterior y parece pertenecerle.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

BASE = Path(settings.BASE_DIR) / "templates" / "base.html"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
APP_JS = Path(settings.BASE_DIR) / "static" / "js" / "app.js"

# El mínimo medido en el navegador: 248 px de la fila más larga + 24 de relleno.
MIN_SIDEBAR_WIDTH = 272

_COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL)
_GROUP = re.compile(
    r'<div class="nav-group">\s*(?P<toggle><button[^>]*nav-group-toggle[^>]*>)'
    r"(?P<body>.*?)</div>\s*</div>",
    re.DOTALL,
)


@pytest.fixture(scope="module")
def markup():
    """La plantilla sin los bloques comentados: no se dibujan, no cuentan."""
    return _COMMENT.sub("", BASE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def groups(markup):
    """{nombre del grupo: sus urls}, leído de la plantilla."""
    found = {}
    for match in _GROUP.finditer(markup):
        name = re.search(r'data-nav-group="([^"]+)"', match.group("toggle")).group(1)
        found[name] = set(re.findall(r"\{%\s*url '([^']+)'", match.group("body")))
    return found


def test_the_six_groups_are_there(groups):
    assert set(groups) == {
        "flight",
        "compliance",
        "reports",
        "maintenance",
        "registry",
        "inventory",
    }


def test_reports_holds_the_roster_and_the_compliance_report_together(groups):
    """El usuario los confundió justamente porque estaban en grupos distintos.

    `monthly-report` se suma con `R3`: es el informe que se emite a la DGAC, y
    su lugar es junto a los otros dos y no en una sección propia. Que este test
    cayera al agregarlo es lo que se le pide — una fila nueva en el menú tiene
    que costar una decisión sobre en qué grupo va, no colarse.
    """
    assert groups["reports"] == {
        "registry-roster",
        "compliance-report",
        "monthly-report",
    }


def test_the_compliance_group_no_longer_holds_the_report(groups):
    assert "compliance-report" not in groups["compliance"]


def test_registry_keeps_only_what_is_set_up_once(groups):
    assert groups["registry"] == {
        "costcenter-list",
        "aircraft-list",
        "operator-list",
        "assessment-take",
    }


def test_inventory_takes_what_moves_every_day(groups):
    assert groups["inventory"] == {
        "operatorassignment-list",
        "aircraftassignment-list",
        "battery-list",
        "resourcemovementlog-list",
    }


def test_no_menu_row_is_left_outside_a_group(markup, groups):
    """Una fila suelta se dibuja pegada al grupo anterior y parece suya."""
    sidebar = markup[markup.index('<aside class="sidebar') :]
    everything = set(re.findall(r"\{%\s*url '([^']+)'", sidebar))
    grouped = set().union(*groups.values())
    # Fuera de grupo sólo el panel (encabeza el menú) y el pie de administración.
    assert everything - grouped == {"dashboard", "administration", "admin:index"}


def test_every_toggle_points_at_the_container_it_folds(markup):
    """Un `aria-controls` mal escrito deja el botón sin efecto y sin aviso."""
    toggles = re.findall(r"<button[^>]*nav-group-toggle[^>]*>", markup)
    assert len(toggles) == 6
    for toggle in toggles:
        controls = re.search(r'aria-controls="([^"]+)"', toggle).group(1)
        assert f'id="{controls}"' in markup
        assert 'aria-expanded="true"' in toggle, (
            "sin JS los grupos tienen que quedar abiertos: es el estado correcto "
            "para degradar"
        )


def test_the_group_label_is_a_button_and_not_a_span(markup):
    """Un `<span>` con click no llega por teclado ni se anuncia."""
    assert '<span class="sidebar-label">' not in markup


def test_a_folded_group_stays_reachable_with_the_bar_in_icon_mode():
    """Ahí el rótulo no se dibuja, así que no habría con qué desplegarlo."""
    assert ".sidebar.is-collapsed .nav-group-items[hidden]" in CSS.read_text("utf-8")


def test_the_sidebar_is_wide_enough_for_its_longest_row():
    """El ancho **por defecto** no puede cortar la fila más larga.

    LV-208: el patrón cambió y el regex viejo (`--ac-sidebar-width:\\s*(\\d+)px`)
    pasó a encontrar el **72px del estado colapsado** en vez del valor por
    defecto, así que el test empezó a fallar midiendo otra cosa. Ahora el valor
    por defecto vive en el fallback del `var()`, porque el ancho que el usuario
    fije arrastrando el borde tiene que poder ganarle.

    Sigue midiendo el **default** a propósito: que alguien elija estrechar la
    barra por debajo de estos 272 px es su decisión —el arrastre lo permite hasta
    240 y ahí los rótulos largos pasan a dos líneas—, pero nadie debería
    encontrarse la barra cortada sin haberla tocado.
    """
    match = re.search(
        r"--ac-sidebar-width:\s*var\(--ac-sidebar-width-user,\s*(\d+)px\)",
        CSS.read_text("utf-8"),
    )

    assert match, (
        "no se encontró el ancho por defecto de la barra: si el patrón del token "
        "volvió a cambiar, actualizar este regex -- ver LV-170 y LV-208"
    )
    assert int(match.group(1)) >= MIN_SIDEBAR_WIDTH, (
        f"medido en el navegador: hacen falta {MIN_SIDEBAR_WIDTH}px o se corta "
        '"Evaluación de conocimientos" -- ver LV-170'
    )


def test_the_folded_state_is_remembered_by_what_is_folded():
    """Guardar los abiertos haría nacer invisible a cualquier grupo nuevo."""
    source = APP_JS.read_text(encoding="utf-8")

    assert "nav-groups-collapsed" in source
    assert "localStorage" in source


def test_the_group_of_the_current_page_is_opened_even_if_it_was_folded():
    """Si no, la pantalla en la que estás parado no figura en el menú."""
    source = APP_JS.read_text(encoding="utf-8")

    assert ".nav-group-items .nav-item.active" in source
