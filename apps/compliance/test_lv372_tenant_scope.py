"""LV-372: los consumidores de «qué vence» y de las alertas acotan por empresa (F-08).

`upcoming_expirations` alimenta el panel, la sección «Cumplimiento» y (sin sesión) el digest;
las alertas se leen en la bandeja y se actúan con cuatro botones. Esta prueba recorre cada uno
con dos empresas y un usuario por empresa con los permisos del rol. Las pruebas de
`TestAlertTray` fallaban antes del acotado; el calendario y el digest ya estaban acotados y
quedan como guardián. Datos ficticios.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.digest import build_digest
from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
SOON = TODAY + timedelta(days=10)


@pytest.fixture
def world(db):
    data = {}
    doc_type = DocumentType.objects.create(code="t372c", name="T")
    for key in ("a", "b"):
        tenant = OperationalTenant.objects.create(name=f"E {key}", slug=f"e-{key}")
        center = CostCenter.objects.create(
            code=f"CC-{key.upper()}", name=f"Faena {key}", tenant=tenant
        )
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{key.upper()}1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=center,
            tenant=tenant,
            status="active",
            insurance_expiry=SOON,
        )
        operator = Operator.objects.create(
            employee_id=f"E-{key}",
            full_name=f"Piloto {key.upper()}",
            cost_center=center,
            tenant=tenant,
            credential_expiry=SOON,
        )
        permit = FlightPermission.objects.create(
            internal_folio=f"JEJ-2026-{key.upper()}",
            cost_center=center,
            purpose="patrol",
            status=FlightPermission.STATUS_APPROVED,
            valid_from=TODAY,
            valid_until=SOON,
            location="Sitio ficticio",
            area_type="unpopulated",
        )
        document = Document.objects.create(
            title=f"Documento {key.upper()}",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY - timedelta(days=1),
            expiry_date=SOON,
            is_current_version=True,
            tenant=tenant,
        )
        rule = AlertRule.objects.create(
            name=f"Regla {key}",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
            tenant=tenant,
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            message=f"Alerta {key.upper()}",
            watched_value=SOON.isoformat(),
        )
        data[key] = {
            "tenant": tenant,
            "center": center,
            "aircraft": aircraft,
            "operator": operator,
            "permit": permit,
            "document": document,
            "rule": rule,
            "alert": alert,
        }
    return data


def _client(world, *codenames, tenant="a"):
    return login_as(*codenames, member_of=world[tenant]["tenant"])


@pytest.mark.django_db
class TestAlertTray:
    def test_the_list_shows_only_own_tenant_alerts(self, world):
        """Fuga: la bandeja traía las alertas de todas las empresas."""
        response = _client(world, "view_alert").get(reverse("alert-list"))
        alerts = list(response.context["object_list"])
        assert world["a"]["alert"] in alerts
        assert world["b"]["alert"] not in alerts

    def test_the_csv_export_does_not_leak(self, world):
        response = _client(world, "view_alert").get(
            reverse("alert-list"), {"export": "csv", "is_resolved": "all"}
        )
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        assert "Alerta A" in body and "Alerta B" not in body

    def test_a_foreign_cost_centre_filter_is_a_no_op_not_a_peek(self, world):
        client = _client(world, "view_alert", "view_costcenter")
        response = client.get(
            reverse("alert-list"), {"cost_center": world["b"]["center"].pk}
        )
        assert response.status_code == 200
        assert response.context["selected_cost_center"] is None
        assert world["b"]["alert"] not in list(response.context["object_list"])

    def test_resolve_form_of_another_tenant_is_404(self, world):
        """Fuga: el modal de resolver abría cualquier alerta por su pk."""
        client = _client(world, "change_alert")
        assert (
            client.get(
                reverse("alert-resolve", args=[world["b"]["alert"].pk])
            ).status_code
            == 404
        )

    def test_resolving_an_alert_of_another_tenant_is_404_and_changes_nothing(
        self, world
    ):
        alert = world["b"]["alert"]
        response = _client(world, "change_alert").post(
            reverse("alert-resolve", args=[alert.pk]), {"reason": "Se renueva"}
        )
        assert response.status_code == 404
        alert.refresh_from_db()
        assert alert.is_resolved is False

    def test_resolving_an_own_alert_still_works(self, world):
        alert = world["a"]["alert"]
        response = _client(world, "change_alert").post(
            reverse("alert-resolve", args=[alert.pk]), {"reason": "Se renueva"}
        )
        assert response.status_code == 302
        alert.refresh_from_db()
        assert alert.is_resolved is True

    def test_reopening_an_alert_of_another_tenant_is_404(self, world):
        alert = world["b"]["alert"]
        alert.resolve(reason="ok")
        response = _client(world, "change_alert").post(
            reverse("alert-reopen", args=[alert.pk])
        )
        assert response.status_code == 404
        alert.refresh_from_db()
        assert alert.is_resolved is True

    def test_verifying_an_alert_of_another_tenant_is_404(self, world):
        alert = world["b"]["alert"]
        alert.resolve(reason="ok")
        response = _client(world, "change_alert").post(
            reverse("alert-verify-effectiveness", args=[alert.pk]), {"note": "x"}
        )
        assert response.status_code == 404

    def test_creating_a_task_from_an_alert_of_another_tenant_is_404(self, world):
        alert = world["b"]["alert"]
        response = _client(world, "add_kanbantask").post(
            reverse("alert-create-task", args=[alert.pk])
        )
        assert response.status_code == 404

    def test_superuser_sees_every_tenant(self, world, admin_client):
        response = admin_client.get(reverse("alert-list"))
        alerts = list(response.context["object_list"])
        assert world["a"]["alert"] in alerts and world["b"]["alert"] in alerts


@pytest.mark.django_db
class TestCalendarAndDigestGuardians:
    """Ya acotados antes de esta fila: quedan como guardián."""

    def test_the_calendar_feed_only_has_own_tenant_events(self, world):
        client = _client(
            world,
            "view_flightpermission",
            "view_flightrecord",
            "view_assignment",
            "view_maintenancerecord",
            "view_document",
            "view_qualification",
            "view_operator",
            "view_aircraft",
        )
        response = client.get(
            reverse("calendar-events"),
            {
                "start": (TODAY - timedelta(days=5)).isoformat(),
                "end": (TODAY + timedelta(days=60)).isoformat(),
            },
        )
        titles = " ".join(str(event["title"]) for event in response.json())
        assert titles
        for needle in ("JEJ-2026-B", "RPA-B1", "Piloto B", "Documento B"):
            assert needle not in titles, needle
        assert "JEJ-2026-A" in titles

    def test_the_digest_of_a_site_never_has_another_tenants_items(self, world):
        buckets = build_digest(world["a"]["center"], today=TODAY)
        labels = {item["label"] for items in buckets.values() for item in items}
        assert labels
        assert not any("B1" in label or label.endswith("B") for label in labels)
        assert "RPA-A1" in labels
