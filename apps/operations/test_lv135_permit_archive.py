"""LV-135: archivar un permiso, con confirmación y con motivo cuando corresponde.

Decisión del usuario entre tres alternativas: un permiso ya **aprobado o
completado** se puede archivar, pero cuesta un motivo escrito que queda en la
auditoría. Un permiso que la DGAC aprobó no desaparece de la lista sin
explicación — el mismo trato que `LV-101` hizo para corregir un estado.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = date(2026, 8, 24)


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC135P", name="Faena")


def _permit(cost_center, folio, *, status="requested", is_active=True):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=cost_center,
        purpose="other",
        purpose_detail="Levantamiento",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        location="Faena",
        status=status,
        is_active=is_active,
    )


@pytest.mark.django_db
class TestTheConfirmation:
    def test_it_always_confirms_even_with_nothing_attached(self, cost_center):
        """A diferencia del plan, un permiso es el espejo de un trámite ante la
        DGAC desde que se crea: la confirmación aparece siempre."""
        permit = _permit(cost_center, "JEJ-135-1")

        response = login_as("view_flightpermission", "delete_flightpermission").post(
            reverse("permission-archive", args=[permit.pk])
        )

        assert response.status_code == 200
        permit.refresh_from_db()
        assert permit.is_active is True

    def test_confirming_archives_a_draft_without_asking_for_a_reason(self, cost_center):
        permit = _permit(cost_center, "JEJ-135-2")

        response = login_as("view_flightpermission", "delete_flightpermission").post(
            reverse("permission-archive", args=[permit.pk]), {"confirm": "1"}
        )

        assert response.status_code == 302
        permit.refresh_from_db()
        assert permit.is_active is False

    def test_it_counts_what_hangs_off_the_permit(self, cost_center):
        from decimal import Decimal

        from apps.operations.models import FlightRequest

        permit = _permit(cost_center, "JEJ-135-3")
        FlightRequest.objects.create(
            title="CG-01",
            cost_center=cost_center,
            flight_permission=permit,
            center_lat=Decimal("-31.906392"),
            center_lon=Decimal("-70.717982"),
        )

        response = login_as("view_flightpermission", "delete_flightpermission").post(
            reverse("permission-archive", args=[permit.pk])
        )

        assert response.context["dependents"]["requests"] == 1
        assert response.context["dependents"]["flights"] == 0


@pytest.mark.django_db
class TestTheWrittenReason:
    def test_an_approved_permit_needs_one(self, cost_center):
        permit = _permit(cost_center, "JEJ-135-4", status="approved")

        response = login_as("view_flightpermission", "delete_flightpermission").post(
            reverse("permission-archive", args=[permit.pk]), {"confirm": "1"}
        )

        # Vuelve a la confirmación marcando la falta, no archiva.
        assert response.status_code == 200
        assert response.context["needs_reason"] is True
        assert response.context["reason_missing"] is True
        permit.refresh_from_db()
        assert permit.is_active is True

    def test_with_the_reason_it_archives_and_the_reason_is_on_record(self, cost_center):
        from apps.core.models import AuditEvent

        permit = _permit(cost_center, "JEJ-135-5", status="completed")

        response = login_as("view_flightpermission", "delete_flightpermission").post(
            reverse("permission-archive", args=[permit.pk]),
            {"confirm": "1", "reason": "Cargado por error, duplicaba JEJ-2026-002."},
        )

        assert response.status_code == 302
        permit.refresh_from_db()
        assert permit.is_active is False
        event = AuditEvent.objects.filter(action="archived").latest("created_at")
        assert "duplicaba" in str(event.metadata)

    def test_a_draft_does_not_ask_for_it(self, cost_center):
        """Pedir motivo para archivar un borrador sería fricción sin nada que
        proteger: no hay trámite que explicar todavía."""
        permit = _permit(cost_center, "JEJ-135-6", status="requested")

        response = login_as("view_flightpermission", "delete_flightpermission").post(
            reverse("permission-archive", args=[permit.pk])
        )

        assert response.context["needs_reason"] is False


@pytest.mark.django_db
class TestTheListing:
    def test_an_archived_permit_is_out_of_the_way_by_default(self, cost_center):
        _permit(cost_center, "JEJ-135-VIVO")
        _permit(cost_center, "JEJ-135-MUERTO", is_active=False)

        body = (
            login_as("view_flightpermission")
            .get(reverse("permission-list"))
            .content.decode()
        )

        assert "JEJ-135-VIVO" in body
        assert "JEJ-135-MUERTO" not in body

    def test_the_archived_filter_finds_it(self, cost_center):
        _permit(cost_center, "JEJ-135-VIVO")
        _permit(cost_center, "JEJ-135-MUERTO", is_active=False)

        body = (
            login_as("view_flightpermission")
            .get(reverse("permission-list"), {"is_active": "archived"})
            .content.decode()
        )

        assert "JEJ-135-MUERTO" in body
        assert "JEJ-135-VIVO" not in body


@pytest.mark.django_db
class TestPermissionsAndRestore:
    def test_archiving_needs_the_delete_permission(self, cost_center):
        permit = _permit(cost_center, "JEJ-135-7")

        response = login_as("view_flightpermission", "change_flightpermission").post(
            reverse("permission-archive", args=[permit.pk]), {"confirm": "1"}
        )

        assert response.status_code == 403
        permit.refresh_from_db()
        assert permit.is_active is True

    def test_restore_brings_it_back(self, cost_center):
        permit = _permit(cost_center, "JEJ-135-8", is_active=False)

        response = login_as("view_flightpermission", "change_flightpermission").post(
            reverse("permission-restore", args=[permit.pk])
        )

        assert response.status_code == 302
        permit.refresh_from_db()
        assert permit.is_active is True
