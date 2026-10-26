"""LV-376 (fase 1b): la tabla «Permisos de vuelo por centro de costo» v4.

Se fija: resumen con `?state=` de lista permitida (las cifras son SIEMPRE las totales, y todas las faenas
siguen visibles por omisión), `q` sólo en la página completa, «Nuevo permiso» y «Renovar» sólo con su
permiso (y el `pk` a renovar es el del permiso que vence primero), «esperando desde» sale de `created_at`,
el ámbar «Renovar ya» (el rojo es sólo «sin permiso»), la barra de días sin `style`, el contraste CALCULADO de
los chips sólidos y de los tokens de espera, y que no cuesta consultas nuevas.
"""

# ruff: noqa: F811  (los fixtures se importan de otros módulos y se usan como argumentos)
import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from apps.core.models import OperationalTenant
from apps.core.test_lv315_identity_foundation import ROOT
from apps.core.testing import login_as as _login_as
from apps.dashboard.compliance_permits import (
    STATE_FILTERS,
    kind_of,
    permit_table,
    requested_query,
    requested_state,
)
from apps.dashboard.templatetags.compliance_charts import render_daybar
from apps.dashboard.test_lv359_compliance_charts import (
    _contrast,
    _resolve,
    _theme_tokens,
)
from apps.dashboard.test_lv359_compliance_permits import (  # noqa: F401
    HX,
    TODAY,
    URL,
    VIEW,
    _codes,
    _page,
    _permit,
    _permits_block,
    _rows,
    _site,
    sites,
)
from apps.operations.models import FlightPermission


@pytest.fixture(autouse=True)
def english():
    """Las cadenas se comparan en inglés (la fuente); el español se activa aparte."""
    with translation.override("en"):
        yield


def login_as(*codenames, **kwargs):
    client = _login_as(*codenames, **kwargs)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


ADD = "add_flightpermission"
GEO = "add_geoplan"


@pytest.fixture
def mix(db):
    """Una faena de cada estado: CC1 sin nada, CC2 espera, CC3 vence en 20 d, CC4 en 45 d, CC5 en 200 d."""
    none, waiting, soon, mid, far = (_site(f"CC{n}") for n in range(1, 6))
    _permit(waiting, 30, status=FlightPermission.STATUS_REQUESTED)
    _permit(soon, 20, number="P-SOON")
    _permit(mid, 45)
    _permit(far, 200)
    return none, waiting, soon, mid, far


def _tbody(html):
    return _permits_block(html).split("<tbody>")[1]


def _row_of(html, code):
    return next(r for r in _tbody(html).split("</tr>") if f">{code}</span>" in r)


# --- el resumen y el filtro -------------------------------------------------------------------


@pytest.mark.django_db
def test_the_summary_counts_are_the_totals_of_every_site(mix):
    context = _page(login_as(VIEW)).context["cx_permits"]
    assert {t["key"]: t["n"] for t in context["tally"]} == {
        "none": 1,
        "waiting": 1,
        "renew": 2,
        "ok": 1,
    }
    assert context["total"] == 5 and context["without_permit"] == 2
    # «sin permiso» + «esperando» del resumen son las faenas sin permiso vigente: la cifra del panel
    tally = {t["key"]: t["n"] for t in context["tally"]}
    assert tally["none"] + tally["waiting"] == context["without_permit"]


@pytest.mark.django_db
def test_the_panel_chip_and_the_section_agree_on_sites_without_a_permit(mix):
    from apps.registry.models import Aircraft

    Aircraft.objects.create(
        registration="RPA-0001", type="RPA", model="M3", manufacturer="DJI"
    )
    client = login_as(VIEW)
    chip = next(
        item
        for item in client.get(reverse("dashboard")).context["attention"]
        if item["key"] == "sites_without_permit"
    )
    assert chip["count"] == _page(client).context["cx_permits"]["without_permit"] == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("none", ["CC1"]),
        ("waiting", ["CC2"]),
        ("renew", ["CC3", "CC4"]),
        ("ok", ["CC5"]),
    ],
)
def test_state_filters_the_rows_and_never_moves_the_figures(mix, state, expected):
    client = login_as(VIEW)
    response = _page(client, state=state)
    context = response.context["cx_permits"]
    assert _codes(context["rows"]) == expected
    # las cifras siguen siendo las de las cinco faenas
    assert context["total"] == 5 and context["without_permit"] == 2
    assert sum(t["n"] for t in context["tally"]) == 5
    html = response.content.decode()
    assert "data-cx-showing" in html
    assert f"Showing {len(expected)} of 5" in html
    assert next(t for t in context["tally"] if t["key"] == state)["active"] is True


@pytest.mark.django_db
def test_every_site_is_visible_by_default(mix):
    response = _page(login_as(VIEW))
    context = response.context["cx_permits"]
    assert len(context["rows"]) == 5 and not context["filtered"]
    assert "data-cx-showing" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "junk", ["", "all", "NONE", "none; drop", '"><script>alert(1)</script>', "renew,ok"]
)
def test_an_unknown_state_is_ignored_and_never_reflected(mix, junk):
    client = login_as(VIEW)
    response = _page(client, state=junk)
    assert len(response.context["cx_permits"]["rows"]) == 5
    block = _permits_block(response.content.decode())
    assert "<script>alert" not in block
    if junk:
        assert f"state={junk}" not in block
    assert requested_state({"state": junk}) == ""


def test_the_allowed_states_cover_every_kind_exactly_once():
    from apps.dashboard.compliance_permits import KINDS

    covered = [kind for kinds in STATE_FILTERS.values() for kind in kinds]
    assert sorted(covered) == sorted(KINDS)


@pytest.mark.django_db
def test_the_state_links_go_to_the_full_page_even_inside_the_panel(mix):
    html = login_as(VIEW).get(reverse(URL), **HX).content.decode()
    nav = html.split("data-cx-tally")[1].split("</nav>")[0]
    assert f'href="{reverse(URL)}?state=none#cx-permits"' in nav
    assert 'href="?' not in nav


@pytest.mark.django_db
def test_the_sort_links_keep_the_active_filter(mix):
    html = _page(login_as(VIEW), state="renew", q="CC").content.decode()
    head = _permits_block(html).split("<thead>")[1].split("</thead>")[0]
    assert "state=renew&amp;q=CC&amp;sort=code" in head


# --- la búsqueda ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_q_filters_by_code_or_name_only_on_the_full_page(mix):
    client = login_as(VIEW)
    assert _codes(_page(client, q="cc3").context["cx_permits"]["rows"]) == ["CC3"]
    assert _codes(_page(client, q="faena cc4").context["cx_permits"]["rows"]) == ["CC4"]
    assert _page(client, q="zzz").context["cx_permits"]["rows"] == []
    # el fragmento del panel no tiene cuadro de búsqueda y no aplica `q`
    fragment = client.get(reverse(URL), {"q": "cc3"}, **HX)
    assert len(fragment.context["cx_permits"]["rows"]) == 5
    assert 'id="cx-q"' not in fragment.content.decode()
    assert 'id="cx-q"' in _page(client).content.decode()


@pytest.mark.django_db
def test_q_is_cleaned_escaped_and_never_changes_the_figures(mix):
    assert requested_query({"q": "  a   b  "}) == "a b"
    assert len(requested_query({"q": "x" * 500})) == 60
    client = login_as(VIEW)
    response = _page(client, q='"><script>alert(1)</script>')
    html = response.content.decode()
    assert "<script>alert(1)" not in html
    context = response.context["cx_permits"]
    assert context["rows"] == [] and context["total"] == 5
    assert "No site matches this filter." in html


@pytest.mark.django_db
def test_the_search_form_keeps_the_state_and_the_site(mix):
    site = mix[2]
    html = _page(login_as(VIEW), state="renew", cost_center=site.pk).content.decode()
    form = html.split('<form class="id-cx-find"')[1].split("</form>")[0]
    assert 'type="hidden" name="state" value="renew"' in form
    assert f'name="cost_center" value="{site.pk}"' in form
    assert 'role="search"' in html


# --- «Nuevo permiso» y «Renovar» --------------------------------------------------------------


@pytest.mark.django_db
def test_new_permit_links_exist_only_with_add_flightpermission(mix):
    without = _page(login_as(VIEW)).content.decode()
    assert (
        "?cost_center=" not in without.split("<tbody>")[1].split("permission-list")[0]
    )
    assert reverse("permission-create") not in without
    allowed = _page(login_as(VIEW, ADD)).content.decode()
    none_site = mix[0]
    assert f"{reverse('permission-create')}?cost_center={none_site.pk}" in allowed
    row = _row_of(allowed, "CC1")
    assert "Request a permit" in row and reverse("permission-create") in row
    # sin el permiso la frase se dice igual, sin enlace
    assert "Request a permit" in _row_of(without, "CC1")


@pytest.mark.django_db
def test_renew_needs_add_flightpermission_and_geo_add_geoplan(mix):
    soon_permit = FlightPermission.objects.get(permission_number="P-SOON")
    renew_url = f"{reverse('permission-create')}?renueva={soon_permit.pk}"
    for codes in ((VIEW,), (VIEW, ADD), (VIEW, GEO)):
        row = _row_of(_page(login_as(*codes)).content.decode(), "CC3")
        assert "?renueva=" not in row, codes
        assert "renew now" in row  # la frase se dice igual
    client = login_as(VIEW, ADD, GEO)
    full = _page(client).content.decode()
    assert renew_url in _row_of(full, "CC3")
    # los que no son «Renovar ya» no ofrecen renovar

    for code in ("CC4", "CC5", "CC1", "CC2"):
        assert "?renueva=" not in _row_of(full, code)


@pytest.mark.django_db
def test_the_renewal_is_the_permit_that_expires_first(db):
    site = _site("CC1")
    later = _permit(site, 25, number="LATER")
    first = _permit(site, 10, number="FIRST")
    html = _page(login_as(VIEW, ADD, GEO)).content.decode()
    row = _row_of(html, "CC1")
    assert f"?renueva={first.pk}" in row and f"?renueva={later.pk}" not in row


@pytest.mark.django_db
def test_the_renew_link_opens_the_renewal_form_without_a_403(mix):
    soon_permit = FlightPermission.objects.get(permission_number="P-SOON")
    client = login_as(VIEW, ADD, GEO)
    assert (
        client.get(
            f"{reverse('permission-create')}?renueva={soon_permit.pk}"
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_the_new_permit_link_preloads_the_site(mix):
    client = login_as(VIEW, ADD)
    response = client.get(f"{reverse('permission-create')}?cost_center={mix[0].pk}")
    assert response.context["form"].initial["cost_center"] == mix[0].pk


# --- el texto de cada estado ------------------------------------------------------------------


@pytest.mark.django_db
def test_waiting_since_comes_from_the_date_the_request_was_registered(db):
    site = _site("CC1")
    permit = _permit(site, 30, status=FlightPermission.STATUS_REQUESTED)
    stamp = timezone.now() - timedelta(days=9)
    FlightPermission.objects.filter(pk=permit.pk).update(created_at=stamp)
    row = _row_of(_page(login_as(VIEW)).content.decode(), "CC1")
    assert f"Waiting for the DGAC since {timezone.localtime(stamp):%d-%m}" in row


@pytest.mark.django_db
def test_a_permit_that_has_not_started_says_when_and_that_nothing_is_due(db):
    site = _site("CC1")
    start = TODAY + timedelta(days=6)
    FlightPermission.objects.create(
        cost_center=site,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        location="Sector",
        area_type="unpopulated",
        valid_from=start,
        valid_until=start + timedelta(days=90),
    )
    row = _row_of(_page(login_as(VIEW)).content.decode(), "CC1")
    assert f"Starts on {start:%d-%m}; nothing to do until then" in row
    assert f"Starts {start:%d-%m}" in row
    assert 'class="row-awaiting"' in row


@pytest.mark.django_db
def test_renew_now_is_amber_and_only_no_permit_is_red(mix):
    html = _page(login_as(VIEW)).content.decode()
    soon = _row_of(html, "CC3")
    assert "id-cx-state--warning" in soon and "▲" in soon and "Renew now" in soon
    assert "row-critical" not in soon  # G1: el rojo es sólo «no se puede volar»
    none = _row_of(html, "CC1")
    assert "id-cx-state--none" in none and 'class="row-critical"' in none
    assert "id-cx-state--advisory" in _row_of(html, "CC4")
    assert "Renew soon" in _row_of(html, "CC4")
    assert "id-cx-state--ok" in _row_of(html, "CC5")


@pytest.mark.django_db
def test_a_site_with_a_lapsed_permit_says_to_review_it(db):
    site = _site("CC1")
    _permit(site, -5)
    row = _row_of(_page(login_as(VIEW)).content.decode(), "CC1")
    assert "with a validity that has passed and is still open: review" in row


@pytest.mark.django_db
def test_the_default_order_is_urgency(mix):
    # sin permiso > esperando > ≤30 d > ≤60 d > al día
    assert _codes(_rows(login_as(VIEW))) == ["CC1", "CC2", "CC3", "CC4", "CC5"]


def test_kind_of_uses_the_kpi_scale():
    def row(days, **extra):
        base = {"in_force": 1, "awaiting": 0, "not_started": 0, "days_remaining": days}
        return {**base, **extra}

    assert [kind_of(row(d)) for d in (0, 30, 31, 60, 61)] == [
        "renew_now",
        "renew_now",
        "renew_soon",
        "renew_soon",
        "ok",
    ]
    assert kind_of(row(None, in_force=0)) == "none"
    assert kind_of(row(None, in_force=0, awaiting=1)) == "awaiting"
    assert kind_of(row(None, in_force=0, not_started=1)) == "not_started"


# --- tenant y consultas -----------------------------------------------------------------------


@pytest.mark.django_db
def test_the_summary_never_counts_another_tenants_sites(mix):
    mine = OperationalTenant.objects.create(name="Mine", slug="mine")
    _site("OWN", tenant=mine)
    client = login_as(VIEW, member_of=mine)
    context = _page(client).context["cx_permits"]
    assert context["total"] == 1 and _codes(context["rows"]) == ["OWN"]
    assert [t["n"] for t in context["tally"]] == [1]


@pytest.mark.django_db
def test_new_links_and_summary_add_no_queries_per_row(db):
    user = login_as(VIEW, ADD, GEO).user
    user.has_perm("operations.view_flightpermission")
    user.has_perm("registry.view_costcenter")

    def count():
        with CaptureQueriesContext(connection) as queries:
            permit_table(user, None, TODAY, None, state="renew", query="CC")
        return len(queries)

    for n in range(2):
        _permit(_site(f"CC{n}"), 10 + n)
    before = count()
    for n in range(2, 12):
        site = _site(f"CC{n}")
        _permit(site, 10 + n)
        _permit(site, 40 + n)
    assert count() == before


# --- la barra de días -------------------------------------------------------------------------


def test_the_daybar_geometry_is_in_attributes_and_the_colour_in_the_class():
    svg = render_daybar(45)
    assert 'aria-hidden="true"' in svg and "role=" not in svg and "style=" not in svg
    assert svg.count("<line") == 2 and 'x1="42.67"' in svg and 'x1="85.33"' in svg
    assert "id-cx-day--mid" in svg and 'width="64"' in svg


@pytest.mark.parametrize(
    ("days", "css"),
    [
        (-3, "soon"),
        (0, "soon"),
        (30, "soon"),
        (31, "mid"),
        (60, "mid"),
        (61, "far"),
        (400, "far"),
    ],
)
def test_the_daybar_band_and_clamp(days, css):
    svg = render_daybar(days)
    assert f"id-cx-day--{css}" in svg
    widths = re.findall(r'class="id-cx-day-fill[^"]*"[^>]*width="([\d.]+)"', svg)
    assert 3 <= float(widths[0]) <= 128


# --- el CSS: tarjeta a 375 px, filete y contraste calculado -----------------------------------


def _css():
    return (ROOT / "static" / "css" / "compliance.css").read_bytes().decode("utf-8")


def test_the_phone_layout_is_a_card_per_site():
    css = _css()
    phone = css.split("@media (max-width: 575.98px) {")[1].split("\n}\n")[0]
    assert "td::before { content: attr(data-cx-label)" in phone
    assert "display: block" in phone and "thead" in phone


@pytest.mark.django_db
def test_every_cell_has_its_label_and_the_page_has_no_inline_style(mix):
    html = _page(login_as(VIEW)).content.decode()
    block = _permits_block(html) + "</table>"
    rows = block.split("<tbody>")[1].split("</tr>")[:-1]
    for row in rows:
        assert row.count("<td") == 4 and row.count("data-cx-label=") == 4
    assert "style=" not in block


def test_the_row_tint_is_replaced_by_a_four_pixel_edge_inside_the_table():
    css = _css()
    assert re.search(
        r"\.id-cx-permits tr\.row-critical > td, \.id-cx-permits tr\.row-awaiting > td \{ background-color: transparent",
        css,
    )
    assert "inset 4px 0 0 var(--sev-critical-text)" in css
    assert "inset 4px 0 0 var(--id-cx-wait-fg)" in css


CHIP_FILLS = (
    "--sev-critical-text",
    "--id-cx-wait-fg",
    "--sev-warning-text",
    "--sev-advisory-text",
    "--id-ok-text",
)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fill", CHIP_FILLS)
def test_the_solid_chip_letter_reaches_4_5_to_1(theme, fill):
    tokens = _theme_tokens(theme)
    ratio = _contrast(
        _resolve(tokens["--ac-surface"], tokens), _resolve(tokens[fill], tokens)
    )
    assert ratio >= 4.5, (theme, fill, ratio)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_wait_token_pair_reaches_4_5_to_1_and_differs_between_themes(theme):
    tokens = _theme_tokens(theme)
    assert _contrast(tokens["--id-cx-wait-fg"], tokens["--id-cx-wait-bg"]) >= 4.5, theme
    assert (
        _theme_tokens("light")["--id-cx-wait-bg"]
        != _theme_tokens("dark")["--id-cx-wait-bg"]
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_edge_fills_and_marks_reach_3_to_1(theme):
    tokens = _theme_tokens(theme)
    surface = _resolve(tokens["--ac-surface"], tokens)
    for name in ("--sev-critical-text", "--id-cx-wait-fg"):  # el filete de la fila
        assert _contrast(_resolve(tokens[name], tokens), surface) >= 3, (theme, name)
    track = _resolve(tokens["--id-cx-track"], tokens)
    for name in ("--sev-warning-text", "--sev-advisory-text", "--id-ok-text"):
        assert _contrast(_resolve(tokens[name], tokens), track) >= 3, (theme, name)
    assert _contrast(_resolve(tokens["--id-edge"], tokens), surface) >= 3


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    ("fg", "bg"),
    [
        ("--sev-critical-text", "--id-tile"),
        ("--sev-warning-text", "--id-tile"),
        ("--id-ok-text", "--id-tile"),
        ("--id-cx-wait-fg", "--id-cx-wait-bg"),
        ("--ac-text", "--id-tile"),
        ("--ac-text-secondary", "--ac-surface"),
    ],
)
def test_the_summary_pills_read(theme, fg, bg):
    tokens = _theme_tokens(theme)
    assert (
        _contrast(_resolve(tokens[fg], tokens), _resolve(tokens[bg], tokens)) >= 4.5
    ), (theme, fg, bg)
