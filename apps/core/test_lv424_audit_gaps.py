"""LV-424: auditoría #13 y #14.

#13 — `MaintenanceComplete.post` reemplaza al `post` de `StatusTransitionView` y
se había quedado sin su `set_audit_context`: cerrar una mantención (que puede
devolver la aeronave al servicio) no dejaba un evento con la transición.

#14 — el `X-Request-ID` del cliente se copiaba sin validar al log, a la cabecera
de la respuesta y a `AuditEvent.request_id` (64 caracteres).
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.maintenance.models import MaintenanceRecord
from apps.registry.models import Aircraft, CostCenter


@pytest.fixture
def client_and_record(db):
    centre = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=centre,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "pw")
    client = Client()
    assert client.login(username="mechanic", password="pw")
    return client, record


def test_completing_a_maintenance_leaves_its_transition_in_the_audit(
    client_and_record,
):
    client, record = client_and_record

    response = client.post(
        reverse("maintenance-complete", args=[record.pk]),
        {"completed_date": "2026-07-24", "performed_by": "Workshop", "notes": "ok"},
    )

    assert response.status_code == 302
    event = AuditEvent.objects.get(action="status_changed", object_id=str(record.pk))
    assert event.model_label == "maintenance.MaintenanceRecord"
    assert event.metadata["from_status"] == "in_progress"
    assert event.metadata["to_status"] == "completed"


@pytest.mark.parametrize(
    "header",
    ["x" * 65, "abc\r\nfake-log-line", "<script>", "id with spaces"],
)
def test_an_unsafe_client_request_id_is_replaced(db, header):
    response = Client().get(reverse("health"), HTTP_X_REQUEST_ID=header)

    returned = response.headers["X-Request-ID"]
    assert returned != header
    assert len(returned) == 32  # uuid4().hex


def test_a_safe_client_request_id_is_kept(db):
    response = Client().get(reverse("health"), HTTP_X_REQUEST_ID="trace-01.A_b")

    assert response.headers["X-Request-ID"] == "trace-01.A_b"
