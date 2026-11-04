"""LV-412: la tabla «Permisos de vuelo por centro de costo», columnas Centro de costo y Estado.

Se fija:
- el chip de estado y la barra de días salen del MISMO dato (`permit_band` -> `BAND_CHIP`): mismo tono;
- tres colores, los del semáforo (rojo sin permiso, ámbar, verde): el cian de «Renovar pronto» no vuelve;
- el chip dice el ESTADO y «Qué hay que hacer» la acción: no se repiten;
- la leyenda al pie tiene un chip por estado posible (`KINDS`), dibujado igual que en las filas;
- la línea bajo la faena dice algo útil en español natural;
- el contraste CALCULADO de los textos tocados (≥ 4,5:1 en los dos temas), leyendo los tokens de la regla.
"""

# ruff: noqa: F811  (los fixtures se importan de otros módulos y se usan como argumentos)
import re

import pytest
from django.utils import translation

from apps.compliance.kpis import (
    PERMIT_BAND_CRITICAL,
    PERMIT_BAND_NOMINAL,
    PERMIT_BAND_WARNING,
    permit_band,
)
from apps.dashboard.compliance_permits import BAND_CHIP, KIND_CHIP, KINDS, chip_css
from apps.dashboard.test_lv359_compliance_charts import (
    _contrast,
    _resolve,
    _theme_tokens,
)
from apps.dashboard.test_lv359_compliance_permits import (  # noqa: F401
    _page,
    _permit,
    _permits_block,
    _site,
)
from apps.dashboard.test_lv376_permits_v4 import (  # noqa: F401
    VIEW,
    _css,
    english,
    login_as,
    mix,
)
from apps.operations.models import FlightPermission


def _rows_html(html):
    return _permits_block(html).split("<tbody>")[1].split("</tr>")[:-1]


@pytest.mark.django_db
def test_the_chip_and_the_bar_come_from_the_same_band(mix):
    response = _page(login_as(VIEW))
    html = response.content.decode()
    rows = response.context["cx_permits"]["rows"]
    drawn = _rows_html(html)
    with_bar = 0
    for row, markup in zip(rows, drawn, strict=True):
        assert f'<span class="{row["chip"]["css"]}">' in markup
        if row["days_remaining"] is None:
            assert "id-cx-daybar" not in markup
            continue
        with_bar += 1
        band = permit_band(row["days_remaining"])
        # el tono del chip es el del tramo de `permit_band`, y la barra lleva ese mismo tono
        assert row["chip"]["tone"] == BAND_CHIP[band][1]
        assert f"id-cx-day--{row['chip']['tone']}" in markup
    assert with_bar == 3  # CC3, CC4 y CC5


def test_three_colors_as_the_traffic_light_and_the_two_ambers_differ_by_shape_and_weight():
    assert BAND_CHIP[PERMIT_BAND_NOMINAL][1] == "ok"
    critical, warning = BAND_CHIP[PERMIT_BAND_CRITICAL], BAND_CHIP[PERMIT_BAND_WARNING]
    assert critical[1] == warning[1] == "warning"  # ámbar los dos: ≤30 y 31–60
    assert critical[0] != warning[0] and critical[2] != warning[2]  # forma y peso
    tones = {tone for _symbol, tone, _soft in KIND_CHIP.values()}
    assert tones == {"none", "wait", "warning", "ok"}
    assert "advisory" not in _css().split(".id-cx-state {")[1].split("/*")[0]


def test_the_state_chip_never_breaks_so_the_column_takes_the_longest_one():
    rule = _css().replace("\r\n", "\n").split("\n.id-cx-state {")[1].split("}")[0]
    assert "white-space: nowrap" in rule
    # a 375 px la tarjeta recorta lo que sobra (`overflow: hidden`): ahí el chip vuelve a partirse
    phone = _css().split("@media (max-width: 575.98px) {")[1].split("\n}\n")[0]
    assert ".id-cx-permits .id-cx-state { white-space: normal; }" in phone


@pytest.mark.django_db
def test_the_chip_says_the_state_and_the_action_is_not_repeated(mix):
    rows = _page(login_as(VIEW)).context["cx_permits"]["rows"]
    for row in rows:
        assert row["chip"]["label"] not in row["action"]["text"], row["kind"]
    ok = next(row for row in rows if row["kind"] == "ok")
    assert ok["action"]["text"] == "Nothing to do"


@pytest.mark.django_db
def test_the_legend_has_one_chip_per_possible_state_drawn_as_in_the_rows(mix):
    response = _page(login_as(VIEW))
    html = response.content.decode()
    key = html.split("data-cx-key>")[1].split("</div>")[0]
    kinds = re.findall(r'data-cx-key-kind="(\w+)"', key)
    assert kinds == list(KINDS)
    for item in response.context["cx_permits"]["legend"]:
        assert item["css"] == chip_css(item["kind"])
        assert (
            f'<span class="{item["css"]}"><span aria-hidden="true">{item["symbol"]}</span> {item["label"]}</span>'
            in key
        )
    legend = {item["kind"]: item for item in response.context["cx_permits"]["legend"]}
    for row in response.context["cx_permits"]["rows"]:
        assert row["chip"]["css"] == legend[row["kind"]]["css"]
        assert row["chip"]["symbol"] == legend[row["kind"]]["symbol"]
        if (
            row["kind"] != "not_started"
        ):  # la fila lleva la fecha; la leyenda, «más adelante»
            assert row["chip"]["label"] == legend[row["kind"]]["label"]


@pytest.mark.django_db
def test_the_line_under_the_site_says_something_useful(db):
    nothing = _site("CC1")
    busy = _site("CC2")
    for days in (100, 120, 140, 160):
        _permit(busy, days)
    _permit(busy, 30, status=FlightPermission.STATUS_REQUESTED)
    del nothing
    with translation.override("es"):
        client = login_as(VIEW)
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
        rows = {
            row["cost_center"].code: row["counts_text"]
            for row in _page(client).context["cx_permits"]["rows"]
        }
    assert rows["CC1"] == "Sin permiso vigente"
    assert rows["CC2"] == "4 permisos vigentes · 1 en trámite ante la DGAC"


def _rule_tokens(selector, prop):
    body = _css().split(f"{selector} {{")[1].split("}")[0]
    return re.search(rf"(?:^|;)\s*{prop}:\s*var\((--[\w-]+)\)", body).group(1)


TEXT_PAIRS = (
    # (selector, propiedad del texto, token del fondo real)
    (
        ".id-cx-site .cc-chip",
        "color",
        _rule_tokens(".id-cx-site .cc-chip", "background"),
    ),
    (".id-cx-permits .id-cx-site-counts", "color", "--ac-surface"),
    # las filas sin permiso heredaban la tinta del tema claro en el oscuro (`color: inherit`)
    (
        ".id-cx-permits tr.row-critical > td, .id-cx-permits tr.row-awaiting > td",
        "color",
        "--ac-surface",
    ),
    (".id-cx-state--soft", "color", _rule_tokens(".id-cx-state--soft", "background")),
)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("selector", "prop", "bg"), TEXT_PAIRS)
def test_the_touched_texts_reach_4_5_to_1(theme, selector, prop, bg):
    tokens = _theme_tokens(theme)
    fg = _rule_tokens(selector, prop)
    ratio = _contrast(_resolve(tokens[fg], tokens), _resolve(tokens[bg], tokens))
    assert ratio >= 4.5, (theme, selector, fg, bg, ratio)
    # y no es el gris de antes: la faena se escribe en tinta
    if selector != ".id-cx-state--soft":
        assert fg == "--ac-text"
