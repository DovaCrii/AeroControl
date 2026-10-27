"""LV-359 (fase 3): la guía de lectura y el historial de revisión de «Cumplimiento».

Lo que se vigila:
- el historial sólo existe con `view_monthlycompliancereview`; son seis meses CERRADOS y cada uno
  enlaza a `monthly-review?month=`; símbolo + texto además del color;
- acotado por tenant (otro tenant no suma, ni a las revisiones ni a las faenas «sin revisar»);
- cuesta un número fijo de consultas, no crece con los datos;
- la guía es un `<details>` cerrado, trae la leyenda y las dos escalas de umbrales, y cada enlace
  existe sólo si la persona puede abrir esa pantalla.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext

from apps.compliance.models import MonthlyComplianceReview
from apps.core.models import OperationalTenant
from apps.core.tenancy import visible_tenant_ids
from apps.core.testing import login_as
from apps.dashboard.compliance_data import (
    closed_months,
    review_history,
    review_status_label,
)
from apps.dashboard.compliance_section import guide_steps
from apps.registry.models import CostCenter

URL = "dashboard-compliance"
HX = {"HTTP_HX_REQUEST": "true"}


def _get(client, **params):
    return client.get(reverse(URL), params, **HX).content.decode()


def _history(html):
    start = html.index('id="cx-history"')
    return html[start:].split("</table>")[0]


def _guide(html):
    return html[html.index('id="cx-guide"') :]


@pytest.fixture
def sites(db):
    one = CostCenter.objects.create(code="CC738", name="Faena uno")
    two = CostCenter.objects.create(code="CC861", name="Faena dos")
    return one, two


def _review(site, month, status):
    return MonthlyComplianceReview.objects.create(
        cost_center=site, period=month, status=status
    )


def _last_closed():
    return closed_months(timezone.localdate())[0]


# --- el historial -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_history_needs_view_monthlycompliancereview(sites):
    seeing = _get(login_as("view_monthlycompliancereview"))
    assert 'data-cx-block="history"' in seeing
    other = _get(login_as("view_alert"))
    assert 'data-cx-block="history"' not in other
    assert 'id="cx-history"' not in other


@pytest.mark.django_db
def test_the_history_data_is_never_read_without_the_permission(sites):
    """Segunda puerta: el dato mismo (no sólo el bloque) se niega sin el permiso."""
    user = login_as("view_alert").user
    assert review_history(user, None, timezone.localdate(), None) is None


@pytest.mark.django_db
def test_only_the_review_permission_is_enough_to_open_the_section(sites):
    """Con sólo esa fuente la sección no queda oculta: `can_see_compliance` y `blocks_for` coinciden."""
    html = _get(login_as("view_monthlycompliancereview"))
    assert html.strip() != '<div id="compliance-section" hidden></div>'
    assert 'id="cx-history"' in html


@pytest.mark.django_db
def test_six_closed_months_each_linking_to_its_close(sites):
    today = timezone.localdate()
    html = _history(_get(login_as("view_monthlycompliancereview")))
    months = closed_months(today)
    assert len(months) == 6
    assert today.replace(day=1) not in months  # el mes en curso no es un cierre
    assert html.count("<tr data-cx-month=") == 6
    for month in months:
        stamp = month.strftime("%Y-%m")
        assert f'data-cx-month="{stamp}"' in html
        assert f'href="{reverse("monthly-review")}?month={stamp}"' in html


@pytest.mark.django_db
def test_each_state_carries_symbol_and_text_and_the_count(sites):
    one, two = sites
    month = _last_closed()
    _review(one, month, MonthlyComplianceReview.STATUS_NON_COMPLIANT)
    _review(two, month, MonthlyComplianceReview.STATUS_COMPLETED)
    html = _history(_get(login_as("view_monthlycompliancereview")))
    row = html.split(f'data-cx-month="{month:%Y-%m}"')[1].split("</tr>")[0]
    assert "✕" in row and review_status_label("non_compliant") in row
    assert "●" in row and review_status_label("completed") in row
    assert "id-chip--critical" in row and "id-chip--ok" in row
    # las dos faenas ya tienen revisión: nadie queda «sin revisar» ese mes
    assert "○" not in row
    # un mes sin ninguna revisión dice que las dos faenas siguen sin revisar
    older = closed_months(timezone.localdate())[1]
    row = html.split(f'data-cx-month="{older:%Y-%m}"')[1].split("</tr>")[0]
    assert "○" in row and f"<b>2</b> {review_status_label('unreviewed')}" in row


@pytest.mark.django_db
def test_a_pending_review_is_not_reviewed_nor_compliant(sites):
    one, _two = sites
    month = _last_closed()
    _review(one, month, MonthlyComplianceReview.STATUS_PENDING)
    html = _history(_get(login_as("view_monthlycompliancereview")))
    row = html.split(f'data-cx-month="{month:%Y-%m}"')[1].split("</tr>")[0]
    assert "▲" in row and review_status_label("pending") in row
    assert f"<b>1</b> {review_status_label('unreviewed')}" in row  # la otra faena
    assert "id-chip--ok" not in row


@pytest.mark.django_db
def test_a_review_older_than_six_months_is_not_in_the_history(sites):
    one, _two = sites
    old = closed_months(timezone.localdate(), 8)[-1]
    _review(one, old, MonthlyComplianceReview.STATUS_NON_COMPLIANT)
    assert "✕" not in _history(_get(login_as("view_monthlycompliancereview")))


@pytest.mark.django_db
def test_the_chosen_site_narrows_the_history(sites):
    one, two = sites
    month = _last_closed()
    _review(two, month, MonthlyComplianceReview.STATUS_NON_COMPLIANT)
    client = login_as("view_monthlycompliancereview")
    assert "✕" in _history(_get(client))
    assert "✕" not in _history(_get(client, cost_center=one.pk))


@pytest.mark.django_db
def test_another_tenants_reviews_and_sites_do_not_count(sites):
    foreign, _two = sites  # viven en el tenant por defecto, que esta persona no ve
    mine = OperationalTenant.objects.create(name="Mine", slug="mine")
    own = CostCenter.objects.create(code="CC900", name="Propia", tenant=mine)
    month = _last_closed()
    _review(foreign, month, MonthlyComplianceReview.STATUS_NON_COMPLIANT)
    _review(own, month, MonthlyComplianceReview.STATUS_COMPLETED)
    client = login_as("view_monthlycompliancereview", member_of=mine)
    html = _history(_get(client))
    row = html.split(f'data-cx-month="{month:%Y-%m}"')[1].split("</tr>")[0]
    assert "✕" not in row and review_status_label("non_compliant") not in row
    assert "●" in row
    # sólo una faena visible: un mes sin revisión dice «1 sin revisar», no «3»
    older = closed_months(timezone.localdate())[1]
    row = html.split(f'data-cx-month="{older:%Y-%m}"')[1].split("</tr>")[0]
    assert f"<b>1</b> {review_status_label('unreviewed')}" in row


@pytest.mark.django_db
def test_a_site_that_does_not_fly_is_not_pending_review(sites):
    one, two = sites
    two.operates_flights = False
    two.save()
    html = _history(_get(login_as("view_monthlycompliancereview")))
    older = closed_months(timezone.localdate())[1]
    row = html.split(f'data-cx-month="{older:%Y-%m}"')[1].split("</tr>")[0]
    assert f"<b>1</b> {review_status_label('unreviewed')}" in row


@pytest.mark.django_db
def test_without_any_flying_site_the_history_says_so(db):
    html = _get(login_as("view_monthlycompliancereview"))
    assert 'id="cx-history"' in html
    assert '<table class="id-cx-hist"' not in html


@pytest.mark.django_db
def test_the_history_costs_a_fixed_number_of_queries(sites):
    one, two = sites
    user = login_as("view_monthlycompliancereview").user
    today = timezone.localdate()
    tenants = visible_tenant_ids(user)
    user.has_perm("compliance.view_monthlycompliancereview")  # calienta permisos

    def count():
        with CaptureQueriesContext(connection) as queries:
            review_history(user, None, today, tenants)
        return len(queries)

    before = count()
    for month in closed_months(today):
        _review(one, month, MonthlyComplianceReview.STATUS_COMPLETED)
        _review(two, month, MonthlyComplianceReview.STATUS_PENDING)
    for index in range(5):
        extra = CostCenter.objects.create(code=f"CC9{index}0", name=f"Extra {index}")
        for month in closed_months(today):
            _review(extra, month, MonthlyComplianceReview.STATUS_NON_COMPLIANT)
    assert count() == before
    assert before <= 2


# --- la guía ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_guide_is_a_closed_details_with_the_legend_and_both_scales(sites):
    html = _get(login_as("view_alert"))
    assert '<details class="id-cx-guide" id="cx-guide">' in html  # sin `open`
    guide = _guide(html)
    for symbol in ("✕", "▲", "◆", "●", "○"):
        assert symbol in guide
    # las dos escalas y «hoy» frente al corte del informe: se comparan contra el catálogo, no contra
    # un texto tecleado, así que sirven en cualquier idioma activo (LV-376: sin motivo de negocio inventado)
    today = timezone.localdate().strftime("%d-%m-%Y")
    for text in (
        gettext(
            "Flight permits follow the scale of the report: 30 and 60 days. Documents and alerts are graded at 7, 15 and 30 days."
        ),
        gettext("Everything above is as of today, %(date)s.") % {"date": today},
        gettext(
            "The DGAC monthly report is a snapshot at its own cut-off date, so its figures can differ from these without either being wrong."
        ),
    ):
        assert escape(text) in guide


@pytest.mark.django_db
def test_without_any_source_there_is_no_guide(sites):
    html = _get(login_as())
    assert "cx-guide" not in html


@pytest.mark.django_db
def test_the_guide_only_links_to_screens_the_person_can_open(sites):
    only_alerts = _guide(_get(login_as("view_alert")))
    assert f'href="{reverse("alert-list")}"' in only_alerts
    assert f'href="{reverse("dashboard")}#panel-attention"' in only_alerts
    assert reverse("permission-list") not in only_alerts
    assert reverse("monthly-review") not in only_alerts
    assert reverse("monthly-report") not in only_alerts
    # los cinco pasos se dicen aunque algunos no lleven enlace
    assert only_alerts.count("data-cx-step=") == 5

    everything = _guide(
        _get(
            login_as(
                "view_alert",
                "view_flightpermission",
                "view_monthlycompliancereview",
                "view_reportrun",
            )
        )
    )
    for name in ("alert-list", "permission-list", "monthly-review", "monthly-report"):
        assert f'href="{reverse(name)}"' in everything


@pytest.mark.django_db
def test_the_permits_step_carries_the_chosen_site(sites):
    one, _two = sites
    user = login_as("view_flightpermission").user
    steps = {step["n"]: step for step in guide_steps(user, one)}
    assert steps[3]["url"] == f"{reverse('permission-list')}?cost_center={one.pk}"
    steps = {step["n"]: step for step in guide_steps(user, None)}
    assert steps[3]["url"] == reverse("permission-list")
