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

**`LV-381` cambió dos cosas de este archivo, a propósito.** F1: el menú sale de
`apps/core/navigation.py`, así que se lee el registro y el menú renderizado con
un usuario que lo puede todo (antes, el texto de `base.html`). F2: de seis grupos
a cinco (*Vuelo, Cumplimiento, Informes, Flota y personal, Faenas y movimientos*)
con los mismos veinticuatro destinos; los tests de reparto de arriba describen
el reparto de F2 y el docstring del principio, el de `LV-170`.

Varias filas están tras un permiso que una petición cualquiera no ejercita, y
por eso se lee el menú completo y no una página.

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

from apps.core.navigation import NAV_FOOTER, NAV_GROUPS, NAV_TOP
from apps.core.testing import full_sidebar_html

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
APP_JS = Path(settings.BASE_DIR) / "static" / "js" / "app.js"

# El mínimo medido en el navegador: 248 px de la fila más larga + 24 de relleno.
MIN_SIDEBAR_WIDTH = 272


@pytest.fixture(scope="module")
def markup():
    """El menú **renderizado** con todas las entradas.

    `LV-381` F1: el menú ya no está escrito en `base.html` sino que sale del
    registro (`apps/core/navigation.py`), así que el guardián lo lee renderizado
    con un usuario que lo puede todo: el mismo código que ejecuta quien lo usa.
    """
    return full_sidebar_html()


@pytest.fixture(scope="module")
def groups():
    """{nombre del grupo: sus nombres de URL}, leído del registro."""
    return {group.key: {item.url_name for item in group.items} for group in NAV_GROUPS}


def test_the_five_groups_are_there(groups):
    """`LV-381` F2 (D2 del diseño): de seis grupos a cinco, con los mismos
    veinticuatro destinos. «Mantenimiento» tenía una sola entrada; «Padrón» e
    «Inventario y movimientos» se reparten entre *Flota y personal* (lo que se
    opera y se mantiene) y *Faenas y movimientos* (dónde está cada cosa)."""
    assert set(groups) == {"flight", "compliance", "reports", "fleet", "sites"}


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


def test_flight_holds_the_permission_flow_and_the_environment(groups):
    """«Entorno» (LV-358) pasa a Vuelo: se consulta para decidir si se vuela."""
    assert groups["flight"] == {
        "permission-list",
        "geo-plan-list",
        "record-list",
        "environment-hub",
    }


def test_compliance_keeps_the_monthly_close_and_what_backs_it(groups):
    """La bandeja y las alertas salen al bloque de arriba: son la cola de
    pendientes de cualquiera, no sólo de quien gestiona cumplimiento."""
    assert groups["compliance"] == {
        "monthly-review",
        "nonconformity-list",
        "company-documents",
    }


def test_fleet_and_personnel_hold_what_is_operated_and_maintained(groups):
    assert groups["fleet"] == {
        "aircraft-list",
        "battery-list",
        "maintenance-list",
        "operator-list",
        "assessment-take",
    }


def test_sites_and_movements_hold_where_each_thing_is(groups):
    assert groups["sites"] == {
        "costcenter-list",
        "operatorassignment-list",
        "aircraftassignment-list",
        "resourcemovementlog-list",
    }


def test_the_menu_keeps_exactly_the_same_destinations(groups):
    """F2 reagrupa y renombra; **no suma ni quita** un destino. Son los
    veinticuatro de siempre (entre ellos, «Entorno»)."""
    everything = {item.url_name for item in (*NAV_TOP, *NAV_FOOTER)}
    everything |= set().union(*groups.values())

    assert len(everything) == 24


def test_no_menu_row_is_left_outside_a_group(markup, groups):
    """Una fila suelta se dibuja pegada al grupo anterior y parece suya.

    ⚠️ Mide la región del menú y nada más. Antes leía `base.html` hasta
    `</aside>` (y, antes todavía, hasta el final del archivo, que `UX-25` rompió
    al poner `{% url 'global-search' %}` en un `data-*` de la paleta: un destino
    que no es una fila de menú, contado como si lo fuera). Desde `LV-381` F1 la
    región es el menú renderizado, así que la paleta ni entra. Un guardián que se
    equivoca de región acusa a quien no toca lo que él vigila.
    """
    everything = {item.url_name for item in (*NAV_TOP, *NAV_FOOTER)}
    grouped = set().union(*groups.values())
    # Fuera de grupo sólo el bloque sin título de arriba (panel, bandeja y
    # alertas, LV-381 F2) y el pie de administración.
    assert everything == {
        "dashboard",
        "work-tray",
        "alert-list",
        "administration",
        "admin:index",
    }
    assert grouped.isdisjoint(everything)
    # Y lo dibujado es exactamente eso: ninguna fila fuera de un grupo ni de los extremos.
    assert markup.count('class="nav-item') == len(everything) + len(grouped)


def test_every_toggle_points_at_the_container_it_folds(markup):
    """Un `aria-controls` mal escrito deja el botón sin efecto y sin aviso."""
    toggles = re.findall(r"<button[^>]*nav-group-toggle[^>]*>", markup)
    assert len(toggles) == 5
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


def test_the_open_groups_are_remembered_as_a_list():
    """Reescrito A PROPOSITO en `LV-381` F3 (D1).

    Antes se guardaba lo **plegado** para que un grupo nuevo naciera abierto
    (guardar los abiertos lo haria nacer invisible). La decision D1 pide guardar
    la **lista de abiertos** (`nav-groups-open`): el costo conocido es que un grupo
    que se agregue en el futuro aparece plegado para quien ya tenia una
    preferencia guardada, hasta que lo abra; se acepta porque el de la pagina
    activa siempre se abre solo y los grupos cambian rara vez (F2 fijo cinco).
    """
    source = APP_JS.read_text(encoding="utf-8")

    assert "nav-groups-open" in source
    assert "localStorage" in source


def test_the_group_of_the_current_page_is_opened_even_if_it_was_not_remembered():
    """Si no, la pantalla en la que estás parado no figura en el menú."""
    source = APP_JS.read_text(encoding="utf-8")

    assert ".nav-group-items .nav-item.active" in source
