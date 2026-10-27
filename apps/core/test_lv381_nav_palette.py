"""`LV-381` F4 (V6, V7, D3): la paleta de comandos dice dónde está cada cosa.

Lo que arregla:

- **V6**: el rótulo salía de `textContent` del enlace y arrastraba el contador de
  alertas («Alertas 3»); no decía el grupo («Reporte», sin saber de qué); y los
  atajos de «Su jornada» duplicaban destinos del menú. Ahora el rótulo sale de
  `.nav-label`, lleva el grupo (`Informes › Reporte de vigencias`) y un destino
  nunca aparece dos veces.
- **V7**: `Ctrl/⌘+K` no se anunciaba y el cuadro «Buscar en AeroControl» de la
  barra no abría nada. Ahora lleva la pista `Ctrl K` y abre la paleta al recibir
  el foco.
- **D3**: «Recientes» con `localStorage` (sin migración, sin Favoritos).

El comportamiento es de JavaScript y el repo no tiene infraestructura para
ejecutarlo, así que acá se afirma lo que Python puede ver (que el código dice lo
que debe y que el marcado que el JS lee trae lo que el JS espera); se verificó en
el navegador demo. ⚠️ La regla que no se negocia (V6): **la paleta no inventa
enlaces**; los destinos son los que el servidor ya filtró por permisos.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.testing import full_sidebar_html, login_as

PALETTE = Path("static/js/command-palette.js").read_text(encoding="utf-8")
BASE = Path("templates/base.html").read_text(encoding="utf-8")


def _code(source):
    """El archivo sin sus comentarios de línea: el JS **explica** lo que no hace."""
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )


class TestTheDestinationsAreTheMenuOnes:
    def test_the_label_comes_from_nav_label_not_the_link_text(self):
        read_menu = (
            _code(PALETTE).split("function readMenu", 1)[1].split("function matches")[0]
        )

        assert "querySelector('.nav-label')" in read_menu
        assert "link.textContent" not in read_menu

    def test_the_alert_counter_is_outside_the_label(self):
        """Si el contador entrara en `.nav-label`, la paleta diría «Alertas 3»."""
        html = full_sidebar_html()
        link = re.search(r'<a [^>]*href="/compliance/alert/"[^>]*>.*?</a>', html, re.S)

        assert link, "el enlace de alertas no se dibujó"
        label = re.search(r'<span class="nav-label">(.*?)</span>', link.group(0), re.S)
        assert label.group(1).strip() == "Alerts"

    def test_shortcuts_never_repeat_a_destination(self):
        code = _code(PALETTE)

        assert "nav-shortcut" in code  # se ordenan al final
        assert "seen[href]" in code  # y un destino ya visto no se repite

    def test_the_group_travels_with_each_destination(self):
        code = _code(PALETTE)

        assert "group: groupOf(link)" in code
        assert ".nav-group-toggle" in code and ".nav-admin-label" in code
        assert "entry.group + ' › '" in code

    def test_it_never_writes_a_link_of_its_own(self):
        """Ninguna ruta escrita en el JS: los enlaces salen del menú filtrado."""
        assert not re.search(r"""['"]/[a-z][\w/-]*/?['"]""", _code(PALETTE))

    @pytest.mark.django_db
    def test_a_destination_the_user_cannot_open_is_not_in_the_menu_the_js_reads(
        self, db
    ):
        client = login_as("view_costcenter")

        body = client.get(reverse("dashboard")).content.decode()
        sidebar = body[body.index('<aside class="sidebar') : body.index("</aside>")]

        assert reverse("costcenter-list") in sidebar
        assert reverse("alert-list") not in sidebar
        assert reverse("permission-list") not in sidebar


class TestTheTopBarBoxOpensIt:
    def test_the_box_announces_the_shortcut(self):
        assert 'aria-keyshortcuts="Control+K Meta+K"' in BASE
        assert re.search(
            r'<kbd class="global-search-hint"[^>]*>Ctrl&nbsp;K</kbd>', BASE
        )

    def test_the_hint_is_decorative_for_screen_readers(self):
        hint = re.search(r'<kbd class="global-search-hint"[^>]*>', BASE).group(0)

        assert 'aria-hidden="true"' in hint

    def test_the_box_opens_the_palette_on_click_only(self):
        code = _code(PALETTE)

        assert "box.addEventListener('click'" in code
        assert "(event.ctrlKey || event.metaKey)" in code

    def test_receiving_focus_never_opens_it(self):
        """WCAG 3.2.1 «On Focus»: el foco por Tab, o al volver a la pestaña, no
        puede cambiar el contexto. Y sin oyente de foco, cerrar y devolver el foco
        al cuadro no reabre nada."""
        code = _code(PALETTE)

        assert "addEventListener('focus'" not in code
        assert "restoringFocus" not in code

    def test_the_hint_reads_command_k_on_a_mac(self):
        assert "String.fromCharCode(160)" in PALETTE


class TestRecents:
    def test_the_labels_travel_translated_in_data_attributes(self):
        assert "data-recent-label=\"{% translate 'Recent' %}\"" in BASE
        assert "data-goto-label=\"{% translate 'Go to' %}\"" in BASE
        assert "dataset.recentLabel" in PALETTE

    def test_every_storage_access_is_guarded_reading_included(self):
        code = _code(PALETTE)
        start = code.index("function readRecents")
        end = code.index("function currentPage")

        block = code[start:end]
        assert block.count("localStorage.") == block.count("try {") == 2
        assert block.count("catch (error)") == 2

    def test_only_relative_paths_become_links(self):
        """El contenido de `localStorage` no es de fiar: un `javascript:` guardado
        ahí no debe llegar a un `href`."""
        code = _code(PALETTE)

        assert r"/^\/(?![\/\\])/.test(href)" in code
        assert "isRelativePath(item.href)" in code

    def test_a_backslash_after_the_slash_is_not_a_relative_path(self):
        """Los navegadores tratan `/\\evil.com` como `//evil.com`: otro sitio."""
        assert r"(?![\/\\])" in _code(PALETTE)

    def test_they_belong_to_the_user_who_visited(self):
        """En un equipo compartido, otra sesión no hereda títulos de fichas ajenas."""
        assert 'data-user="{{ user.pk }}"' in BASE
        assert "data.user !== userId" in PALETTE

    def test_the_list_is_capped_and_newest_first(self):
        code = _code(PALETTE)

        assert "var RECENT_MAX = 8;" in code
        assert "items.unshift(page)" in code
        assert "items.slice(0, RECENT_MAX)" in code

    def test_the_page_you_are_on_and_retired_menu_entries_are_not_offered(self):
        code = _code(PALETTE)

        assert "item.href === location.pathname" in code
        assert "!item.menu || known[item.href]" in code

    def test_only_with_an_empty_query(self):
        render = _code(PALETTE).split("function render(", 1)[1]

        assert "var recent = query ? [] : recents();" in render

    def test_a_ficha_is_recognised_by_its_breadcrumb(self):
        code = _code(PALETTE)

        assert "nav.ac-breadcrumb .breadcrumb-item.active" in code
        assert "textContent = entry.label" in code  # nunca innerHTML
        assert "innerHTML" not in code
