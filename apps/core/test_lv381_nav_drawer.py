"""`LV-381` F5 (V10, D5): el cajón móvil es un cajón de verdad, y la tableta arranca en modo icono.

Antes (V10) el menú de menos de 769 px se deslizaba sobre la página **sin** fondo
oscuro, sin cerrar al tocar fuera, sin mover el foco y con el contenido de atrás
todavía tabulable y legible por un lector de pantalla; cerrado, además, sus
enlaces seguían en el orden de tabulación fuera de la pantalla. Ahora:

- fondo oscuro (`#sidebar-backdrop`) que cierra al tocarlo;
- el foco entra al primer enlace al abrir y vuelve al botón que lo abrió al cerrar;
- barra superior, aviso sin conexión, enlace de salto y `<main>` quedan `inert`;
- Esc cierra, y el botón de la cabecera de la barra pasa a «Cerrar navegación»;
- cerrado, el cajón es `visibility: hidden` (sin tabulación ni lectura);
- **D5**: de 769 a 1199 px, sin preferencia guardada, la barra arranca en modo
  icono, y ese arranque **no se guarda** como si fuera una elección.

El comportamiento es de JavaScript/CSS y el repo no tiene infraestructura para
ejecutarlo; acá se afirma lo que Python puede ver y se verificó en el navegador
demo (375, 1000 y 1366 px). El navegador integrado no compone: la animación no se
pudo ver, sí los estados finales con las transiciones apagadas.
"""

import re
from pathlib import Path

APP_JS = Path("static/js/app.js").read_text(encoding="utf-8")
APP_CSS = Path("static/css/app.css").read_text(encoding="utf-8")
BASE = Path("templates/base.html").read_text(encoding="utf-8")
SIDEBAR = Path("templates/core/_sidebar.html").read_text(encoding="utf-8")


def _mobile_block():
    start = APP_CSS.index("@media (max-width: 768px) {\n  .sidebar {")
    return APP_CSS[start : APP_CSS.index("\n}\n", start)]


class TestTheDrawerIsModal:
    def test_there_is_a_backdrop_hidden_by_default(self):
        assert re.search(
            r'<div class="sidebar-backdrop" id="sidebar-backdrop" hidden>', BASE
        )

    def test_the_backdrop_only_exists_on_a_phone_and_sits_under_the_drawer(self):
        block = _mobile_block()

        assert ".sidebar-backdrop:not([hidden])" in block
        assert "z-index: 1039" in block  # el cajón es 1040
        assert "rgb(6 12 24 / 55%)" in block

    def test_touching_outside_closes_it(self):
        assert "drawerBackdrop.addEventListener('click'" in APP_JS
        assert (
            "setSidebar(false)"
            in APP_JS.split("drawerBackdrop.addEventListener", 1)[1][:120]
        )

    def test_the_rest_of_the_page_is_inert_while_it_is_open(self):
        assert "'.skip-link, #offline-banner, body > .navbar, #main-content'" in APP_JS
        assert "node.inert = on" in APP_JS
        assert "setPageInert(modal)" in APP_JS

    def test_focus_goes_in_and_comes_back_to_the_button(self):
        source = APP_JS.split("function setSidebar(open)", 1)[1].split(
            "function syncToolbarLabel"
        )[0]

        assert "sidebar.querySelector('nav a[href]')" in source
        assert "first.focus()" in source
        assert "toggle.focus()" in source
        # sólo al **cerrar un cajón que estaba abierto**, no en cada llamada
        assert "narrow && !open && wasOpen" in source

    def test_escape_closes_it(self):
        assert "if (event.key === 'Escape') { setSidebar(false); }" in APP_JS

    def test_the_header_button_closes_the_drawer_and_says_so(self):
        assert "data-label-close=\"{% translate 'Close navigation' %}\"" in SIDEBAR
        assert "button.dataset.labelClose" in APP_JS
        click = APP_JS.split(
            "getElementById('sidebar-collapse').addEventListener('click'", 1
        )[1][:260]
        assert "isNarrow()" in click and "setSidebar(false)" in click

    def test_closed_it_is_out_of_the_tab_order_and_it_does_not_scroll_the_page(self):
        block = _mobile_block()

        assert "visibility: hidden;" in block
        assert (
            ".sidebar.is-open { transform: translateX(0); visibility: visible;" in block
        )
        assert "overscroll-behavior: contain" in block
        assert "body.drawer-open { overflow: hidden; }" in block

    def test_growing_the_window_does_not_leave_the_page_inert(self):
        resize = APP_JS.split(
            "window.addEventListener('resize', function () {\n    var sidebar", 1
        )[1][:260]

        assert "!isNarrow()" in resize and "setSidebar(false)" in resize


class TestTheTabletStartsAsARail:
    def test_without_a_saved_preference_a_tablet_starts_collapsed_without_saving(self):
        assert "savedRail === null && window.innerWidth < 1200" in APP_JS
        assert "setSidebarCollapsed(true, false)" in APP_JS

    def test_a_saved_preference_wins(self):
        assert "if (savedRail === 'true') setSidebarCollapsed(true);" in APP_JS

    def test_the_default_is_not_remembered_but_a_choice_is(self):
        source = APP_JS.split("function setSidebarCollapsed", 1)[1][:500]

        assert "if (persist !== false) remember('sidebar-collapsed'" in source
