"""LV-359 (fase 1): el hueco y el endpoint de la sección «Cumplimiento» del panel.

Lo que se vigila:
- el hueco sólo se dibuja con al menos una fuente visible y cuesta 0 consultas al panel;
- el endpoint pide sesión, filtra cada bloque por el permiso de su fuente y, sin ninguna,
  devuelve un contenedor vacío SIN nombres de registros;
- la faena de otro tenant o un UUID inválido se ignoran sin error;
- el aviso del informe DGAC se LEE del último `ReportRun` (nunca se recalcula);
- el endpoint tiene su techo de consultas, y no crece con los datos.
"""

import uuid
from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.reporting.models import ReportRun

URL = "dashboard-compliance"
HX = {"HTTP_HX_REQUEST": "true"}

# Medido (2026-10-20) sobre la operación del fixture, con el proceso caliente. Ver el aviso de
# `test_lv237_panel_query_budget.py` antes de tocarlos: se suben a propósito y se dice por qué.
# Fase 3: +2 por el historial de revisión (una cuenta de las faenas que operan y una agregación por mes
# y estado). Fase 4: +7 por la tabla de permisos: `permit_status_by_cost_center(hoy, usuario)` cuesta 6
# (sus dos consultas más las 4 de membresía de tenant que repite `scope_queryset_to_tenant`) y el detalle
# de las faenas 1 (acotado con los `tenant_ids` ya resueltos). Todas constantes: no crecen con los datos
# (`test_the_section_budget_does_not_grow_with_the_data`). Antes 20 y 23.
SECTION_QUERY_BUDGET = 29
SECTION_FILTERED_QUERY_BUDGET = 32


@pytest.fixture
def operation(db):
    today = timezone.localdate()
    soon = today + timedelta(days=10)
    centre = CostCenter.objects.create(code="CC738", name="Faena")
    other = CostCenter.objects.create(code="CC861", name="Otra")
    for index, cc in enumerate((centre, other)):
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{index}000",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=cc,
            status="active",
            insurance_expiry=soon,
        )
        operator = Operator.objects.create(
            employee_id=f"E{index}",
            full_name=f"Piloto {index}",
            cost_center=cc,
            credential_expiry=soon,
        )
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="Survey",
            location="Sector",
            valid_from=today,
            valid_until=soon,
        )
        permit.operators.add(operator)
        permit.aircraft_fleet.add(aircraft)
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="to_be_defined", status="pending"
        )
    return centre


def _get(client, **params):
    return client.get(reverse(URL), params, **HX)


# --- el hueco del panel -------------------------------------------------------------------


@pytest.mark.django_db
def test_the_panel_draws_the_slot_only_with_a_visible_source(operation):
    blind = login_as()  # sesión sin ningún permiso de lectura
    html = blind.get(reverse("dashboard")).content.decode()
    assert 'id="compliance-section"' not in html
    assert reverse(URL) not in html

    seeing = login_as("view_alert")
    html = seeing.get(reverse("dashboard")).content.decode()
    assert 'id="compliance-section"' in html
    assert 'hx-trigger="revealed"' in html
    assert 'aria-busy="true"' in html
    assert f'<noscript><p class="id-cx-note"><a href="{reverse(URL)}"' in html


@pytest.mark.django_db
def test_the_slot_carries_the_chosen_site_explicitly(operation):
    client = login_as("view_alert")
    html = client.get(
        reverse("dashboard"), {"cost_center": operation.pk}
    ).content.decode()
    assert f'hx-get="{reverse(URL)}?cost_center={operation.pk}"' in html
    # sin faena: la URL no lleva el parámetro (el fragmento no lee la sesión)
    html = client.get(reverse("dashboard"), {"cost_center": ""}).content.decode()
    assert f'hx-get="{reverse(URL)}"' in html


@pytest.mark.django_db
def test_the_slot_costs_the_panel_no_queries(operation, django_assert_num_queries):
    """El hueco se dibuja con permisos ya en memoria: `test_lv237` sigue EXACTAMENTE en 49/50."""
    from apps.dashboard.test_lv237_panel_query_budget import (
        PANEL_FILTERED_QUERY_BUDGET,
        PANEL_QUERY_BUDGET,
    )

    assert (PANEL_QUERY_BUDGET, PANEL_FILTERED_QUERY_BUDGET) == (49, 50)
    client = login_as("view_maintenancerecord")
    client.get(reverse("dashboard"))
    with django_assert_num_queries(PANEL_QUERY_BUDGET):
        response = client.get(reverse("dashboard"))
    assert 'id="compliance-section"' in response.content.decode()


# --- el endpoint ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_anonymous_visitor_is_sent_to_login(operation):
    response = Client().get(reverse(URL), **HX)
    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_htmx_gets_the_fragment_and_a_plain_request_gets_the_full_page(operation):
    client = login_as("view_alert")
    fragment = _get(client)
    assert fragment.status_code == 200
    assert b"<html" not in fragment.content
    assert 'id="compliance-section"' in fragment.content.decode()

    page = client.get(reverse(URL))
    assert page.status_code == 200
    assert b"<html" in page.content
    assert 'id="compliance-section"' in page.content.decode()
    # la página completa no se enlaza a sí misma
    assert "Open as a page" not in page.content.decode()


@pytest.mark.django_db
def test_without_any_source_the_section_is_an_empty_placeholder(operation):
    client = login_as()
    response = _get(client)
    assert response.status_code == 200
    html = response.content.decode()
    assert html.strip() == '<div id="compliance-section" hidden></div>'
    for name in ("CC738", "RPA-0000", "Piloto 0"):
        assert name not in html


@pytest.mark.django_db
def test_each_block_needs_the_permission_of_its_source(operation):
    alerts_only = _get(login_as("view_alert")).content.decode()
    assert 'data-cx-block="alerts"' in alerts_only
    for other in ("rings", "heat", "maintenance"):
        assert f'data-cx-block="{other}"' not in alerts_only

    maintenance_only = _get(login_as("view_maintenancerecord")).content.decode()
    assert 'data-cx-block="maintenance"' in maintenance_only
    assert 'data-cx-block="alerts"' not in maintenance_only

    document = _get(login_as("view_document")).content.decode()
    assert 'data-cx-block="rings"' in document
    assert 'data-cx-block="heat"' in document
    assert 'data-cx-block="alerts"' not in document


@pytest.mark.django_db
def test_the_header_says_today_and_the_site(operation):
    client = login_as("view_alert")
    today = timezone.localdate().strftime("%d-%m-%Y")
    everything = _get(client).content.decode()
    assert today in everything
    assert "CC738" not in everything
    one = _get(client, cost_center=operation.pk).content.decode()
    assert today in one
    assert "CC738" in one


# --- la faena: tenant e inválidos -----------------------------------------------------------


@pytest.mark.django_db
def test_an_invalid_or_unknown_site_is_ignored_without_error(operation):
    client = login_as("view_alert")
    for raw in ("abc", str(uuid.uuid4()), "", "1; drop"):
        response = _get(client, cost_center=raw)
        assert response.status_code == 200
        assert "CC738" not in response.content.decode()


@pytest.mark.django_db
def test_an_archived_site_is_ignored(operation):
    operation.is_active = False
    operation.save()
    response = _get(login_as("view_alert"), cost_center=operation.pk)
    assert response.status_code == 200
    assert "CC738" not in response.content.decode()


@pytest.mark.django_db
def test_a_site_of_another_tenant_is_ignored(operation):
    mine = OperationalTenant.objects.create(name="Mine", slug="mine")
    own_site = CostCenter.objects.create(code="CC900", name="Propia", tenant=mine)
    foreign = operation  # vive en el tenant por defecto, que esta persona no ve
    client = login_as("view_alert", member_of=mine)

    response = _get(client, cost_center=foreign.pk)
    assert response.status_code == 200
    assert "CC738" not in response.content.decode()

    assert "CC900" in _get(client, cost_center=own_site.pk).content.decode()


# --- el aviso del informe DGAC --------------------------------------------------------------


@pytest.mark.django_db
def test_the_report_notice_reads_the_last_run_and_never_recomputes(
    operation, monkeypatch
):
    def boom(*args, **kwargs):
        raise AssertionError("el aviso del informe no puede recalcular")

    monkeypatch.setattr("apps.reporting.builder.build", boom)
    ReportRun.objects.create(
        period=date(2026, 8, 1),
        generated_by="cron",
        status=ReportRun.STATUS_APPROVED,
        payload={"meta": {"cutoff": "2026-08-31"}},
    )
    ReportRun.objects.create(
        period=date(2026, 9, 1),
        generated_by="cron",
        status=ReportRun.STATUS_DRAFT,
        payload={"meta": {"cutoff": "2026-09-30"}},
    )
    client = login_as("view_alert", "view_reportrun")
    html = _get(client).content.decode()
    assert "30-09-2026" in html  # el último informe, con SU corte
    assert "31-08-2026" not in html
    assert "Draft" in html or "Borrador" in html
    # «hoy» y el corte son fechas distintas y las dos se dicen
    assert timezone.localdate().strftime("%d-%m-%Y") in html


@pytest.mark.django_db
def test_the_report_notice_needs_view_reportrun(operation):
    ReportRun.objects.create(
        period=date(2026, 9, 1),
        generated_by="cron",
        payload={"meta": {"cutoff": "2026-09-30"}},
    )
    html = _get(login_as("view_alert")).content.decode()
    assert "30-09-2026" not in html
    # el aviso del informe; la guía nombra a la DGAC en su texto, el aviso no debe estar
    assert 'class="id-cx-report"' not in html


# --- consultas ------------------------------------------------------------------------------


def _multiply(times):
    today = timezone.localdate()
    soon = today + timedelta(days=10)
    for index in range(2, 2 + times):
        cc = CostCenter.objects.create(code=f"CC{index:03d}", name=f"Faena {index}")
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{index}500",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=cc,
            status="active",
            insurance_expiry=soon,
        )
        Operator.objects.create(
            employee_id=f"E{index}00",
            full_name=f"Piloto {index}",
            cost_center=cc,
            credential_expiry=soon,
        )
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="to_be_defined", status="pending"
        )


ALL_SOURCES = (
    "view_alert",
    "view_document",
    "view_aircraft",
    "view_operator",
    "view_flightpermission",
    "view_maintenancerecord",
    "view_monthlycompliancereview",
    "view_reportrun",
)


@pytest.mark.django_db
def test_the_section_stays_within_its_query_budget(
    operation, django_assert_num_queries
):
    ReportRun.objects.create(period=date(2026, 9, 1), generated_by="cron")
    client = login_as(*ALL_SOURCES)
    _get(client)
    with django_assert_num_queries(SECTION_QUERY_BUDGET):
        assert _get(client).status_code == 200
    _get(client, cost_center=operation.pk)
    with django_assert_num_queries(SECTION_FILTERED_QUERY_BUDGET):
        assert _get(client, cost_center=operation.pk).status_code == 200


@pytest.mark.django_db
def test_the_section_budget_does_not_grow_with_the_data(
    operation, django_assert_num_queries
):
    client = login_as(*ALL_SOURCES)
    _get(client)
    _multiply(20)
    with django_assert_num_queries(SECTION_QUERY_BUDGET):
        assert _get(client).status_code == 200
