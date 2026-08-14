"""LV-101: the edit screen was a back door around every status guard.

Found in production. `JEJ-2026-001` carried a history row reading *"Aprobado
desde Completado · system · 2026-08-12"*: a permit that walked **backwards**
through the flow, attributed to nobody. Cause: `FlightPermissionForm` offers
`status` as a plain dropdown and `FlightPermissionUpdate` reused it without
setting `_changed_by`, so the transition guards never ran and the history signal
fell through to its `"system"` fallback.

Three separate guarantees are at stake, so they are three separate tests: the
door is closed, the paperwork guard still holds on the new route, and the
correction that replaces it records *who* and *why*.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.core.models import AuditEvent
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = date(2026, 8, 14)


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client, user


@pytest.fixture
def permit(db):
    cost_center = CostCenter.objects.create(code="CC101", name="Demo")
    operator = Operator.objects.create(full_name="Ana Rivas", cost_center=cost_center)
    aircraft = Aircraft.objects.create(
        registration="RPA-101", type="RPA", model="M3", manufacturer="DJI"
    )
    permit = FlightPermission.objects.create(
        permission_number="6031",
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        location="Tranque el Mauro",
        area_type="unpopulated",
        status="completed",
    )
    permit.operators.add(operator)
    permit.aircraft_fleet.add(aircraft)
    return permit


def _attach_authorization(permit):
    """The signed SIGO PDF the DGAC returns -- what LV-51/LV-64 guard on."""
    doc_type, _created = DocumentType.objects.get_or_create(
        code="dgac-rpa-operation-authorization",
        defaults={"name": "Autorización de Operación RPA", "requires_expiry": False},
    )
    return Document.objects.create(
        title="Autorización",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        issue_date=TODAY,
        file_path="auth/permit/x/auth.pdf",
    )


def _edit_payload(permit, **overrides):
    payload = {
        "permission_number": permit.permission_number,
        "operators": [str(o.pk) for o in permit.operators.all()],
        "aircraft_fleet": [str(a.pk) for a in permit.aircraft_fleet.all()],
        "cost_center": str(permit.cost_center_id),
        "purpose": permit.purpose,
        "purpose_detail": "",
        "valid_from": permit.valid_from.isoformat(),
        "valid_until": permit.valid_until.isoformat(),
        "location": permit.location,
        "region": "",
        "commune": "",
        "area_name": "",
        "latitude": "",
        "longitude": "",
        "radius_km": "",
        "max_altitude_ft": "",
        "area_type": permit.area_type,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestTheBackDoorIsClosed:
    def test_editing_cannot_change_the_status(self, permit):
        """The production case, as a test: completed -> approved through Edit."""
        client, _user = _client("change_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-update", args=[permit.pk]),
            _edit_payload(permit, status="approved"),
        )

        assert response.status_code == 302
        permit.refresh_from_db()
        assert permit.status == "completed"

    def test_the_edit_form_does_not_even_offer_it(self, permit):
        client, _user = _client("change_flightpermission", "view_flightpermission")

        html = client.get(
            reverse("permission-update", args=[permit.pk])
        ).content.decode()

        assert 'name="status"' not in html

    def test_editing_something_else_still_works(self, permit):
        """Closing the door must not close the screen."""
        client, _user = _client("change_flightpermission", "view_flightpermission")

        client.post(
            reverse("permission-update", args=[permit.pk]),
            _edit_payload(permit, location="Los Vilos"),
        )

        permit.refresh_from_db()
        assert permit.location == "Los Vilos"
        assert permit.status == "completed"


@pytest.mark.django_db
class TestCorrectionRecordsWhoAndWhy:
    def test_a_correction_moves_the_status_and_names_the_person(self, permit):
        _attach_authorization(permit)
        client, user = _client("change_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "approved", "reason": "Se completó por error, no se voló."},
        )

        assert response.status_code == 302
        permit.refresh_from_db()
        assert permit.status == "approved"
        entry = permit.history.order_by("-sequence").first()
        # The whole point: not "system".
        assert entry.changed_by == user.get_username()
        assert entry.changed_by_user == user
        assert "no se voló" in entry.notes

    def test_the_reason_is_required(self, permit):
        _attach_authorization(permit)
        client, _user = _client("change_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "approved", "reason": "   "},
        )

        assert response.status_code == 422
        permit.refresh_from_db()
        assert permit.status == "completed"

    def test_the_history_row_says_it_was_a_correction(self, permit):
        """A correction and a transition mean different things to an auditor.

        The language is pinned with `Accept-Language`: the prefix is translated,
        so asserting on its text would make this pass or fail depending on which
        locale happened to be active -- which is exactly how it behaved when run
        inside the full suite instead of on its own.
        """
        _attach_authorization(permit)
        client, _user = _client("change_flightpermission", "view_flightpermission")

        client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "approved", "reason": "Error de tipeo."},
            HTTP_ACCEPT_LANGUAGE="en",
        )

        notes = permit.history.order_by("-sequence").first().notes
        assert notes.startswith("Correction:")
        assert notes.endswith("Error de tipeo.")

    def test_it_lands_in_the_audit_log(self, permit):
        _attach_authorization(permit)
        client, _user = _client("change_flightpermission", "view_flightpermission")

        client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "approved", "reason": "Se completó por error."},
        )

        assert AuditEvent.objects.filter(action="status_corrected").exists()

    def test_the_current_status_is_not_offered(self, permit):
        """ "Correcting" to the status it already has would write a history row
        saying nothing happened."""
        client, _user = _client("change_flightpermission", "view_flightpermission")

        html = client.get(
            reverse("permission-correct-status", args=[permit.pk])
        ).content.decode()

        assert 'value="completed"' not in html
        assert 'value="approved"' in html


@pytest.mark.django_db
class TestTheCorrectionKeepsThePaperworkGuard:
    def test_it_cannot_reach_approved_without_the_signed_pdf(self, permit):
        """LV-51/LV-64 guard a fact in the world, not a route. A correction that
        skipped it would be the same hole with one more click."""
        permit.status = "requested"
        permit.save(update_fields=["status"])
        client, _user = _client("change_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "approved", "reason": "La DGAC ya respondió."},
        )

        assert response.status_code == 422
        permit.refresh_from_db()
        assert permit.status == "requested"
        assert AuditEvent.objects.filter(action="status_correction_rejected").exists()

    def test_but_an_unguarded_status_goes_through(self, permit):
        """Correcting *away* from a wrong approval is exactly the case that
        motivated this, and it must not need paperwork it never had."""
        client, _user = _client("change_flightpermission", "view_flightpermission")

        client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "requested", "reason": "Nunca se aprobó; se anotó mal."},
        )

        permit.refresh_from_db()
        assert permit.status == "requested"


@pytest.mark.django_db
class TestPermissions:
    def test_a_user_without_change_permission_gets_403(self, permit):
        client, _user = _client("view_flightpermission")

        response = client.post(
            reverse("permission-correct-status", args=[permit.pk]),
            {"status": "approved", "reason": "x"},
        )

        assert response.status_code == 403

    def test_the_form_itself_is_gated_too(self, permit):
        client, _user = _client("view_flightpermission")

        response = client.get(reverse("permission-correct-status", args=[permit.pk]))

        assert response.status_code == 403
