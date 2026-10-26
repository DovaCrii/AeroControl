"""LV-376 (fase 3): la guía v4 de «Cumplimiento».

Se fija: la leyenda de estados es una tabla (estado con su chip sólido, qué significa, qué hacer y un enlace SOLO si
la persona puede abrir esa pantalla: ningún enlace de la guía lleva a un 403); los números de la leyenda salen de las
constantes de los KPI; las dos escalas se explican SIN inventar el motivo de negocio (queda «la escala del informe» y
la fila pendiente de la persona); «a hoy» se dice frente al corte del informe, que sólo se nombra con
`view_reportrun`; y el catálogo ya no guarda la frase inventada.
"""

# ruff: noqa: F811  (los fixtures se importan de otros módulos y se usan como argumentos)
import re
from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone, translation

from apps.compliance.kpis import PERMIT_CRITICAL_DAYS, PERMIT_WARNING_DAYS
from apps.core.test_lv315_identity_foundation import ROOT
from apps.core.testing import login_as as _login_as
from apps.dashboard.compliance_permits import KINDS
from apps.dashboard.compliance_section import guide_states
from apps.dashboard.test_lv359_compliance_permits import (  # noqa: F401
    VIEW,
    sites,
)
from apps.reporting.models import ReportRun

URL = "dashboard-compliance"
ADD = "add_flightpermission"


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


def login_as(*codenames, **kwargs):
    client = _login_as(*codenames, **kwargs)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


def _guide(client, **headers):
    html = client.get(reverse(URL), **headers).content.decode()
    return html[html.index('id="cx-guide"') :]


def _legend(guide):
    return guide.split("data-cx-legend")[1].split("</table>")[0]


@pytest.mark.django_db
def test_the_legend_is_a_table_with_one_row_per_state_in_urgency_order(sites):
    legend = _legend(_guide(login_as(VIEW)))
    head = legend.split("<thead>")[1].split("</thead>")[0]
    assert head.count('scope="col"') == 4
    rows = re.findall(r'<tr data-cx-state="(\w+)">', legend)
    # el orden de la leyenda es el del diseño: sin permiso, esperando, empieza, renovar ya, pronto, al día
    assert rows == ["none", "awaiting", "not_started", "renew_now", "renew_soon", "ok"]
    assert sorted(rows) == sorted(KINDS)
    # el chip es el sólido de la tabla de permisos: símbolo + palabra
    for kind, symbol, tone in (
        ("none", "✕", "none"),
        ("awaiting", "◐", "wait"),
        ("renew_now", "▲", "warning"),
        ("renew_soon", "◆", "advisory"),
        ("ok", "●", "ok"),
    ):
        row = legend.split(f'data-cx-state="{kind}"')[1].split("</tr>")[0]
        assert f'<span class="id-cx-state id-cx-state--{tone}">' in row
        assert f'<span aria-hidden="true">{symbol}</span>' in row
        assert '<th scope="row">' in row


@pytest.mark.django_db
def test_the_numbers_of_the_legend_are_the_kpi_constants(sites):
    client = login_as(VIEW)
    states = {s["kind"]: s for s in guide_states(client.user)}
    assert str(PERMIT_CRITICAL_DAYS) in states["renew_now"]["meaning"]
    assert str(PERMIT_CRITICAL_DAYS + 1) in states["renew_soon"]["meaning"]
    assert str(PERMIT_WARNING_DAYS) in states["renew_soon"]["meaning"]
    assert str(PERMIT_WARNING_DAYS) in states["ok"]["meaning"]
    # la frase de las dos escalas la escribe una persona: si los umbrales se mueven, esta prueba avisa
    assert f"{PERMIT_CRITICAL_DAYS} and {PERMIT_WARNING_DAYS} days" in _guide(client)


@pytest.mark.django_db
def test_there_is_no_legend_without_the_permits_table(sites):
    guide = _guide(login_as("view_alert"))
    assert "data-cx-legend" not in guide and "Status of each site" not in guide
    assert "Symbols and colors" in guide  # el resto de la guía sigue


@pytest.mark.django_db
def test_the_legend_links_exist_only_if_the_person_can_open_them(sites):
    only_view = _legend(_guide(login_as(VIEW)))
    assert reverse("permission-create") not in only_view
    assert (
        only_view.count(f'href="{reverse("permission-list")}"') == 2
    )  # esperando y renovar ya
    with_add = _legend(_guide(login_as(VIEW, ADD)))
    none_row = with_add.split('data-cx-state="none"')[1].split("</tr>")[0]
    assert f'href="{reverse("permission-create")}"' in none_row
    # sin ver permisos no hay leyenda; con sólo `add_` la tabla ni existe (la sección exige ver)
    assert "data-cx-legend" not in _guide(login_as(ADD, "view_alert"))
    # los estados que no piden nada no llevan enlace
    for kind in ("not_started", "renew_soon", "ok"):
        row = with_add.split(f'data-cx-state="{kind}"')[1].split("</tr>")[0]
        assert "<a " not in row


@pytest.mark.django_db
def test_no_link_in_the_guide_leads_to_a_403(sites):
    client = login_as(
        VIEW, ADD, "view_alert", "view_monthlycompliancereview", "view_reportrun"
    )
    guide = _guide(client)
    hrefs = {h.replace("&amp;", "&") for h in re.findall(r'href="([^"#][^"]*)"', guide)}
    assert hrefs
    for href in sorted(hrefs):
        status = client.get(href).status_code
        assert status in (200, 302), (href, status)
    # una persona con menos permisos no recibe enlaces a pantallas que no abre
    narrow_client = login_as(VIEW)
    for href in re.findall(r'href="([^"#][^"]*)"', _guide(narrow_client)):
        assert narrow_client.get(href.replace("&amp;", "&")).status_code in (200, 302)


@pytest.mark.django_db
def test_the_business_reason_of_the_scales_is_not_invented(sites):
    guide = _guide(login_as(VIEW))
    assert "which takes longer" not in guide and "involves a request" not in guide
    assert "Flight permits follow the scale of the report" in guide
    # queda marcado como pendiente de la persona, en la plantilla y en el tablero
    template = (ROOT / "templates/dashboard/_compliance_guide.html").read_text(
        encoding="utf-8"
    )
    assert "PENDIENTE (de la persona" in template and "NO está escrito" in template
    plan = (ROOT / "MASTER_PLAN.md").read_text(encoding="utf-8")
    row = next(line for line in plan.splitlines() if line.startswith("| LV-376 |"))
    assert "30 y 60" in row and "Pendiente de la persona" in row


def test_the_invented_reason_is_gone_from_the_spanish_catalog_too():
    po = (ROOT / "locale/es/LC_MESSAGES/django.po").read_text(encoding="utf-8")
    assert "renovar uno implica una solicitud a la DGAC" not in po
    assert "renewing one involves a request to the DGAC" not in po.replace('"\n"', "")


@pytest.mark.django_db
def test_today_is_said_next_to_the_report_cut_off_and_only_with_the_permission(sites):
    ReportRun.objects.create(
        period=date(2026, 8, 1),
        generated_by="cron",
        status=ReportRun.STATUS_APPROVED,
        payload={"meta": {"cutoff": "2026-08-31"}},
    )
    today = timezone.localdate().strftime("%d-%m-%Y")
    seeing = _guide(login_as(VIEW, "view_reportrun"))
    assert f"Everything above is as of today, {today}." in seeing
    assert "snapshot at its own cut-off date (31-08-2026)" in seeing
    blind = _guide(login_as(VIEW))
    assert f"as of today, {today}" in blind
    assert "31-08-2026" not in blind and "cut-off date, so its figures" in blind


@pytest.mark.django_db
def test_the_guide_stays_closed_and_has_no_aria_expanded(sites):
    html = login_as(VIEW).get(reverse(URL)).content.decode()
    assert '<details class="id-cx-guide" id="cx-guide">' in html
    # sólo la guía: la paleta de órdenes del armazón sí declara `aria-expanded`
    guide = _guide(login_as(VIEW, "view_alert")).split("</details>")[0]
    assert "aria-expanded" not in guide


@pytest.mark.django_db
def test_the_legend_speaks_spanish_without_voseo(sites):
    client = login_as(VIEW)
    html = client.get(reverse(URL), headers={"Accept-Language": "es"}).content.decode()
    guide = html[html.index('id="cx-guide"') :]
    for text in (
        "Estado de cada faena",
        "Sin permiso vigente: la faena no puede volar.",
        "Hacer seguimiento con la DGAC",
        "Preparar la renovación hoy",
        "Los permisos de vuelo siguen la escala del informe",
    ):
        assert text in guide, text
    assert not re.search(r"\b(podés|escribí|revisá|volvé|emití|hacé)\b", guide)


def test_the_legend_css_wraps_on_a_phone():
    css = (ROOT / "static/css/compliance.css").read_text(encoding="utf-8")
    assert ".id-cx-gwrap { overflow-x: auto; }" in css
    assert not re.search(r"\banimation(-[a-z]+)?\s*:|transition\s*:", css)
    assert len(css.encode()) < 16 * 1024
