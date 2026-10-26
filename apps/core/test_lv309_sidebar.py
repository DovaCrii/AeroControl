"""LV-309: barra lateral en acordeon, con tres niveles visuales y burbuja en modo icono.

Rediseno de la barra (PR 1). Los ganchos viven en la plantilla, el CSS y `app.js`; el repo no
tiene infraestructura de tests de JavaScript, asi que se afirma lo que Python puede ver (que el
codigo dice lo que debe decir) y el comportamiento se verifico en el navegador demo.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.testing import full_sidebar_html, login_as

APP_JS = Path("static/js/app.js")
IDENTITY_CSS = Path("static/css/identity.css")

NO_PREFERENCE = "@media (prefers-reduced-motion: no-preference) {"


def _no_preference_block(css):
    start = css.index(NO_PREFERENCE)
    depth = 0
    for index in range(start + len(NO_PREFERENCE) - 1, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[start : index + 1]
    raise AssertionError("bloque no-preference sin cerrar")


def _sidebar_markup():
    """El menú renderizado completo (`LV-381` F1: ya no está escrito en `base.html`)."""
    return full_sidebar_html()


class TestTheGroups:
    """Reescrito A PROPOSITO en `LV-381` F3 (D1).

    Esta clase afirmaba el **acordeon**: abrir un grupo cerraba los demas y se
    recordaba un solo grupo (`nav-group-open`). La decision D1 del diseno lo
    invierte (varios grupos abiertos a la vez, el de la pagina activa siempre
    abierto, lista guardada en `nav-groups-open`), porque quien trabaja con Vuelo y
    Flota a la vez reabria uno cada vez. El comportamiento nuevo lo cubre
    `test_lv381_nav_orientation.py::TestTheGroupsAreIndependent`; aqui quedan las
    afirmaciones que siguen valiendo y la que prohibe volver al acordeon.
    """

    def test_opening_a_group_does_not_close_the_others(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert "other !== toggle" not in source
        assert "setGroup(other" not in source

    def test_the_open_groups_are_remembered_under_a_new_key(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert "'nav-groups-open'" in source
        # Las claves antiguas ya no se leen: eran otro formato (un nombre, o los plegados).
        assert "getItem('nav-group-open')" not in source
        assert "getItem('nav-groups-collapsed')" not in source

    def test_the_group_of_the_current_page_always_stays_open(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert ".nav-group-items .nav-item.active" in source
        assert re.search(
            r"activeName = activeOwner \? activeOwner\.dataset\.navGroup", source
        )

    def test_every_storage_access_is_guarded(self):
        source = APP_JS.read_text(encoding="utf-8")
        start = source.index("function readOpenGroups")
        end = source.index("function mayAnimate")

        block = source[start:end]
        assert block.count("localStorage.") == block.count("try {") == 2

    def test_the_height_is_only_animated_without_reduced_motion(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert "(prefers-reduced-motion: no-preference)" in source
        assert "!mayAnimate()" in source

    def test_the_html_still_degrades_to_everything_open(self):
        toggles = re.findall(r"<button[^>]*nav-group-toggle[^>]*>", _sidebar_markup())

        assert len(toggles) == 5  # LV-381 F2: cinco grupos
        assert all('aria-expanded="true"' in toggle for toggle in toggles)


class TestTheLabelsAndTheTooltip:
    def test_every_menu_link_wraps_its_text_in_a_nav_label(self):
        links = re.findall(
            r'<a [^>]*class="nav-item[^>]*>.*?</a>', _sidebar_markup(), re.DOTALL
        )

        assert len(links) == _sidebar_markup().count('class="nav-item')
        assert all('<span class="nav-label">' in link for link in links)

    def test_the_current_page_is_announced(self):
        assert 'aria-current="page"' in full_sidebar_html("dashboard")

    @pytest.mark.django_db
    def test_the_rendered_menu_marks_exactly_the_current_page(self, db):
        client = login_as()

        body = client.get(reverse("dashboard")).content.decode()
        sidebar = body[body.index('<aside class="sidebar') : body.index("</aside>")]

        assert sidebar.count('aria-current="page"') == 1
        assert 'class="nav-label"' in sidebar

    def test_the_script_no_longer_writes_a_duplicate_title(self):
        source = APP_JS.read_text(encoding="utf-8")

        assert "link.title" not in source

    def test_the_collapsed_label_shows_on_hover_and_keyboard_focus(self):
        css = IDENTITY_CSS.read_text(encoding="utf-8")

        assert ".sidebar.is-collapsed a:hover .nav-label" in css
        assert ".sidebar.is-collapsed a:focus-visible .nav-label" in css
        assert "left: calc(100% + 10px)" in css

    def test_its_transition_only_exists_without_reduced_motion(self):
        css = IDENTITY_CSS.read_text(encoding="utf-8")
        inside = _no_preference_block(css)
        outside = css.replace(inside, "")

        assert "transition: opacity 150ms" in inside
        assert "height 200ms" in inside
        assert not re.search(r"\.nav-label\s*\{[^}]*transition", outside)
        assert not re.search(r"\.is-animating\s*\{[^}]*transition", outside)

    def test_the_hover_no_longer_slides_the_link(self):
        css = IDENTITY_CSS.read_text(encoding="utf-8")

        assert "translateX" not in css

    def test_the_group_title_lost_its_colour_stripe(self):
        css = IDENTITY_CSS.read_text(encoding="utf-8")

        assert ".sidebar-label::before" not in css

    def test_the_administration_zone_is_separate_and_labelled(self):
        markup = _sidebar_markup()

        assert 'class="nav-admin-zone"' in markup
        assert 'msgid "Administration"' in Path(
            "locale/es/LC_MESSAGES/django.po"
        ).read_text(encoding="utf-8")
