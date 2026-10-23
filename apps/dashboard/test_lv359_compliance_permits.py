"""LV-359 (fase 4): la tabla «Permisos por faena», mudada del panel a «Cumplimiento».

Lo que se vigila:
- una sola fuente de cálculo: las filas son las de `permit_status_by_cost_center(hoy, usuario)` y el
  tramo el de `permit_band` (30/60 días); aquí sólo se ordena y se presenta;
- orden `?sort=&dir=` con lista permitida (cualquier otra cosa se ignora y no se refleja), con
  `aria-sort`, vacíos al final en los dos sentidos y el orden de LV-246 sin orden pedido;
- permisos y tenant: sin `view_flightpermission` ni la tabla ni los nombres; otro tenant no aparece
  ni en las filas ni en el detalle;
- medidor (0 a 90, bajo 30, alto 60) con el texto «17 d» y un chip con símbolo y palabra;
- la faena es un `<details>` dentro de su celda (sin `colspan`) y el detalle cuesta UNA consulta,
  no una por fila;
- el panel ya no dibuja la tabla y su hueco lleva el ancla `#cx-permits`.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.compliance.kpis import permit_band, permit_status_by_cost_center
from apps.core.models import OperationalTenant
from apps.core.tenancy import visible_tenant_ids
from apps.core.testing import login_as
from apps.dashboard.compliance_permits import (
    DETAIL_LIMIT,
    ordered_rows,
    permit_table,
    requested_sort,
)
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

URL = "dashboard-compliance"
HX = {"HTTP_HX_REQUEST": "true"}
TODAY = timezone.localdate()
VIEW = "view_flightpermission"


def _site(code, **extra):
    return CostCenter.objects.create(
        code=code, name=f"Faena {code}", operates_flights=True, **extra
    )


def _permit(site, days, status=FlightPermission.STATUS_APPROVED, number=""):
    """Un permiso que vence en `days` días (negativo: ya venció)."""
    until = TODAY + timedelta(days=days)
    return FlightPermission.objects.create(
        cost_center=site,
        purpose="photogrammetry",
        status=status,
        permission_number=number or None,
        location="Sector",
        area_type="unpopulated",
        valid_from=min(until - timedelta(days=60), TODAY - timedelta(days=1)),
        valid_until=until,
    )


def _page(client, **params):
    return client.get(reverse(URL), params)


def _permits_block(html):
    """El bloque de permisos: el armazón de la página (selector de idioma, etc.) refleja la URL."""
    return html.split('data-cx-block="permits"')[1].split("</table>")[0]


def _head(html):
    return _permits_block(html).split("<thead>")[1].split("</thead>")[0]


def _rows(client, **params):
    """Todas las filas (`?all=1`): por omisión la tabla muestra sólo las faenas con problema (LV-367)."""
    return _page(client, all="1", **params).context["cx_permits"]["rows"]


def _codes(rows):
    return [row["cost_center"].code for row in rows]


@pytest.fixture
def sites(db):
    """CC1 vence en 12 días, CC2 en 50, CC3 en 200; CC4 espera, CC5 no tiene nada."""
    one, two, three, four, five = (_site(f"CC{n}") for n in range(1, 6))
    _permit(one, 12)
    _permit(two, 50)
    _permit(three, 200)
    _permit(four, 30, status=FlightPermission.STATUS_REQUESTED)
    return one, two, three, four, five


# --- una sola fuente de cálculo ---------------------------------------------------------------


@pytest.mark.django_db
def test_the_rows_are_the_ones_the_kpi_computes(sites):
    client = login_as(VIEW)
    expected = {
        row["cost_center"].code: row
        for row in permit_status_by_cost_center(TODAY, client.user)
    }
    rows = _rows(client)
    assert set(_codes(rows)) == set(expected)
    for row in rows:
        source = expected[row["cost_center"].code]
        for key in ("in_force", "soon", "awaiting", "days_remaining", "next_expiry"):
            assert row[key] == source[key]
        assert row["band"] == permit_band(source["days_remaining"])


@pytest.mark.django_db
def test_without_a_requested_order_the_sites_without_a_permit_lead(sites):
    codes = _codes(_rows(login_as(VIEW)))
    # LV-246: sin permiso vigente primero (CC4 espera, CC5 nada), después por código
    assert codes == ["CC4", "CC5", "CC1", "CC2", "CC3"]


# --- el orden ---------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("column", "direction", "expected"),
    [
        ("code", "asc", ["CC1", "CC2", "CC3", "CC4", "CC5"]),
        ("code", "desc", ["CC5", "CC4", "CC3", "CC2", "CC1"]),
        # `days`: los que no tienen fecha (CC4 y CC5) van al final en los DOS sentidos
        ("days", "asc", ["CC1", "CC2", "CC3", "CC4", "CC5"]),
        ("days", "desc", ["CC3", "CC2", "CC1", "CC4", "CC5"]),
        ("in_force", "desc", ["CC1", "CC2", "CC3", "CC4", "CC5"]),
        ("awaiting", "desc", ["CC4", "CC1", "CC2", "CC3", "CC5"]),
    ],
)
def test_each_column_sorts_both_ways(sites, column, direction, expected):
    rows = _rows(login_as(VIEW), sort=column, dir=direction)
    assert _codes(rows) == expected


@pytest.mark.django_db
def test_soon_and_past_are_sortable_columns(sites):
    # CC1 vence en 12 días (vence pronto); una faena con un aprobado vencido sin cerrar
    late = _site("CC6")
    _permit(late, -5)
    client = login_as(VIEW)
    assert _codes(_rows(client, sort="soon", dir="desc"))[0] == "CC1"
    assert _codes(_rows(client, sort="past", dir="desc"))[0] == "CC6"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "junk",
    [
        '"><script>alert(1)</script>',
        "cost_center__name",
        "code; drop table",
        "-days",
        "",
        "CODE",
    ],
)
def test_an_unknown_sort_is_ignored_and_never_reflected(sites, junk):
    client = login_as(VIEW)
    default = _codes(_rows(client))
    response = _page(client, all="1", sort=junk, dir="desc")
    assert response.status_code == 200
    assert _codes(response.context["cx_permits"]["rows"]) == default
    html = response.content.decode()
    block = _permits_block(html)
    assert "<script>alert" not in block
    if junk:
        assert f"sort={junk}" not in block
    assert 'aria-sort="ascending"' not in block
    assert 'aria-sort="descending"' not in block


@pytest.mark.django_db
def test_an_unknown_direction_falls_back_to_ascending(sites):
    assert requested_sort({"sort": "days", "dir": "sideways"}) == ("days", "asc")
    assert requested_sort({"sort": "nope", "dir": "desc"}) == ("", "")


@pytest.mark.django_db
def test_headers_carry_aria_sort_and_flip_their_link(sites):
    client = login_as(VIEW)
    html = _page(client, sort="days", dir="asc").content.decode()
    head = _head(html)
    assert (
        head.count("aria-sort=") == 3
    )  # LV-367: tres columnas (Faena, Estado, Próximo vencimiento)
    assert head.count('aria-sort="ascending"') == 1
    assert head.count('aria-sort="none"') == 2
    # el enlace de la columna ya ordenada pide el sentido contrario, con ruta propia y ancla
    assert f"{reverse(URL)}?sort=days&amp;dir=desc#cx-permits" in head
    assert f"{reverse(URL)}?sort=code&amp;dir=asc#cx-permits" in head


@pytest.mark.django_db
def test_the_sort_links_keep_the_chosen_site(sites):
    one = sites[0]
    html = _page(login_as(VIEW), cost_center=one.pk).content.decode()
    head = _head(html)
    assert f"?cost_center={one.pk}&amp;sort=code&amp;dir=asc#cx-permits" in head


@pytest.mark.django_db
def test_the_fragment_links_to_the_section_not_to_the_panel(sites):
    """El fragmento se pinta dentro del panel: un `?sort=` suelto resolvería contra él."""
    html = login_as(VIEW).get(reverse(URL), **HX).content.decode()
    assert f'href="{reverse(URL)}?sort=' in html
    assert 'href="?sort=' not in html


def test_ordering_is_stable_and_pure():
    class Site:
        def __init__(self, code):
            self.code = code

    def row(code, days):
        return {"cost_center": Site(code), "days_remaining": days, "in_force": 1}

    rows = [row("B", 5), row("A", 5), row("C", None), row("D", 1)]
    assert [r["cost_center"].code for r in ordered_rows(rows, "days", "asc")] == [
        "D",
        "A",
        "B",
        "C",
    ]
    assert [r["cost_center"].code for r in ordered_rows(rows, "days", "desc")] == [
        "A",
        "B",
        "D",
        "C",
    ]


# --- permisos y tenant ------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_table_needs_view_flightpermission(sites):
    alerts_only = _page(login_as("view_alert")).content.decode()
    assert 'data-cx-block="permits"' not in alerts_only
    assert 'id="cx-permits"' not in alerts_only
    for name in ("CC1", "CC5", "Faena CC1"):
        assert name not in alerts_only

    seeing = _page(login_as(VIEW)).content.decode()
    assert 'data-cx-block="permits"' in seeing
    assert "Faena CC1" in seeing


@pytest.mark.django_db
def test_the_data_is_never_built_without_the_permission(sites):
    user = login_as("view_alert").user
    assert permit_table(user, None, TODAY, None) is None


@pytest.mark.django_db
def test_another_tenants_sites_and_permits_are_not_listed(sites):
    mine = OperationalTenant.objects.create(name="Mine", slug="mine")
    own = _site("CC900", tenant=mine)
    _permit(own, 20, number="MIO-1")
    client = login_as(VIEW, member_of=mine)
    html = _page(client).content.decode()
    assert _codes(_rows(client)) == ["CC900"]
    assert "MIO-1" in html
    for foreign in ("CC1", "CC2", "CC3", "CC4", "CC5"):
        assert f"Faena {foreign}" not in html


@pytest.mark.django_db
def test_the_detail_of_a_foreign_site_is_not_reachable_by_choosing_it(sites):
    mine = OperationalTenant.objects.create(name="Mine", slug="mine")
    _site("CC900", tenant=mine)
    foreign = sites[0]
    _permit(foreign, 15, number="AJENO-1")
    client = login_as(VIEW, member_of=mine)
    html = _page(client, cost_center=foreign.pk).content.decode()
    assert "AJENO-1" not in html and "Faena CC1" not in html


# --- el medidor y los chips -------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("days", "symbol", "tone"),
    [
        (30, "✕", "critical"),
        (31, "▲", "warning"),
        (60, "▲", "warning"),
        (61, "●", "ok"),
    ],
)
def test_the_band_boundaries_are_the_kpis_30_and_60(db, days, symbol, tone):
    site = _site("CC1")
    _permit(site, days)
    html = _page(login_as(VIEW), all="1").content.decode()
    cell = _permits_block(html).split("<tbody>")[1].split("</tr>")[0].split("<td")[2]
    assert (
        f'<span class="id-chip id-chip--{tone}"><span aria-hidden="true">{symbol}</span>'
        in cell
    )


@pytest.mark.django_db
def test_the_meter_has_the_scale_and_the_text_carries_the_days(db):
    site = _site("CC1")
    _permit(site, 17)
    _permit(_site("CC2"), 200)
    html = _page(login_as(VIEW), all="1").content.decode()
    assert 'min="0" max="90" low="30" high="60" optimum="90" value="17"' in html
    assert gettext("%(n)s d") % {"n": 17} in html
    # más de 90 días: el valor se acota al máximo del medidor, el texto dice los 200 reales
    assert 'value="90"' in html
    assert gettext("%(n)s d") % {"n": 200} in html


@pytest.mark.django_db
def test_a_row_without_a_date_has_no_meter(db):
    _site("CC5")
    html = _page(login_as(VIEW)).content.decode()
    assert "<meter" not in html


@pytest.mark.django_db
def test_the_state_cell_says_what_there_is_with_symbol_and_word(sites):
    html = _page(login_as(VIEW)).content.decode()
    body = _permits_block(html).split("<tbody>")[1]
    assert f"▲</span> {gettext('Awaiting')}" in body  # CC4
    assert f"✕</span> {gettext('None')}" in body  # CC5


# --- la fila expandible -----------------------------------------------------------------------


@pytest.mark.django_db
def test_the_site_is_a_details_inside_its_cell_with_no_colspan(sites):
    html = _page(login_as(VIEW), all="1").content.decode()
    table = html.split('<table class="table table-sm table-hover mb-0 id-cx-permits">')[
        1
    ].split("</table>")[0]
    assert "colspan" not in table
    assert "table-normalized" not in table
    assert table.count("<details") == 5
    first_cell = table.split("<tbody>")[1].split("</td>")[0]
    assert "<details" in first_cell and "<summary>" in first_cell
    assert "Faena CC4" in first_cell  # sin permiso vigente va primero


@pytest.mark.django_db
def test_the_detail_lists_only_live_permits_with_a_link(db):
    site = _site("CC1")
    live = _permit(site, 20, number="VIVO-1")
    _permit(site, 25, status=FlightPermission.STATUS_DENIED, number="DENEGADO-1")
    _permit(site, -3, status=FlightPermission.STATUS_EXPIRED, number="CADUCADO-1")
    html = _page(login_as(VIEW)).content.decode()
    assert "VIVO-1" in html
    assert "DENEGADO-1" not in html and "CADUCADO-1" not in html
    assert f'href="{live.get_absolute_url()}"' in html


@pytest.mark.django_db
def test_a_long_list_is_cut_and_says_how_many_more(db):
    site = _site("CC1")
    for index in range(DETAIL_LIMIT + 3):
        _permit(site, 10 + index, number=f"P-{index:02d}")
    html = _page(login_as(VIEW)).content.decode()
    assert f"P-{DETAIL_LIMIT - 1:02d}" in html
    assert f"P-{DETAIL_LIMIT:02d}" not in html
    assert "3" in html.split("id-cx-permit-list")[1].split("</details>")[0]


@pytest.mark.django_db
def test_the_detail_costs_one_query_not_one_per_row(db):
    user = login_as(VIEW).user
    tenants = visible_tenant_ids(user)
    user.has_perm("operations.view_flightpermission")

    def count():
        with CaptureQueriesContext(connection) as queries:
            permit_table(user, None, TODAY, tenants)
        return len(queries)

    for n in range(2):
        _permit(_site(f"CC{n}"), 10 + n)
    before = count()
    for n in range(2, 12):
        site = _site(f"CC{n}")
        _permit(site, 10 + n)
        _permit(site, 40 + n)
    assert count() == before


# --- el panel ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_panel_no_longer_draws_the_table_and_the_chip_points_at_the_anchor(sites):
    from apps.registry.models import Aircraft

    Aircraft.objects.create(
        registration="RPA-0001", type="RPA", model="M3", manufacturer="DJI"
    )
    client = login_as(VIEW)
    response = client.get(reverse("dashboard"))
    html = response.content.decode()
    assert "panel-permit-status-title" not in html
    assert "permit_status_rows" not in response.context
    assert 'id="cx-permits"' in html  # el esqueleto del hueco
    chip = next(
        item
        for item in response.context["attention"]
        if item["key"] == "sites_without_permit"
    )
    assert chip["url"] == "#cx-permits"
    assert chip["count"] == 2  # CC4 y CC5
