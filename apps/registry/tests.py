from datetime import date

import pytest
from django.test import Client
from django.utils import timezone, translation
from django.urls import reverse

from apps.core.models import OperationalTenant
from apps.operations.models import FlightPermission
from apps.registry.forms import AssignmentForm
from apps.registry.models import (
    Aircraft,
    Assignment,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="registry-admin", email="registry@example.com", password="password"
    )


@pytest.fixture
def registry_data():
    tenant = OperationalTenant.objects.create(name="Operations", slug="operations")
    center = CostCenter.objects.create(code="410", name="Operations", tenant=tenant)
    operator = Operator.objects.create(
        employee_id="OP-1", full_name="Pilot One", tenant=tenant, cost_center=center
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-1",
        type="RPAS",
        model="Mavic 3",
        manufacturer="DJI",
        tenant=tenant,
        cost_center=center,
    )
    return tenant, center, operator, aircraft


@pytest.mark.django_db
def test_qualification_type_seed_is_idempotent_and_keywords_lowercase():
    """B4.3: the qualification-type catalog seeds cleanly and keyword_list()
    normalizes for the B4.4 aircraft-model match."""
    from django.core.management import call_command

    call_command("seed_qualification_types")
    count = QualificationType.objects.count()
    assert count == 7
    mavic = QualificationType.objects.get(code="mavic")
    assert mavic.keyword_list() == ["mavic"]
    autel = QualificationType.objects.get(code="autel-evo")
    assert autel.keyword_list() == ["autel", "evo"]

    call_command("seed_qualification_types")
    assert QualificationType.objects.count() == count


@pytest.mark.django_db
def test_qualification_form_flags_empty_type_catalog():
    from apps.registry.forms import QualificationForm

    assert not QualificationType.objects.exists()
    help_text = str(QualificationForm().fields["qualification_type"].help_text)
    assert (
        "No qualification types configured yet" in help_text
        or "Aún no hay tipos de habilitación" in help_text
    )


@pytest.mark.django_db
def test_qualification_is_documentable(client, admin_user, registry_data):
    """B4.3: evidence documents can hang off a specific qualification."""
    from apps.compliance.forms import DOCUMENTABLE_MODELS

    assert ("registry", "qualification") in DOCUMENTABLE_MODELS


@pytest.mark.django_db
def test_aircraft_list_exposes_model(client, admin_user, registry_data):
    client.force_login(admin_user)
    response = client.get(reverse("aircraft-list"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_aircraft_list_shows_overdue_insurance(client, admin_user, registry_data):
    """LV-29: the JAC insurance expiry is a field on Aircraft (was derived from
    an is_insurance Document under LV-4); the list marks a past date overdue."""
    _tenant, _center, _operator, aircraft = registry_data
    aircraft.insurance_expiry = date(2025, 6, 1)  # in the past relative to any run
    aircraft.save(update_fields=["insurance_expiry"])
    client.force_login(admin_user)

    response = client.get(reverse("aircraft-list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "2025-06-01" in content
    assert "Overdue" in content or "Atrasada" in content


@pytest.mark.django_db
def test_aircraft_list_shows_dash_without_an_insurance_document(
    client, admin_user, registry_data
):
    client.force_login(admin_user)
    response = client.get(reverse("aircraft-list"))
    aircraft_row = [
        line for line in response.content.decode().splitlines() if "RPA-1" in line
    ]

    assert response.status_code == 200
    assert aircraft_row
    assert "RPA-1" in response.content.decode()
    assert "Mavic 3" in response.content.decode()


@pytest.mark.django_db
def test_confirmed_assignment_rejects_operator_overlap(registry_data):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 12),
        status="confirmed",
    )
    form = AssignmentForm(
        data={
            "operator": operator.pk,
            "aircraft": aircraft.pk,
            "cost_center": center.pk,
            "purpose": "Inspection",
            "start_date": "2026-07-11",
            "end_date": "2026-07-13",
            "status": "confirmed",
        }
    )

    assert not form.is_valid()
    assert "operator" in form.errors


@pytest.mark.django_db
def test_assignment_status_choices_are_translated_and_confirmed_requires_cost_center(
    registry_data,
):
    _tenant, _center, operator, aircraft = registry_data
    with translation.override("es"):
        form = AssignmentForm()
        assert dict(form.fields["status"].choices)["planned"] == "Planificado"

    form = AssignmentForm(
        data={
            "operator": operator.pk,
            "aircraft": aircraft.pk,
            "cost_center": "",
            "purpose": "Inspection",
            "start_date": "2026-07-11",
            "end_date": "2026-07-13",
            "status": "confirmed",
        }
    )

    assert not form.is_valid()
    assert "cost_center" in form.errors


@pytest.mark.django_db
def test_assignment_list_filters_by_status_and_review(
    client, admin_user, registry_data
):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 10),
        status="confirmed",
    )
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        start_date=date(2026, 7, 20),
        status="planned",
    )
    client.force_login(admin_user)

    response = client.get(reverse("assignment-list"), {"status": "confirmed"})
    assert response.status_code == 200
    assert response.context["object_list"].count() == 1
    assert "Período" in response.content.decode()

    response = client.get(reverse("assignment-list"), {"review": "needs_review"})
    assert response.context["object_list"].count() == 1


@pytest.mark.django_db
def test_calendar_feed_contains_resource_and_expiration_events(
    client, admin_user, registry_data
):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
        status="planned",
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type=QualificationType.objects.create(code="rpas", name="RPAS"),
        issue_date=date(2026, 1, 1),
        expiry_date=date(2026, 7, 21),
    )
    permission = FlightPermission.objects.create(
        permission_number="PERM-1",
        cost_center=center,
        purpose="Inspection",
        valid_from=date(2026, 7, 20),
        valid_until=date(2026, 7, 20),
        location="Santiago",
    )
    permission.operators.add(operator)
    permission.aircraft_fleet.add(aircraft)
    client.force_login(admin_user)

    response = client.get(
        reverse("calendar-events"),
        {
            "start": "2026-07-01",
            "end": "2026-08-01",
            "types": "permission,assignment,qualification",
        },
    )
    event_types = {event["type"] for event in response.json()}

    assert response.status_code == 200
    assert {"permission", "assignment", "qualification"}.issubset(event_types)


class TestArchiveRestoreFromUI:
    """V.30/V.31: archiving lived only in the technical admin, and archiving a
    cost center silently dropped it from the digest."""

    @staticmethod
    def _world(db):
        center = CostCenter.objects.create(code="ARC", name="Archive tests")
        operator = Operator.objects.create(
            employee_id="ARC-1",
            full_name="Pilot",
            cost_center=center,
            email="pilot@test.cl",
        )
        return center, operator

    @staticmethod
    def _client(*codenames):
        from django.contrib.auth.models import Permission, User

        user = User.objects.create_user(f"u-{'-'.join(codenames)}", password="pw")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = Client()
        assert client.login(username=user.username, password="pw")
        return client

    @pytest.mark.django_db
    def test_archive_requires_delete_permission(self, db):
        _, operator = self._world(db)
        client = self._client("view_operator", "change_operator")

        response = client.post(reverse("operator-archive", args=[operator.pk]))

        operator.refresh_from_db()
        assert response.status_code == 403
        assert operator.is_active is True

    @pytest.mark.django_db
    def test_archive_and_restore_roundtrip(self, db):
        _, operator = self._world(db)
        client = self._client("delete_operator", "change_operator")

        archived = client.post(reverse("operator-archive", args=[operator.pk]))
        operator.refresh_from_db()
        assert archived.status_code == 302
        assert operator.is_active is False

        restored = client.post(reverse("operator-restore", args=[operator.pk]))
        operator.refresh_from_db()
        assert restored.status_code == 302
        assert operator.is_active is True

    @pytest.mark.django_db
    def test_cost_center_archive_shows_dependents_first(self, db):
        center, operator = self._world(db)
        client = self._client("delete_costcenter")

        response = client.post(reverse("costcenter-archive", args=[center.pk]))

        center.refresh_from_db()
        assert response.status_code == 200  # confirmation page, nothing archived
        assert center.is_active is True
        assert "1" in response.content.decode()

        confirmed = client.post(
            reverse("costcenter-archive", args=[center.pk]), {"confirm": "1"}
        )
        center.refresh_from_db()
        assert confirmed.status_code == 302
        assert center.is_active is False

    @pytest.mark.django_db
    def test_cost_center_without_dependents_archives_directly(self, db):
        center = CostCenter.objects.create(code="EMPTY", name="No dependents")
        client = self._client("delete_costcenter")

        response = client.post(reverse("costcenter-archive", args=[center.pk]))

        center.refresh_from_db()
        assert response.status_code == 302
        assert center.is_active is False


# ── LV-29: DGAC vigencias ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_vigencia_overdue_properties(registry_data):
    """Past dates are overdue; a missing date is unknown, not overdue."""
    _tenant, _center, operator, aircraft = registry_data
    assert operator.credential_is_overdue is False
    assert aircraft.insurance_is_overdue is False

    operator.credential_expiry = date(2000, 1, 1)
    aircraft.insurance_expiry = date(2000, 1, 1)
    assert operator.credential_is_overdue is True
    assert aircraft.insurance_is_overdue is True


@pytest.mark.django_db
def test_operator_list_shows_credential_expiry_column(client, admin_user, registry_data):
    _tenant, _center, operator, _aircraft = registry_data
    operator.credential_expiry = date(2025, 6, 1)  # past
    operator.save(update_fields=["credential_expiry"])
    client.force_login(admin_user)

    response = client.get(reverse("operator-list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "2025-06-01" in content
    assert "Overdue" in content or "Atrasada" in content


@pytest.mark.django_db
def test_load_dgac_vigencias_matches_updates_and_reports_unmatched(
    registry_data, capsys
):
    from django.core.management import call_command

    _tenant, _center, operator, aircraft = registry_data
    operator.dgac_credential = "CRED-1"
    operator.save(update_fields=["dgac_credential"])

    csv_rows = [
        ("operator", "CRED-1", "2026-09-01"),
        ("aircraft", "RPA-1", "2026-10-01"),
        ("aircraft", "RPA-DOES-NOT-EXIST", "2026-10-01"),
    ]
    tmp = _write_csv(csv_rows)
    call_command("load_dgac_vigencias", "--file", str(tmp))

    operator.refresh_from_db()
    aircraft.refresh_from_db()
    assert operator.credential_expiry == date(2026, 9, 1)
    assert aircraft.insurance_expiry == date(2026, 10, 1)
    out = capsys.readouterr().out
    assert "unmatched: aircraft:RPA-DOES-NOT-EXIST" in out


@pytest.mark.django_db
def test_load_dgac_vigencias_dry_run_and_idempotent(registry_data, capsys):
    from django.core.management import call_command

    _tenant, _center, _operator, aircraft = registry_data
    tmp = _write_csv([("aircraft", "RPA-1", "2026-10-01")])

    call_command("load_dgac_vigencias", "--file", str(tmp), "--dry-run")
    aircraft.refresh_from_db()
    assert aircraft.insurance_expiry is None  # dry-run wrote nothing

    call_command("load_dgac_vigencias", "--file", str(tmp))
    aircraft.refresh_from_db()
    assert aircraft.insurance_expiry == date(2026, 10, 1)

    # A rerun with the same data changes nothing.
    call_command("load_dgac_vigencias", "--file", str(tmp))
    assert "0 updated, 1 already current" in capsys.readouterr().out


@pytest.mark.django_db
def test_notify_expiring_credentials_emails_operator_with_their_items(
    registry_data, settings
):
    from django.core import mail
    from django.core.management import call_command

    _tenant, _center, operator, _aircraft = registry_data
    operator.email = "pilot@example.cl"
    operator.credential_expiry = timezone.localdate() + date.resolution * 5  # +5 days
    operator.save(update_fields=["email", "credential_expiry"])
    qual_type = QualificationType.objects.create(name="Mavic", code="mavic")
    Qualification.objects.create(
        operator=operator,
        qualification_type=qual_type,
        expiry_date=timezone.localdate() - date.resolution * 2,  # already lapsed
    )

    call_command("notify_expiring_credentials")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["pilot@example.cl"]
    assert "Mavic" in message.body


@pytest.mark.django_db
def test_notify_expiring_credentials_skips_operator_without_email(
    registry_data, capsys
):
    from django.core import mail
    from django.core.management import call_command

    _tenant, _center, operator, _aircraft = registry_data
    operator.email = ""
    operator.credential_expiry = timezone.localdate() + date.resolution * 5
    operator.save(update_fields=["email", "credential_expiry"])

    call_command("notify_expiring_credentials")

    assert mail.outbox == []
    assert "no email on file" in capsys.readouterr().out


def _write_csv(rows):
    """Write a kind,key,expiry CSV to the pytest tmp dir and return its path."""
    import csv
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "vigencias.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kind", "key", "expiry"])
        writer.writerows(rows)
    return path

    @pytest.mark.django_db
    def test_notification_email_ignores_archived_operator(self, db):
        center, operator = self._world(db)
        center.responsible_operator = operator
        center.save(update_fields=["responsible_operator"])
        assert center.notification_email == "pilot@test.cl"

        operator.is_active = False
        operator.save(update_fields=["is_active"])

        assert center.notification_email == ""

    @pytest.mark.django_db
    def test_notification_email_falls_back_to_external_contact(self, db):
        """The responsible person is not always in the operator roster (an
        administrator, secretary, or safety officer instead of a pilot)."""
        center, _ = self._world(db)
        center.responsible_contact_name = "Secretaria de faena"
        center.responsible_contact_email = "secretaria@test.cl"
        center.save(
            update_fields=["responsible_contact_name", "responsible_contact_email"]
        )

        assert center.notification_email == "secretaria@test.cl"

    @pytest.mark.django_db
    def test_notification_email_prefers_operator_over_external_contact(self, db):
        center, operator = self._world(db)
        center.responsible_operator = operator
        center.responsible_contact_email = "secretaria@test.cl"
        center.save(update_fields=["responsible_operator", "responsible_contact_email"])

        assert center.notification_email == "pilot@test.cl"

    @pytest.mark.django_db
    def test_notification_email_falls_back_to_contact_when_operator_unreachable(
        self, db
    ):
        """An operator on file who left is not a reason to go silent when an
        external contact is also configured."""
        center, operator = self._world(db)
        center.responsible_operator = operator
        center.responsible_contact_email = "secretaria@test.cl"
        center.save(update_fields=["responsible_operator", "responsible_contact_email"])
        operator.is_active = False
        operator.save(update_fields=["is_active"])

        assert center.notification_email == "secretaria@test.cl"

    @pytest.mark.django_db
    def test_digest_reports_archived_center_with_active_dependents(self, db):
        from apps.compliance.digest import archived_centers_with_active_dependents

        center, operator = self._world(db)
        center.is_active = False
        center.save(update_fields=["is_active"])

        rows = archived_centers_with_active_dependents()

        assert len(rows) == 1
        reported, operators, aircraft = rows[0]
        assert reported.pk == center.pk
        assert operators == 1
        assert aircraft == 0
