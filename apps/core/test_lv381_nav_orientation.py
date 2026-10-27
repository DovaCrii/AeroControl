"""`LV-381` F3 (V8, V9, D1): el menú orienta también desde las fichas.

Tres cosas que antes fallaban:

- **V8**: en una ficha (`permission-detail`, `costcenter-detail`...) ningún destino
  del menú se marcaba activo y no había migas de pan; la persona no sabía en qué
  sección estaba. Ahora cada destino declara sus fichas (`detail_url_names`) y
  pantallas hijas (`active_url_names`) en el registro, y las migas
  `Grupo › Lista › ficha` salen de ese mismo registro.
- **V9**: el acordeón cerraba los demás grupos al abrir uno. Ahora son
  independientes (D1) y el de la página activa no se puede cerrar. El
  comportamiento es de JavaScript y el repo no tiene infraestructura para
  ejecutarlo, así que acá se afirma lo que Python puede ver; se verificó en el
  navegador demo.
- La clave de `localStorage` pasa a ser `nav-groups-open` (lista de abiertos).
"""

import re
from pathlib import Path

import pytest
from django.urls import get_resolver, reverse
from django.utils import translation

from apps.core.navigation import all_items, build_sidebar
from apps.core.testing import AllowEverything, login_as
from apps.registry.models import CostCenter

APP_JS = Path("static/js/app.js")


def _url_names():
    return {key for key in get_resolver().reverse_dict if isinstance(key, str)}


def _menu(body):
    return body[body.index('<aside class="sidebar') : body.index("</aside>")]


def test_every_declared_screen_exists():
    """Un nombre mal escrito marcaría una pantalla que no existe y nada avisaría."""
    names = _url_names()

    for item in all_items():
        for name in (*item.active_url_names, *item.detail_url_names):
            assert name in names, f"{item.url_name} declara {name}, que no existe"


def test_a_screen_marks_at_most_one_destination():
    """Si dos destinos reclamaran la misma ficha, el menú tendría dos activos."""
    claimed = {}
    for item in all_items():
        for name in item.active_names:
            assert name not in claimed, f"{name}: {claimed[name]} y {item.url_name}"
            claimed[name] = item.url_name


def test_a_detail_screen_gets_breadcrumbs_from_the_registry():
    menu = build_sidebar(AllowEverything(), "permission-detail")

    with translation.override("en"):
        labels = [str(crumb.label) for crumb in menu.breadcrumbs]
    assert labels == ["Flight", "Permissions"]
    assert menu.breadcrumbs[1].url == reverse("permission-list")
    assert menu.breadcrumbs[0].url == ""  # el grupo no es una página


def test_a_list_and_a_child_screen_have_no_breadcrumbs():
    for name in ("permission-list", "permission-create", "dashboard"):
        assert not build_sidebar(AllowEverything(), name).breadcrumbs


def test_the_top_block_has_no_group_crumb():
    menu = build_sidebar(AllowEverything(), "dashboard")

    assert menu.breadcrumbs == ()


def test_a_detail_marks_its_list_with_aria_current_true_not_page():
    """La ficha lleva el `page`; el menú sólo dice que el destino la contiene."""
    menu = build_sidebar(AllowEverything(), "permission-detail")
    marked = [
        item for group in menu.groups for item in group.items if item.aria_current
    ]

    assert [item.key for item in marked] == ["permission-list"]
    assert marked[0].aria_current == "true"
    assert (
        build_sidebar(AllowEverything(), "permission-list")
        .groups[0]
        .items[0]
        .aria_current
        == "page"
    )


@pytest.mark.django_db
def test_on_a_ficha_its_destination_is_active_and_there_are_crumbs(db):
    centre = CostCenter.objects.create(code="CC1", name="Faena Uno")
    client = login_as("view_costcenter")

    body = client.get(reverse("costcenter-detail", args=[centre.pk])).content.decode()
    menu = _menu(body)

    assert menu.count("aria-current") == 1  # exactamente uno, y es el destino
    marked = re.search(r'<a href="([^"]+)" class="nav-item[^"]*active"', menu)
    assert marked and marked.group(1) == reverse("costcenter-list")
    # el grupo que lo contiene va abierto por el HTML (el JS lo respeta y lo fija)
    assert 'data-nav-group="sites"' in menu
    # las migas viven en `<main>`, no en el menú, y terminan en la página actual
    main = body[body.index("<main") :]
    crumbs = main[main.index('<nav class="ac-breadcrumb') : main.index("</nav>")]
    assert 'aria-label="Ruta"' in crumbs
    assert crumbs.count('aria-current="page"') == 1
    assert crumbs.index('aria-current="page"') > crumbs.index(
        reverse("costcenter-list")
    )
    assert "Faena Uno" in crumbs.split('aria-current="page"')[-1]


@pytest.mark.django_db
def test_a_list_has_no_breadcrumb_landmark(db):
    client = login_as("view_costcenter")

    body = client.get(reverse("costcenter-list")).content.decode()

    assert "ac-breadcrumb" not in body
    assert 'aria-label="Ruta"' not in body


class TestTheGroupsAreIndependent:
    def test_opening_a_group_no_longer_closes_the_others(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert "other !== toggle" not in source
        assert "setGroup(other" not in source

    def test_the_list_of_open_groups_is_remembered_under_a_new_key(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert "'nav-groups-open'" in source
        # Las claves anteriores no se leen: eran otro formato (un nombre, o los plegados).
        assert "getItem('nav-group-open')" not in source
        assert "getItem('nav-groups-collapsed')" not in source

    def test_the_group_of_the_current_page_is_always_open_and_locked(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert ".nav-group-items .nav-item.active" in source
        assert "openNames.indexOf(activeName) === -1" in source
        assert "aria-disabled" in source
        assert "if (locked) return;" in source

    def test_every_storage_access_is_guarded_reading_included(self):
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("function readOpenGroups")
        end = source.index("function mayAnimate")

        block = source[start:end]
        assert block.count("localStorage.") == block.count("try {") == 2
        assert block.count("catch (error)") == 2

    def test_the_html_still_degrades_to_everything_open(self):
        markup = build_sidebar(AllowEverything(), "")
        from apps.core.testing import full_sidebar_html

        toggles = re.findall(r"<button[^>]*nav-group-toggle[^>]*>", full_sidebar_html())

        assert len(toggles) == len(markup.groups)
        assert all('aria-expanded="true"' in toggle for toggle in toggles)
