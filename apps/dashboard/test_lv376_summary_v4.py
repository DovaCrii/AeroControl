"""LV-376 (fase 2): el resumen v4 de «Cumplimiento»: cuatro tarjetas, tiras por categoría y la rejilla.

Se fija: las tarjetas dicen las cifras del panel (`overdue_count` y `expiring_count`, SIN mantención, con y sin
faena) y las de la tabla de permisos; un cero se dice con palabras y con ✓, nunca en rojo; las tarjetas salen
también en el fragmento del panel (G5) y «Qué atender primero» sólo en la página completa; la barra apilada es un
SVG sin `style` con `role="img"` y su cifra impresa al lado; el mapa de calor sigue en el código pero fuera de
pantalla y su hoja no se carga; la rejilla (7/12 + 5/12 desde 1200 px) y el contraste de lo nuevo, CALCULADO.
"""

# ruff: noqa: F811  (los fixtures se importan de otros módulos y se usan como argumentos)
import re
from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone, translation

from apps.core.test_lv315_identity_foundation import ROOT
from apps.core.testing import login_as as _login_as
from apps.dashboard.compliance_section import calm_line, summary_cards
from apps.dashboard.compliance_data import strip_text
from apps.dashboard.templatetags.compliance_charts import render_stack
from apps.dashboard.test_lv359_compliance_charts import (  # noqa: F401
    ALL_SOURCES,
    _contrast,
    _resolve,
    _sums,
    _theme_tokens,
    mix,
)
from apps.dashboard.test_lv359_compliance_permits import (  # noqa: F401
    VIEW,
    _site,
    sites,
)
from apps.reporting.models import ReportRun

URL = "dashboard-compliance"
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


def login_as(*codenames, **kwargs):
    client = _login_as(*codenames, **kwargs)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


def _cards(context):
    return {card["key"]: card for card in context["cx_cards"]}


# --- las cifras --------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("filtered", [False, True])
def test_the_cards_equal_the_panel_figures_without_maintenance(mix, sites, filtered):
    a, _b = mix
    client = login_as(*ALL_SOURCES)
    params = {"cost_center": a.pk} if filtered else {}
    panel = client.get(reverse("dashboard"), params).context
    context = client.get(reverse(URL), params).context
    cards = _cards(context)
    overdue, soon = _sums(context["cx_rings"])
    assert cards["overdue"]["n"] == overdue == panel["overdue_count"] >= 1
    assert cards["expiring"]["n"] == soon == panel["expiring_count"] >= 2
    # la mantención tiene un vencido propio y NO entra en las tarjetas
    maintenance = next(r for r in context["cx_rings"] if r["key"] == "maintenance")
    assert maintenance["counts"]["overdue"] == 1
    assert cards["overdue"]["n"] == sum(
        r["counts"]["overdue"] for r in context["cx_rings"] if r["key"] != "maintenance"
    )


@pytest.mark.django_db
def test_the_permit_cards_equal_the_table_and_the_panel_chip(sites):
    from apps.registry.models import Aircraft

    Aircraft.objects.create(
        registration="RPA-0001", type="RPA", model="M3", manufacturer="DJI"
    )
    client = login_as(*ALL_SOURCES)
    context = client.get(reverse(URL)).context
    cards = _cards(context)
    assert cards["no_permit"]["n"] == context["cx_permits"]["without_permit"] == 2
    assert cards["waiting"]["n"] == 1  # CC4 espera a la DGAC
    chip = next(
        i
        for i in client.get(reverse("dashboard")).context["attention"]
        if i["key"] == "sites_without_permit"
    )
    assert chip["count"] == cards["no_permit"]["n"]


@pytest.mark.django_db
def test_the_cards_link_to_blocks_that_exist(mix, sites):
    html = login_as(*ALL_SOURCES).get(reverse(URL)).content.decode()
    for anchor in re.findall(r'data-cx-card="\w+">\s*<a href="(#[\w-]+)"', html):
        assert f'id="{anchor[1:]}"' in html, anchor


@pytest.mark.django_db
def test_only_visible_sources_make_a_card(sites):
    assert login_as("view_alert").get(reverse(URL)).context["cx_cards"] == []
    only_permits = login_as(VIEW).get(reverse(URL)).context["cx_cards"]
    assert [c["key"] for c in only_permits] == [
        "no_permit",
        "overdue",
        "expiring",
        "waiting",
    ]
    only_maintenance = login_as("view_maintenancerecord").get(reverse(URL)).context
    assert only_maintenance["cx_cards"] == []  # la mantención no tiene tarjeta propia
    docs = login_as("view_document").get(reverse(URL)).context["cx_cards"]
    assert [c["key"] for c in docs] == ["overdue", "expiring"]


@pytest.mark.django_db
def test_a_zero_is_said_with_words_and_a_tick_and_never_in_red(db):
    html = login_as(*ALL_SOURCES).get(reverse(URL)).content.decode()
    block = html.split("data-cx-cards")[1].split("</ul>")[0]
    for text in (
        "Every site that flies has a permit",
        "Nothing overdue",
        "Nothing expires within 30 days",
        "Nothing is waiting",
    ):
        assert text in block
    assert "✕" not in block and "▲" not in block and "◐" not in block
    assert block.count("✓") == 4 and block.count("id-cx-card--zero") == 4


@pytest.mark.django_db
def test_a_non_zero_card_shows_its_symbol_and_the_explanation(mix, sites):
    html = login_as(*ALL_SOURCES).get(reverse(URL)).content.decode()
    block = html.split("data-cx-cards")[1].split("</ul>")[0]
    assert "They cannot fly today" in block and "Worth renewing now" in block
    for key, symbol in (("no_permit", "✕"), ("overdue", "✕"), ("expiring", "▲")):
        card = block.split(f'data-cx-card="{key}"')[1].split("</li>")[0]
        assert symbol in card, key


def test_cards_and_calm_line_are_built_from_what_is_already_computed():
    rings = [
        {
            "key": "papers",
            "label": "Documents",
            "counts": {"overdue": 2, "due_7": 1, "due_15": 0, "due_30": 1},
            "attend": 4,
        },
        {
            "key": "maintenance",
            "label": "Maintenance",
            "counts": {"overdue": 5, "due_7": 0, "due_15": 0, "due_30": 0},
            "attend": 0,
        },
    ]
    permits = {"without_permit": 2, "total": 7, "tally": [{"key": "waiting", "n": 3}]}
    cards = {c["key"]: c["n"] for c in summary_cards(rings, permits)}
    assert cards == {"no_permit": 2, "overdue": 2, "expiring": 2, "waiting": 3}
    assert calm_line(rings, permits) == {
        "names": "Maintenance",
        "sites": "5 of 7 sites with a permit in force",
    }
    assert calm_line([], None) is None
    assert summary_cards(None, None) == []


# --- G5: también en el panel -----------------------------------------------------------------


@pytest.mark.django_db
def test_the_panel_fragment_has_the_cards_and_not_what_to_attend_first(mix, sites):
    client = login_as(*ALL_SOURCES)
    fragment = client.get(reverse(URL), **HX).content.decode()
    assert "data-cx-cards" in fragment and 'data-cx-block="first"' not in fragment
    page = client.get(reverse(URL)).content.decode()
    assert "data-cx-cards" in page and 'data-cx-block="first"' in page


@pytest.mark.django_db
def test_the_header_says_situation_as_of_today_and_the_report_is_a_snapshot(mix):
    ReportRun.objects.create(
        period=date(2026, 8, 1),
        generated_by="cron",
        status=ReportRun.STATUS_APPROVED,
        payload={"meta": {"cutoff": "2026-08-31"}},
    )
    html = login_as(*ALL_SOURCES, "view_reportrun").get(reverse(URL)).content.decode()
    today = timezone.localdate().strftime("%d-%m-%Y")
    assert f"Situation as of today, {today} · all sites" in html
    assert "snapshot of 31-08-2026" in html
    assert "What follows is today's situation, not the report's." in html


# --- las tiras y la barra apilada ------------------------------------------------------------


@pytest.mark.django_db
def test_every_visible_category_has_exactly_one_strip_with_its_words_and_link(mix):
    html = login_as(*ALL_SOURCES).get(reverse(URL)).content.decode()
    for key in ("papers", "people", "aircraft", "permits", "maintenance"):
        assert html.count(f'data-cx-ring="{key}"') == 1, key
    aircraft = re.search(
        r'<li class="id-cx-strip" data-cx-ring="aircraft">.*?</li>', html, re.S
    ).group(0)
    assert "1 overdue" in aircraft and "to attend within 30 days" in aircraft
    assert f'href="{reverse("aircraft-list")}"' in aircraft


@pytest.mark.django_db
def test_the_strip_link_exists_only_if_the_person_can_open_the_list(mix):
    # `view_qualification` muestra la categoría «Personas», pero su lista pide `view_operator`
    context = login_as("view_qualification").get(reverse(URL)).context
    people = next(r for r in context["cx_rings"] if r["key"] == "people")
    assert people["url"] == ""
    html = login_as("view_operator").get(reverse(URL)).content.decode()
    assert f'href="{reverse("operator-list")}"' in html


def test_the_strip_text_has_no_zeros_and_nothing_says_so():
    zero = {"overdue": 0, "due_7": 0, "due_15": 0, "due_30": 0, "later": 0}
    assert strip_text(zero) == "Nothing in 90 days"
    assert strip_text({**zero, "later": 3}) == "3 later"
    text = strip_text({**zero, "overdue": 1, "due_7": 1, "due_30": 2, "later": 4})
    assert text == "1 overdue · 3 to attend within 30 days · 4 later"


def test_the_stack_draws_one_rect_per_non_zero_part_in_attributes_only():
    svg = render_stack(
        [("a", 3), ("b", 0), ("c", 1)], "u", "Title", "Desc 3 and 1", width=100
    )
    assert svg.count('class="id-cx-stk ') == 2
    assert 'role="img"' in svg and "<title" in svg and "<desc" in svg
    assert "style=" not in svg and "translateX" not in svg
    widths = [
        float(w)
        for w in re.findall(r'class="id-cx-stk [^"]*"[^>]*width="([\d.]+)"', svg)
    ]
    assert widths[0] == pytest.approx(widths[1] * 3, rel=0.02)
    assert sum(widths) <= 100


def test_a_tiny_part_is_still_visible_and_nothing_overflows():
    svg = render_stack([("a", 400), ("b", 1)], "u", "t", "d", width=100)
    widths = [
        float(w)
        for w in re.findall(r'class="id-cx-stk [^"]*"[^>]*width="([\d.]+)"', svg)
    ]
    assert min(widths) >= 2.9 and sum(widths) <= 100
    assert render_stack([("a", 0)], "u", "t", "d") == ""


def test_the_stack_escapes_what_comes_from_outside():
    svg = render_stack([('x"><script>', 1)], 'u"', "<b>t</b>", "<i>d</i>")
    assert "<script>" not in svg and "<b>" not in svg and "<i>" not in svg


# --- el mapa de calor: fuera de pantalla, no de código ---------------------------------------


def _templates():
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "templates").rglob("*.html")
        if p.name != "_compliance_heat.html"
    )


def test_the_heat_map_is_parked_with_its_closing_condition_and_loaded_nowhere():
    partial = (ROOT / "templates/dashboard/_compliance_heat.html").read_text(
        encoding="utf-8"
    )
    assert "CONDICIÓN DE CIERRE" in partial and "G4" in partial
    # ninguna plantilla lo incluye ni carga su hoja (los comentarios pueden nombrarlos)
    include = r"""\{%\s*include\s+['"]dashboard/_compliance_heat\.html"""
    assert not re.search(include, _templates())
    assert not re.search(r"href=[^>]*compliance-heat\.css", _templates())
    parked = (ROOT / "static/css/compliance-heat.css").read_text(encoding="utf-8")
    assert ".id-cx-heat" in parked and "RETIRADO DE PANTALLA" in parked
    assert not re.search(
        r"\banimation\b|transition\s*:|translateX|^\s*--", parked, re.M
    )
    live = (ROOT / "static/css/compliance.css").read_text(encoding="utf-8")
    assert ".id-cx-heat" not in live and ".id-cx-cell" not in live
    assert "--id-cx-heat-1" in live  # los tokens esperan con él


@pytest.mark.django_db
def test_the_heat_map_data_is_still_computed(mix):
    context = login_as(*ALL_SOURCES).get(reverse(URL)).context
    assert context["cx_heat_rows"] and context["cx_heat_wide_columns"]


# --- la rejilla y el contraste ---------------------------------------------------------------


def _css():
    return (ROOT / "static/css/compliance.css").read_bytes().decode("utf-8")


def test_the_grid_is_four_cards_and_seven_five_from_1200_and_two_by_two_before():
    css = _css()
    assert re.search(
        r"\.id-cx-cards \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)",
        css,
    )
    wide = css.split("@media (min-width: 1200px) {")[1].split("\n}\n")[0]
    assert "repeat(4, minmax(0, 1fr))" in wide
    assert "repeat(12, minmax(0, 1fr))" in wide
    assert ".id-cx-fold--wide { grid-column: span 7; }" in wide
    assert ".id-cx-side { grid-column: span 5; }" in wide
    assert re.search(
        r"\.id-cx-fold \{ grid-column: 1 / -1;", css
    )  # permisos a todo el ancho


@pytest.mark.django_db
def test_permits_come_before_the_expiries_and_the_side_column_holds_alerts_and_maintenance(
    mix, sites
):
    html = login_as(*ALL_SOURCES).get(reverse(URL)).content.decode()
    order = [
        html.index(marker)
        for marker in (
            "data-cx-cards",
            'data-cx-block="permits"',
            'data-cx-block="expiries"',
            'class="id-cx-side"',
            'data-cx-block="alerts"',
            'data-cx-block="maintenance"',
            'data-cx-block="history"',
        )
        if marker in html
    ]
    assert order == sorted(order) and len(order) >= 6


def test_the_strip_stacks_at_every_width_and_the_cards_stay_two_by_two_before_1200():
    # medido: en la columna de 7/12 (507 px) una fila de cuatro columnas dejaba el texto en 36 px
    css = _css()
    assert re.search(
        r"\.id-cx-strip \{ display: grid; grid-template-columns: minmax\(0, 1fr\) auto;",
        css,
    )
    assert ".id-cx-strip-bar, .id-cx-strip-text { grid-column: 1 / -1; }" in css
    assert "repeat(4" not in css.split("@media (min-width: 1200px)")[0]


def test_the_new_rules_have_no_motion_and_no_style_attributes():
    css = _css()
    assert not re.search(
        r"\banimation(-[a-z]+)?\s*:|@keyframes|transition\s*:|translateX", css
    )
    assert "prefers-reduced-motion" not in css


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "symbol",
    ["--sev-critical-text", "--sev-warning-text", "--id-cx-wait-fg", "--id-ok-text"],
)
def test_the_card_symbols_read_on_the_tile(theme, symbol):
    tokens = _theme_tokens(theme)
    ratio = _contrast(
        _resolve(tokens[symbol], tokens), _resolve(tokens["--id-tile"], tokens)
    )
    assert ratio >= 4.5, (theme, symbol, ratio)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "fill",
    [
        "--sev-critical-text",
        "--sev-warning-text",
        "--sev-advisory-text",
        "--sev-nominal-text",
    ],
)
def test_the_stack_fills_reach_3_to_1_on_the_track_and_the_card(theme, fill):
    tokens = _theme_tokens(theme)
    for ground in ("--id-cx-track", "--ac-surface"):
        ratio = _contrast(
            _resolve(tokens[fill], tokens), _resolve(tokens[ground], tokens)
        )
        assert ratio >= 3, (theme, fill, ground, ratio)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_card_text_reads_on_the_tile_and_its_edge_is_a_shape(theme):
    tokens = _theme_tokens(theme)
    tile = _resolve(tokens["--id-tile"], tokens)
    for name in ("--ac-text", "--ac-text-secondary"):
        assert _contrast(_resolve(tokens[name], tokens), tile) >= 4.5, (theme, name)
    assert _contrast(_resolve(tokens["--id-edge"], tokens), tile) >= 3
