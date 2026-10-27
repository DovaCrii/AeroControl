"""LV-372: el panel y lo que lo alimenta acotan por empresa (F-08).

`dashboard()` armaba todas sus cifras sobre `Aircraft.objects`, `FlightPermission.objects`,
`upcoming_expirations`... sin mirar el tenant de quien abría la pantalla, y la faena elegida
tampoco se acotaba (el docstring de `resolve_cost_center` lo dejaba anotado como riesgo). Hoy
hay una sola empresa en producción, así que no se explota; la regla del proyecto es que
**toda** vista acote, no sólo por permiso de modelo.

Dos empresas, la B con el **doble** de todo que la A: si una cifra de la A suma algo de la B,
el número ya no es el esperado. Cada fila de `TestPanelFigures` fallaba antes del acotado.
Datos ficticios.
"""

from datetime import time, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.expirations import upcoming_expirations
from apps.compliance.models import (
    Alert,
    AlertRule,
    Document,
    DocumentType,
    MonthlyComplianceReview,
)
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission, FlightRecord, FlightRequest
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
SOON = TODAY + timedelta(days=10)

PANEL_PERMS = (
    "view_aircraft",
    "view_operator",
    "view_qualification",
    "view_knowledgeassessment",
    "view_flightpermission",
    "view_flightrequest",
    "view_flightrecord",
    "view_maintenancerecord",
    "view_alert",
    "view_document",
    "view_monthlycompliancereview",
    "view_costcenter",
)


def _build(tenant, key, copies):
    """`copies` de cada cosa en la empresa `tenant`; devuelve su faena y lo creado."""
    center = CostCenter.objects.create(
        code=f"CC-{key.upper()}",
        name=f"Faena {key}",
        tenant=tenant,
        operates_flights=True,
    )
    rule = AlertRule.objects.create(
        name=f"Regla {key}",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
        tenant=tenant,
    )
    doc_type = DocumentType.objects.get_or_create(code="t372", defaults={"name": "T"})[
        0
    ]
    made = {"aircraft": [], "operators": [], "permits": [], "documents": []}
    for index in range(copies):
        tag = f"{key.upper()}{index}"
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{tag}",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=center,
            tenant=tenant,
            status="active",
            insurance_expiry=SOON,
        )
        operator = Operator.objects.create(
            employee_id=f"E-{tag}",
            full_name=f"Piloto {tag}",
            cost_center=center,
            tenant=tenant,
            credential_expiry=SOON,
        )
        permit = FlightPermission.objects.create(
            internal_folio=f"JEJ-2026-{tag}",
            cost_center=center,
            purpose="patrol",
            status=FlightPermission.STATUS_APPROVED,
            valid_from=TODAY,
            valid_until=SOON,
            location="Sitio ficticio",
            area_type="unpopulated",
        )
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="to_be_defined", status="pending"
        )
        FlightRequest.objects.create(
            title=f"Solicitud {tag}",
            cost_center=center,
            center_lat=-31.7,
            center_lon=-70.6,
            status=FlightRequest.STATUS_FILED,
            filed_on=TODAY - timedelta(days=3),
        )
        FlightRecord.objects.create(
            permission=permit,
            actual_date=TODAY,
            departure_time=time(9, 0),
            arrival_time=time(10, 0),
            pilot=operator,
            aircraft=aircraft,
        )
        document = Document.objects.create(
            title=f"Documento {tag}",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY - timedelta(days=1),
            expiry_date=SOON,
            is_current_version=True,
            tenant=tenant,
        )
        Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            message=f"Alerta {tag}",
            watched_value=SOON.isoformat(),
        )
        made["aircraft"].append(aircraft)
        made["operators"].append(operator)
        made["permits"].append(permit)
        made["documents"].append(document)
    MonthlyComplianceReview.objects.create(
        cost_center=center, period=TODAY.replace(day=1)
    )
    made["center"] = center
    return made


@pytest.fixture
def world(db):
    alfa = OperationalTenant.objects.create(name="Alfa", slug="alfa")
    beta = OperationalTenant.objects.create(name="Beta", slug="beta")
    return {
        "alfa": alfa,
        "beta": beta,
        "a": _build(alfa, "a", 1),
        "b": _build(beta, "b", 2),
    }


def _client(world, tenant="alfa"):
    return login_as(*PANEL_PERMS, member_of=world[tenant])


def _readiness(response):
    return {row["key"]: row for row in response.context["readiness"]}


@pytest.mark.django_db
class TestPanelFigures:
    """Cada cifra del panel de la A cuenta lo de la A y nada de la B."""

    def test_summary_counts(self, world):
        context = _client(world).get(reverse("dashboard")).context
        assert context["aircraft_count"] == 1
        assert context["operator_count"] == 1
        assert context["alert_count"] == 1
        assert context["incomplete_maintenance_count"] == 1
        assert context["awaiting_count"] == 1
        assert context["flights_today"] == 1
        assert context["permits_in_force"] == 1

    def test_readiness_strip(self, world):
        rows = _readiness(_client(world).get(reverse("dashboard")))
        assert rows["fleet"]["total"] == 1
        assert rows["insurance"]["total"] == 1
        assert rows["credentials"]["total"] == 1
        assert rows["permits"]["total"] == 1 and rows["permits"]["count"] == 1

    def test_cost_centre_picker_lists_only_own_sites(self, world):
        context = _client(world).get(reverse("dashboard")).context
        assert list(context["cost_centers"]) == [world["a"]["center"]]

    def test_expirations_list_and_counters(self, world):
        context = _client(world).get(reverse("dashboard")).context
        labels = {row["label"] for row in context["expirations"]}
        # Aeronave, credencial, permiso y documento de la A: cuatro filas, ninguna de la B.
        assert context["expirations_total"] == 4
        assert not any("B0" in label or "B1" in label for label in labels)

    def test_upcoming_maintenance_awaiting_requests_and_flights(self, world):
        context = _client(world).get(reverse("dashboard")).context
        assert [r.aircraft for r in context["upcoming_maintenance"]] == world["a"][
            "aircraft"
        ]
        assert [r.title for r in context["awaiting_requests"]] == ["Solicitud A0"]
        assert sum(m["count"] for m in context["chart_data"]["monthly_flights"]) == 1

    def test_monthly_review_card(self, world):
        context = _client(world).get(reverse("dashboard")).context
        assert context["monthly_records"]["total"] == 1

    def test_the_html_never_names_the_other_tenant(self, world):
        content = _client(world).get(reverse("dashboard")).content.decode()
        for needle in ("RPA-B", "Piloto B", "JEJ-2026-B", "Faena b", "CC-B"):
            assert needle not in content, needle

    def test_onboarding_flags_are_per_tenant(self, world):
        """Otra empresa con documentos y reglas no «completa» la puesta en marcha de ésta."""
        Document.objects.filter(tenant=world["alfa"]).update(is_active=False)
        AlertRule.objects.filter(tenant=world["alfa"]).update(is_active=False)
        setup = _client(world).get(reverse("dashboard")).context["compliance_setup"]
        assert setup["documents"] is False
        assert setup["rules"] is False

    def test_superuser_sees_both_tenants(self, world, admin_client):
        context = admin_client.get(reverse("dashboard")).context
        assert context["aircraft_count"] == 3
        assert context["alert_count"] == 3


@pytest.mark.django_db
class TestChosenCostCentre:
    def test_a_foreign_cost_centre_is_not_selected(self, world):
        client = _client(world)
        response = client.get(
            reverse("dashboard"), {"cost_center": world["b"]["center"].pk}
        )
        assert response.status_code == 200
        assert response.context["selected_cost_center"] is None
        assert response.context["aircraft_count"] == 1
        assert "dashboard_cost_center" not in client.session

    def test_a_remembered_foreign_cost_centre_is_dropped(self, world):
        client = _client(world)
        session = client.session
        session["dashboard_cost_center"] = str(world["b"]["center"].pk)
        session.save()
        response = client.get(reverse("dashboard"))
        assert response.context["selected_cost_center"] is None
        assert "dashboard_cost_center" not in client.session

    def test_the_own_cost_centre_is_still_selected(self, world):
        response = _client(world).get(
            reverse("dashboard"), {"cost_center": world["a"]["center"].pk}
        )
        assert response.context["selected_cost_center"] == world["a"]["center"]


@pytest.mark.django_db
class TestExpirationsFunction:
    def test_upcoming_expirations_with_a_user_is_tenant_scoped(self, world):
        user = _client(world).user
        items = upcoming_expirations(TODAY, SOON, None, user)
        assert len(items) == 4
        assert not any("B0" in i["label"] or "B1" in i["label"] for i in items)

    def test_without_a_user_it_still_sees_everything(self, world):
        """El digest y los informes internos preguntan sin sesión: no se acotan."""
        assert len(upcoming_expirations(TODAY, SOON)) == 4 + 8

    def test_a_cost_centre_of_another_tenant_gives_nothing(self, world):
        user = _client(world).user
        assert upcoming_expirations(TODAY, SOON, world["b"]["center"], user) == []

    def test_superuser_sees_both(self, world, admin_client):
        from django.contrib.auth.models import User

        root = User.objects.get(is_superuser=True)
        assert len(upcoming_expirations(TODAY, SOON, None, root)) == 12


@pytest.mark.django_db
class TestComplianceSectionAndStrip:
    """Guardianes: la sección «Cumplimiento» y la franja ya acotaban."""

    def test_the_section_with_a_foreign_cost_centre_ignores_it(self, world):
        response = _client(world).get(
            reverse("dashboard-compliance"),
            {"cost_center": world["b"]["center"].pk},
        )
        assert response.status_code == 200
        assert response.context["cx_cost_center"] is None

    def test_the_section_counts_only_own_tenant(self, world):
        response = _client(world).get(reverse("dashboard-compliance"))
        content = response.content.decode()
        for needle in ("RPA-B", "Piloto B", "JEJ-2026-B", "Faena b", "CC-B"):
            assert needle not in content, needle
        rows = response.context["cx_permits"]["rows"]
        assert [row["cost_center"] for row in rows] == [world["a"]["center"]]
        categories = {r["key"]: r["total"] for r in response.context["cx_rings"]}
        # Aeronave (1), operador (1), permiso (1), documento (1) y mantenimiento (1): sólo de la A.
        assert sum(categories.values()) <= 5

    def test_the_alert_ages_only_count_own_tenant(self, world):
        response = _client(world).get(reverse("dashboard-compliance"))
        ages = response.context["cx_alerts"]
        assert ages is not None and ages["total"] == 1


@pytest.mark.django_db
class TestAlertBadge:
    """El contador de la barra lateral cuenta las alertas de **todas** las empresas."""

    def test_the_context_processor_counts_only_own_tenant(self, world):
        response = _client(world).get(reverse("dashboard"))
        assert response.context["unresolved_alert_count"] == 1

    def test_the_htmx_partial_counts_only_own_tenant(self, world):
        response = _client(world).get(reverse("alert-count"))
        assert response.context["unresolved_alert_count"] == 1

    def test_superuser_counts_every_tenant(self, world, admin_client):
        response = admin_client.get(reverse("alert-count"))
        assert response.context["unresolved_alert_count"] == 3

    def test_the_administration_situation_counts_only_own_tenant(self, world):
        """Fuga: «Situación» del centro de administración contaba alertas, documentos y reglas de todos."""
        client = login_as(
            "view_alert",
            "view_document",
            "view_alertrule",
            member_of=world["alfa"],
        )
        response = client.get(reverse("administration"))
        values = [m["value"] for m in response.context["situation"]["metrics"][:3]]
        # Alertas sin resolver, documentos por vencer y reglas activas: una de cada una en la A.
        assert values == [1, 1, 1]
