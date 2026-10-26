"""LV-367 (fase 4): «Cumplimiento» simple. Resumen de un vistazo, secciones plegables y tabla de permisos simple.

Se fija: «Qué atender primero» sólo en la página completa (el panel ya tiene «Requiere atención»), hasta tres,
en el orden de `PRIORITY_ORDER` (una propuesta que la persona confirma), sólo cifras que existen y las mismas
del resto de la página; `open` de cada `<details>` decidido en Python y sólo con pendientes (mapa de calor,
historial y guía, nunca); ceros dichos con «·» y su «0» oculto; categorías sin nada agrupadas en «Sin
pendientes»; los anillos ya no se dibujan (la etiqueta `ring` sigue); y la tabla de permisos muestra sólo las
faenas con problema por omisión, con un chip de estado y el detalle en `<details>`, sin perder `?sort=`.
"""

# ruff: noqa: F811  (los fixtures se importan de otros módulos y se usan como argumentos)
import re

import pytest
from django.urls import reverse
from django.utils import translation

from apps.core.test_lv315_identity_foundation import ROOT
from apps.core.testing import login_as as _login_as
from apps.dashboard import compliance_section as section
from apps.dashboard.compliance_section import (
    PRIORITY_LIMIT,
    PRIORITY_ORDER,
    attention_first,
    open_flags,
)
from apps.dashboard.templatetags.compliance_charts import ring
from apps.dashboard.test_lv359_compliance_charts import (  # noqa: F401
    ALL_SOURCES,
    _alert,
    mix,
    rule,
)
from apps.dashboard.test_lv359_compliance_permits import (  # noqa: F401
    TODAY,
    VIEW,
    _page,
    _permit,
    _head,
    _permits_block,
    _site,
    sites,
)

from apps.operations.models import FlightPermission  # noqa: E402

URL = "dashboard-compliance"
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def english():
    """Las cadenas se comparan en inglés (la fuente); el español se activa aparte."""
    with translation.override("en"):
        yield


def login_as(*codenames, **kwargs):
    client = _login_as(*codenames, **kwargs)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


def _full(client, **params):
    return client.get(reverse(URL), params).content.decode()


def _fragment(client, **params):
    return client.get(reverse(URL), params, **HX).content.decode()


def _fold(html, block):
    """La etiqueta de apertura del `<details>` de un bloque."""
    return re.search(rf'<details[^>]*data-cx-block="{block}"[^>]*>', html).group(0)


def _rings(*pairs):
    return [{"counts": {"overdue": over}, "key": key} for key, over in pairs]


class TestWhatToAttendFirst:
    def test_only_the_full_page_has_it_the_panel_fragment_does_not_repeat_it(
        self, mix, rule
    ):
        _alert(rule, 40)
        client = login_as(*ALL_SOURCES)
        assert "What to attend first" in _full(client)
        assert "What to attend first" not in _fragment(client)
        assert 'data-cx-block="first"' not in _fragment(client)

    def test_the_order_is_the_constant_and_zero_items_are_left_out(self):
        rings = _rings(("papers", 2), ("aircraft", 1))
        alerts, permits = {"old": 4}, {"without_permit": 3}
        items = attention_first(rings, alerts, permits)
        assert [i["key"] for i in items] == list(PRIORITY_ORDER)
        assert [i["count"] for i in items] == [3, 3, 4]
        only_alerts = attention_first([], {"old": 1}, {"without_permit": 0})
        assert [i["key"] for i in only_alerts] == ["old_alerts"]
        assert attention_first([], None, None) == []

    def test_changing_the_constant_changes_the_order_and_nothing_else(
        self, monkeypatch
    ):
        rings, alerts, permits = (
            _rings(("papers", 2)),
            {"old": 4},
            {"without_permit": 3},
        )
        monkeypatch.setattr(
            section, "PRIORITY_ORDER", ("old_alerts", "no_permit", "overdue")
        )
        assert [i["key"] for i in attention_first(rings, alerts, permits)] == [
            "old_alerts",
            "no_permit",
            "overdue",
        ]

    def test_it_never_lists_more_than_three(self, monkeypatch):
        monkeypatch.setattr(section, "PRIORITY_LIMIT", 2)
        items = attention_first(
            _rings(("papers", 1)), {"old": 1}, {"without_permit": 1}
        )
        assert len(items) == 2
        assert PRIORITY_LIMIT == 3

    def test_the_texts_are_counted_and_link_to_where_it_is_worked(self):
        with translation.override("en"):
            items = attention_first(
                _rings(("papers", 1)), {"old": 2}, {"without_permit": 1}
            )
            by_key = {i["key"]: i for i in items}
            assert by_key["no_permit"]["text"] == "1 site without a permit in force"
            assert by_key["overdue"]["text"] == "1 item overdue"
            assert by_key["old_alerts"]["text"] == "2 alerts open for over 30 days"
        assert by_key["no_permit"]["url"] == "#cx-permits"
        assert by_key["overdue"]["url"] == "#cx-expiries"
        assert by_key["old_alerts"]["url"] == reverse("alert-list")

    @pytest.mark.django_db
    def test_the_figures_are_the_ones_of_the_rest_of_the_page(self, mix, rule, sites):
        _alert(rule, 40)
        _alert(rule, 50)
        client = login_as(*ALL_SOURCES)
        context = client.get(reverse(URL)).context
        by_key = {i["key"]: i for i in context["cx_priorities"]}
        assert by_key["no_permit"]["count"] == context["cx_permits"]["without_permit"]
        assert by_key["old_alerts"]["count"] == context["cx_alerts"]["old"] == 2
        assert by_key["overdue"]["count"] == sum(
            r["counts"]["overdue"] for r in context["cx_rings"]
        )
        panel = client.get(reverse("dashboard")).context
        chip = next(i for i in panel["attention"] if i["key"] == "sites_without_permit")
        assert chip["count"] == by_key["no_permit"]["count"]

    @pytest.mark.django_db
    def test_only_visible_sources_make_a_priority(self, mix, rule):
        _alert(rule, 40)
        context = login_as("view_alert").get(reverse(URL)).context
        assert [i["key"] for i in context["cx_priorities"]] == ["old_alerts"]

    @pytest.mark.django_db
    def test_with_nothing_urgent_it_says_so(self, db):
        html = _full(login_as("view_alert"))
        assert "Nothing needs attention first." in html
        assert 'data-cx-priority="' not in html

    @pytest.mark.django_db
    def test_it_is_spanish_too(self, mix, rule):
        _alert(rule, 40)
        client = login_as(*ALL_SOURCES)
        html = client.get(
            reverse(URL), headers={"Accept-Language": "es"}
        ).content.decode()
        assert "Qué atender primero" in html and "What to attend first" not in html


class TestOpenIsDecidedByWhatThereIs:
    def test_the_rules_in_python(self):
        none = {
            "cx_rings": [],
            "cx_alerts": {"total": 0},
            "cx_permits": {"problems": 0},
        }
        assert open_flags(none) == {
            "expiries": False,
            "alerts": False,
            "maintenance": False,
            "permits": False,
        }
        some = {
            "cx_rings": [{"attend": 1}],
            "cx_alerts": {"total": 2},
            "cx_permits": {"problems": 1},
            "cx_maintenance_to_define": 3,
        }
        assert all(open_flags(some).values())

    @pytest.mark.django_db
    def test_a_quiet_operation_opens_nothing(self, db):
        client = login_as(*ALL_SOURCES)
        html = _full(client)
        for block in ("expiries", "heat", "alerts", "maintenance", "history"):
            assert " open" not in _fold(html, block), block

    @pytest.mark.django_db
    def test_pending_things_open_their_own_section_only(self, mix, rule):
        _alert(rule, 3)
        html = _full(login_as(*ALL_SOURCES))
        assert " open" in _fold(html, "expiries")
        assert " open" in _fold(html, "alerts")
        assert " open" in _fold(html, "maintenance")  # hay una mantención por definir
        for never in ("heat", "history"):
            assert " open" not in _fold(html, never), never
        assert '<details class="id-cx-guide" id="cx-guide" open' not in html

    @pytest.mark.django_db
    def test_the_permits_open_only_with_a_problem(self, sites):
        client = login_as(VIEW)
        assert " open" in _fold(_full(client), "permits")
        healthy = _site("CC9")
        _permit(healthy, 200)
        for site in sites:
            site.is_active = False
            site.save()
        assert " open" not in _fold(_full(client), "permits")

    @pytest.mark.django_db
    def test_the_heat_map_history_and_guide_are_never_open(self, mix, rule):
        _alert(rule, 3)
        html = _full(login_as(*ALL_SOURCES))
        assert " open" not in _fold(html, "heat")
        assert " open" not in _fold(html, "history")
        assert re.search(r'<details class="id-cx-guide"[^>]*>', html)
        assert " open" not in re.search(
            r'<details class="id-cx-guide"[^>]*>', html
        ).group(0)

    @pytest.mark.django_db
    def test_no_summary_declares_aria_expanded(self, mix, rule):
        html = _fragment(login_as(*ALL_SOURCES))
        assert "aria-expanded" not in html  # `<details>` ya expone el estado


class TestTheSummary:
    @pytest.mark.django_db
    def test_each_visible_category_has_exactly_one_marker_attention_or_clear(self, mix):
        html = _full(login_as(*ALL_SOURCES))
        for key in ("papers", "people", "aircraft", "permits", "maintenance"):
            assert html.count(f'data-cx-ring="{key}"') == 1, key

    @pytest.mark.django_db
    def test_a_category_with_nothing_goes_to_no_pending_and_is_not_an_indicator(
        self, db
    ):
        html = _full(login_as("view_aircraft"))
        indicators = html.split('class="id-cx-clear"')[0]
        assert 'data-cx-ring="aircraft"' not in indicators
        clear = html.split('class="id-cx-clear"')[1]
        assert "No pending" in clear and 'data-cx-ring="aircraft"' in clear

    @pytest.mark.django_db
    def test_an_indicator_has_icon_figure_and_a_cross_for_overdue(self, mix):
        html = _full(login_as(*ALL_SOURCES))
        indicators = html.split('class="id-cx-ind"')[1].split("</ul>")[0]
        assert "icons.svg#icon-aircraft-list" in indicators
        assert re.search(
            r'id-chip--critical"><span aria-hidden="true">✕</span> <b>\d+</b>',
            indicators,
        )
        assert re.search(
            r'<b class="id-cx-fig">\d+</b> <span>to attend within 30 days</span>',
            indicators,
        )

    @pytest.mark.django_db
    def test_a_zero_is_a_dot_with_a_hidden_zero_and_empty_rows_are_summarised(
        self, mix
    ):
        html = _full(login_as(*ALL_SOURCES))
        assert (
            '<span aria-hidden="true">·</span><span class="visually-hidden">0 ' in html
        )
        # el mapa de calor trae ceros con la misma forma
        heat = html.split('data-cx-block="heat"')[1]
        assert '<b class="id-cx-zero"><span aria-hidden="true">·</span>' in heat

    @pytest.mark.django_db
    @pytest.mark.django_db
    def test_the_level_table_scrolls_inside_its_own_box_on_a_phone(self, mix):
        """A 375 px la tabla de niveles desbordaba la página 30 px (medido en el navegador)."""
        html = _full(login_as(*ALL_SOURCES))
        assert (
            '<div class="id-cx-lv-wrap">\n      <table class="id-cx-lv">'
            in html.replace("\r\n", "\n")
        )
        compliance = (ROOT / "static" / "css" / "compliance.css").read_text(
            encoding="utf-8"
        )
        assert re.search(r"(?m)^\.id-cx-lv-wrap \{ overflow-x: auto; \}", compliance)

    @pytest.mark.django_db
    def test_a_category_without_expiries_is_one_line_not_a_row_of_zeros(self, db):
        html = _full(login_as(*ALL_SOURCES))
        table_less = html.split('data-cx-block="expiries"')[1].split("</details>")[0]
        assert "<table" not in table_less
        assert "No expiries in the next 90 days:" in table_less

    @pytest.mark.django_db
    def test_the_rings_are_gone_but_the_tag_still_renders(self, mix):
        html = _full(login_as(*ALL_SOURCES))
        assert "id-cx-ring-svg" not in html and "id-cx-rings" not in html
        svg = ring([("id-cx-seg--overdue", 1)], "u", "t", "d", center=1)
        assert "<svg" in str(svg) and 'role="img"' in str(svg)

    @pytest.mark.django_db
    def test_the_summary_counts_use_the_same_data_as_before(self, mix):
        context = login_as(*ALL_SOURCES).get(reverse(URL)).context
        assert [r["key"] for r in context["cx_attention"] + context["cx_clear"]] != []
        assert {r["key"] for r in context["cx_attention"]} | {
            r["key"] for r in context["cx_clear"]
        } == {r["key"] for r in context["cx_rings"]}
        assert all(r["attend"] for r in context["cx_attention"])
        assert not any(r["attend"] for r in context["cx_clear"])


class TestTheSimplePermitTable:
    @pytest.mark.django_db
    def test_by_default_every_site_shows_healthy_ones_included(self, sites):
        context = _page(login_as(VIEW)).context["cx_permits"]
        # CC3 (200 d) está vigente y sana: antes de LV-374 quedaba tras «Ver todas»; ahora sale.
        assert sorted(r["cost_center"].code for r in context["rows"]) == [
            "CC1",
            "CC2",
            "CC3",
            "CC4",
            "CC5",
        ]
        assert (context["total"], context["problems"]) == (5, 4)
        assert "hidden" not in context

    @pytest.mark.django_db
    def test_there_is_no_see_all_link_and_the_count_is_the_number_of_rows(self, sites):
        html = _page(login_as(VIEW)).content.decode()
        assert "See all" not in html and "Show only sites with a problem" not in html
        block = _permits_block(html)
        count = re.search(r'<b class="id-cx-count">(\d+)</b>', block).group(1)
        assert count == "5"
        assert block.count('class="id-cx-site"') == 5

    @pytest.mark.django_db
    def test_a_saved_all_1_link_still_works_and_changes_nothing(self, sites):
        client = login_as(VIEW)
        plain = _page(client).context["cx_permits"]["rows"]
        saved = _page(client, all="1")
        assert saved.status_code == 200
        assert [r["cost_center"].code for r in saved.context["cx_permits"]["rows"]] == [
            r["cost_center"].code for r in plain
        ]
        assert "all=1" not in _head(saved.content.decode())

    @pytest.mark.django_db
    def test_the_sort_links_keep_the_site(self, sites):
        html = _page(login_as(VIEW), cost_center=sites[0].pk).content.decode()
        assert f"cost_center={sites[0].pk}&amp;sort=code" in _head(
            html
        ) or f"cost_center={sites[0].pk}&sort=code" in _head(html)

    @pytest.mark.django_db
    def test_twelve_sites_all_show_in_priority_order_without_extra_queries(self, db):
        # 12 faenas: 2 sin nada, 1 esperando, 1 a 20 d, 1 a 45 d, 7 vigentes lejos.
        none_a, none_b = _site("CC01"), _site("CC02")
        awaiting = _site("CC03")
        _permit(awaiting, 30, status=FlightPermission.STATUS_REQUESTED)
        _permit(_site("CC04"), 20)
        _permit(_site("CC05"), 45)
        for n in range(6, 13):
            _permit(_site(f"CC{n:02d}"), 150 + n)
        client = login_as(VIEW)
        response = _page(client)
        context = response.context["cx_permits"]
        codes = [r["cost_center"].code for r in context["rows"]]
        assert len(codes) == context["total"] == 12
        # sin permiso vigente primero (por código), luego los vigentes (por código)
        assert codes == [f"CC{n:02d}" for n in (1, 2, 3, 4, 5, *range(6, 13))]
        html = response.content.decode()
        block = _permits_block(html)
        for code in codes:
            assert f'<span class="cc-chip me-2">{code}</span>' in block
        assert re.search(r'<b class="id-cx-count">12</b>', html)
        assert "See all" not in html
        del none_a, none_b

    @pytest.mark.django_db
    def test_showing_every_site_adds_no_queries_and_details_stay_one_query(self, db):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = login_as(VIEW)

        def count():
            client.get(reverse(URL))  # calienta cachés (ContentType, permisos)
            with CaptureQueriesContext(connection) as queries:
                response = client.get(reverse(URL))
            return len(queries), len(response.context["cx_permits"]["rows"])

        for i in range(3):
            _permit(_site(f"Z{i:02d}"), 100 + i)
        few = count()
        for i in range(3, 15):
            _permit(_site(f"Z{i:02d}"), 100 + i)
        many = count()
        assert (few[1], many[1]) == (3, 15)
        assert many[0] == few[0]

    @pytest.mark.django_db
    def test_it_has_four_columns_and_one_status_chip_per_row(self, sites):
        html = _page(login_as(VIEW)).content.decode()
        table = _permits_block(html)
        assert table.split("<thead>")[1].split("</thead>")[0].count("<th") == 4
        for row in re.findall(
            r"<tr[ >].*?</tr>", table.split("<tbody>")[1], flags=re.S
        ):
            status_cell = row.split("<td")[2]
            assert status_cell.count("id-cx-state ") == 1

    @pytest.mark.django_db
    def test_the_next_expiry_has_days_and_date_and_the_rest_lives_in_the_details(
        self, sites
    ):
        html = _page(login_as(VIEW)).content.decode()
        table = _permits_block(html)
        row = next(r for r in table.split("<tr") if "CC1" in r)
        assert re.search(r"in \d+ days", row) and re.search(r"\d\d-\d\d-\d{4}", row)
        details = row.split("<details")[1].split("</details>")[0]
        assert "In force" in details and "expiring soon" in details

    @pytest.mark.django_db
    def test_with_only_healthy_sites_they_still_show_and_the_section_stays_closed(
        self, db
    ):
        _permit(_site("CC9"), 200)
        html = _page(login_as(VIEW)).content.decode()
        assert "CC9" in _permits_block(html)
        assert "No site has a problem" not in html and "See all" not in html
        assert "open" not in _fold(html, "permits")

    def test_the_problem_rule_uses_the_kpi_scale(self):
        from apps.dashboard.compliance_permits import has_problem

        def row(state, days):
            return {
                "in_force": 1 if state == "in_force" else 0,
                "awaiting": state == "awaiting",
                "not_started": state == "not_started",
                "days_remaining": days,
            }

        assert has_problem(row("none", None)) and has_problem(row("awaiting", None))
        assert has_problem(row("in_force", 60)) and not has_problem(row("in_force", 61))
        assert has_problem(row("in_force", 30))


class TestTheNewPairsReach:
    """Contraste CALCULADO de lo que suma la fase 4 (claro y oscuro), con las funciones de la fase 1."""

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(
        ("fg", "bg", "minimum"),
        [
            ("--id-ok-text", "--ac-surface", 3),  # icono de «sin pendientes»
            ("--sev-warning-text", "--id-tile", 3),  # filete de «qué atender primero»
            ("--ac-text-muted", "--ac-surface", 4.5),  # el «·» de un cero
            ("--sev-nominal-text", "--sev-nominal-bg", 4.5),  # la cifra de cada sección
            ("--ac-text", "--id-tile", 4.5),  # el texto de los indicadores
            ("--id-edge", "--ac-surface", 3),  # borde de las secciones plegables
        ],
    )
    def test_pair(self, theme, fg, bg, minimum):
        from apps.core.test_lv367_visual_base import (
            _contrast,
            _resolve,
            _theme_tokens,
        )

        tokens = _theme_tokens(theme)
        ratio = _contrast(_resolve(tokens[fg], tokens), _resolve(tokens[bg], tokens))
        assert ratio >= minimum, (theme, fg, bg, ratio)
