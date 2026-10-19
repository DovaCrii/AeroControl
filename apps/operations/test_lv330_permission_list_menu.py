"""LV-330 (ola G, Visual v2): la lista de permisos.

Tres defectos medidos en producción: «Renovar permiso» se cortaba en 110 px fijos de
Acciones; los filtros saltaban a dos filas porque la rejilla `col-md-*` sólo la acomoda
la capa en `form.row`; y los estados mezclaban `badge bg-*` con `cc-chip`. Se fija
que «Ver» queda siempre a la vista, que lo demás vive en el menú «⋯» con los mismos
permisos de antes, que la barra de filtros es una franja y que la capa no abre un
segundo bloque `no-preference`.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core.testing import login_as, without_template_comments
from apps.operations.models import FlightPermission

from . import test_lv320_renew_permit as lv320

ADD = lv320.ADD
cost_center, plan, previous, author = (
    lv320.cost_center,
    lv320.plan,
    lv320.previous,
    lv320.author,
)

ROOT = Path(settings.BASE_DIR)
IDENTITY = (ROOT / "static" / "css" / "identity.css").read_text(encoding="utf-8")
MENU = re.compile(r'<details class="id-rowmenu">(.*?)</details>', re.S)


def _page(client, **params):
    return client.get(reverse("permission-list"), params).content.decode()


def _row(html):
    return html.split('<tr data-pk="', 1)[1].split("</tr>", 1)[0]


def _menu(html):
    found = MENU.search(_row(html))
    return found.group(1) if found else ""


def _outside_menu(html):
    return MENU.sub("", _row(html))


def _section_a2():
    start = IDENTITY.index("/* A2: Visual v2")
    return IDENTITY[start : IDENTITY.index("/* == B:")]


@pytest.mark.django_db
class TestTheRowActions:
    def test_view_stays_outside_the_menu(self, previous, plan):
        html = _page(login_as(*ADD))

        assert f'href="{previous.pk}/"' in _outside_menu(html)
        assert 'btn btn-sm btn-outline-secondary">View' in _outside_menu(html) or (
            "Ver" in _outside_menu(html)
        )
        assert f'href="{previous.pk}/"' not in _menu(html)

    def test_the_secondary_actions_live_inside_the_menu(self, previous, plan):
        client = login_as(*ADD, "delete_flightpermission")
        html = _page(client)

        menu = _menu(html)
        assert f"?renueva={previous.pk}" in menu
        assert reverse("permission-archive", args=[previous.pk]) in menu
        assert "csrfmiddlewaretoken" in menu
        # Fuera del menú, ni renovar ni archivar.
        assert "?renueva=" not in _outside_menu(html)
        assert "permission-archive" not in _outside_menu(html)

    def test_the_menu_button_has_an_accessible_name(self, previous, plan):
        html = _page(login_as(*ADD))

        assert (
            'aria-label="More actions"' in html or 'aria-label="Más acciones"' in html
        )

    def test_without_add_geoplan_renew_is_not_offered(self, previous, plan):
        client = login_as(
            "add_flightpermission", "view_flightpermission", "delete_flightpermission"
        )
        menu = _menu(_page(client))

        assert "?renueva=" not in menu
        # El menú sigue existiendo: archivar es otro permiso.
        assert reverse("permission-archive", args=[previous.pk]) in menu

    def test_without_any_secondary_permission_there_is_no_menu(self, previous, plan):
        html = _page(login_as("view_flightpermission"))

        assert "id-rowmenu" not in _row(html)
        assert f'href="{previous.pk}/"' in _row(html)

    def test_an_archived_row_offers_restore_and_not_archive(self, previous, plan):
        FlightPermission.objects.filter(pk=previous.pk).update(is_active=False)
        client = login_as("view_flightpermission", "change_flightpermission")
        menu = _menu(_page(client, is_active="archived"))

        assert reverse("permission-restore", args=[previous.pk]) in menu
        assert "permission-archive" not in menu

    def test_restore_needs_the_change_permission(self, previous, plan):
        FlightPermission.objects.filter(pk=previous.pk).update(is_active=False)
        client = login_as("view_flightpermission")
        html = _page(client, is_active="archived")

        assert "permission-restore" not in html

    def test_the_archived_marker_moves_next_to_the_status(self, previous, plan):
        FlightPermission.objects.filter(pk=previous.pk).update(is_active=False)
        html = _page(login_as("view_flightpermission"), is_active="archived")

        assert "id-chip--neutral" in _row(html)
        assert "badge bg-secondary" not in _row(html)


@pytest.mark.django_db
class TestTheStatusChips:
    def test_the_state_is_a_chip_not_a_bootstrap_badge(self, previous, plan):
        row = _row(_page(login_as("view_flightpermission")))

        assert "id-chip" in row
        assert "badge bg-" not in row
        assert "badge sev-" not in row


@pytest.mark.django_db
class TestTheFilterStrip:
    def test_the_filters_are_one_labelled_strip(self, previous, plan):
        html = _page(login_as("view_flightpermission"))
        form = html.split('<form method="get" class="id-filterbar">', 1)[1].split(
            "</form>", 1
        )[0]

        assert form.count('class="id-filter-label"') == 5
        assert form.count('class="id-filter ') + form.count('class="id-filter"') >= 5
        assert "col-md-" not in form
        assert 'type="date"' in form
        # Cada fecha con su rótulo: un placeholder no se ve en un `type=date`.
        assert 'for="id-filter-from"' in form and 'for="id-filter-to"' in form

    def test_the_template_no_longer_writes_the_bootstrap_grid(self):
        markup = without_template_comments(
            (ROOT / "templates" / "operations" / "permission_list.html").read_text(
                encoding="utf-8"
            )
        )

        assert "col-md-" not in markup
        assert "col-auto" not in markup


class TestTheStylesheet:
    def test_the_generic_rule_fixes_every_list_that_writes_col_md(self):
        css = _section_a2()

        assert re.search(
            r'\.id-filterbar > \[class\*="col"\]\s*\{[^}]*flex: 0 1 auto;[^}]*width: auto',
            css,
        )

    def test_the_36px_controls_live_only_inside_the_filter_bar(self):
        css = _section_a2()

        assert re.search(
            r"\.id-filterbar \.form-control,[^{]*\{[^}]*height: 2\.25rem", css
        )
        assert not re.search(r"--ac-control-height\s*:", css)
        assert re.search(r'input\[type="date"\]\s*\{\s*max-width: 9\.5rem', css)

    def test_the_row_hover_has_its_own_background_and_a_2px_edge(self):
        css = _section_a2()

        assert "--bs-table-hover-bg: var(--ac-surface-raised)" in css
        assert "inset 2px 0 0 var(--ac-primary)" in css

    def test_density_is_the_existing_global_one_and_is_respected(self):
        css = _section_a2()
        theme_init = (ROOT / "static" / "js" / "theme-init.js").read_text(
            encoding="utf-8"
        )

        assert '[data-density="compact"] .id-rowmenu' in css
        assert "data-density" in theme_init and "density" in theme_init

    def test_the_menu_motion_lives_in_the_only_no_preference_block(self):
        blocks = re.findall(r"prefers-reduced-motion: no-preference\)", IDENTITY)
        a2 = _section_a2()

        assert len(blocks) == 1
        assert "animation" not in a2 and "@keyframes" not in a2
        inside = IDENTITY[IDENTITY.index("prefers-reduced-motion: no-preference") :]
        assert ".id-rowmenu[open] > .id-rowmenu-list { animation: id-menu-in" in inside
        assert "var(--id-t-fast)" in inside

    def test_the_menu_can_leave_the_clipped_container(self):
        css = _section_a2()
        script = (ROOT / "static" / "js" / "row-menu.js").read_text(encoding="utf-8")

        assert ".id-rowmenu-list.is-floating { position: fixed" in css
        for key in ("Escape", "ArrowDown", "ArrowUp", "is-floating", "closest"):
            assert key in script, key


class TestTheTableKeepsItsColumns:
    def test_the_actions_column_still_has_seven_cols_for_a_seven_cell_empty_row(self):
        base = ROOT / "templates" / "operations"
        cols = (
            (base / "permission_list.html").read_text(encoding="utf-8").count("<col ")
        )
        rows = (base / "_permission_rows.html").read_text(encoding="utf-8")

        assert cols == 7
        assert 'colspan="7"' in rows
        assert 'colspan="99"' not in rows
